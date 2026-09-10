#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import json
import os
import queue
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('LIMS_DB_PATH', os.path.join(BASE, 'lims.db'))
OFFICIAL_CATALOG = os.path.join(BASE, 'official_test_catalog.json')
QUALITY_UPLOADS = os.path.join(BASE, 'uploads', 'quality')
RECORD_UPLOADS = os.path.join(BASE, 'uploads', 'records')
PORT = int(os.environ.get('PORT', os.environ.get('LIMS_PORT', '8080')))
ALLOWED_ORIGIN = os.environ.get('LIMS_ALLOWED_ORIGIN', '').rstrip('/')
BALADY_API_BASE_URL = os.environ.get('BALADY_API_BASE_URL', '').strip()
BALADY_API_TOKEN = os.environ.get('BALADY_API_TOKEN', '').strip()
BALADY_API_KEY = os.environ.get('BALADY_API_KEY', '').strip()
SAUDI_TIME_ZONE = 'Asia/Riyadh'
SESSIONS = {}
OTP_REQUESTS = {}
OTP_RESEND_SECONDS = 60
EVENT_SUBSCRIBERS = set()
EVENT_SUBSCRIBERS_LOCK = threading.Lock()

PROJECT_STATUSES = {'مخطط', 'نشط', 'موقوف', 'قيد المراجعة', 'معتمد', 'مكتمل', 'مفتوح'}
WORK_ORDER_STATUSES = {'مفتوح', 'قيد التنفيذ', 'بانتظار المراجعة', 'موقوف', 'مكتمل'}
FIELD_STATUSES = {'مسودة', 'مرسلة', 'قيد المراجعة', 'معتمدة', 'مرفوضة'}
PRIORITIES = {'منخفضة', 'متوسطة', 'عالية', 'حرجة'}

ROLE_PERMS = {
    'admin': {'*'},
    'general_manager': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports', 'equipment', 'quality', 'audit', 'users', 'sync'},
    'technical_manager': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports', 'equipment', 'audit', 'sync'},
    'laboratory_manager': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports', 'equipment', 'audit', 'sync'},
    'quality_manager': {'dashboard', 'equipment', 'quality', 'audit'},
    'quality_officer': {'dashboard', 'quality'},
    'calibration_officer': {'dashboard', 'quality'},
    'document_controller': {'dashboard', 'quality'},
    'manager': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports', 'equipment', 'quality', 'audit', 'users', 'sync'},
    'quality': {'dashboard', 'quality'},
    'technician': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports'},
    'field': {'dashboard', 'field', 'clients', 'projects', 'samples'}
}


def db():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    return connection


def hp(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200000)
    return salt.hex() + ':' + digest.hex()


def checkpw(password, stored_hash):
    try:
        salt, digest = stored_hash.split(':', 1)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 200000).hex()
        return hmac.compare_digest(actual, digest)
    except (TypeError, ValueError):
        return False


def has_perm(user, permission):
    if not user:
        return False
    permissions = ROLE_PERMS.get(user.get('role'), set())
    return user.get('role') == 'admin' or '*' in permissions or permission in permissions


def require_role(user, roles):
    return bool(user and (user.get('role') == 'admin' or user.get('role') in roles))


def rowdict(row):
    return dict(row) if row else None


def _find_value(payload, aliases):
    wanted = {str(alias).lower().replace('_', '').replace('-', '') for alias in aliases}
    stack = [payload]
    while stack:
        current = stack.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                normalized = str(key).lower().replace('_', '').replace('-', '')
                if normalized in wanted and value not in (None, '') and not isinstance(value, (dict, list)):
                    return value
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)
    return ''


def fetch_balady_permit(license_no):
    if not BALADY_API_BASE_URL or not (BALADY_API_TOKEN or BALADY_API_KEY):
        raise RuntimeError('تكامل بلدي غير مهيأ: أضف عنوان API الرسمي ورمز التفويض في إعدادات الخادم')
    encoded = urlencode({'license': license_no})
    url = BALADY_API_BASE_URL.replace('{license}', urlencode({'v': license_no})[2:]) if '{license}' in BALADY_API_BASE_URL else BALADY_API_BASE_URL + ('&' if '?' in BALADY_API_BASE_URL else '?') + encoded
    headers = {'Accept': 'application/json', 'User-Agent': 'ASAS-LIMS/8.1'}
    if BALADY_API_TOKEN:
        headers['Authorization'] = 'Bearer ' + BALADY_API_TOKEN
    if BALADY_API_KEY:
        headers['X-API-Key'] = BALADY_API_KEY
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise PermissionError('رفضت منصة بلدي التفويض؛ تحقق من صلاحية رمز API')
        if error.code == 404:
            raise LookupError('لم يتم العثور على رخصة بهذا الرقم في منصة بلدي')
        raise RuntimeError('تعذر الاتصال بمنصة بلدي حالياً')
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError('تعذر الاتصال بمنصة بلدي أو قراءة استجابتها')
    return {'source':'balady','license_no':str(_find_value(payload,['licenseNo','licenseNumber','permitNo','permitNumber','رقم الرخصة']) or license_no),'municipality':_find_value(payload,['municipalityName','amanahName','municipality','الأمانة','البلدية']),'contractor_name':_find_value(payload,['contractorName','contractor','اسم المقاول']),'project_name':_find_value(payload,['projectName','project','اسم المشروع']),'sector_name':_find_value(payload,['sectorName','districtName','sector','القطاع','الحي']),'location':_find_value(payload,['location','address','siteAddress','الموقع','العنوان']),'permit_type':_find_value(payload,['permitType','licenseType','نوع الرخصة','نوع التصريح']),'status':_find_value(payload,['statusName','licenseStatus','permitStatus','الحالة']),'issue_date':_find_value(payload,['issueDate','startDate','تاريخ الإصدار']),'expiry_date':_find_value(payload,['expiryDate','endDate','تاريخ الانتهاء']),'owner_name':_find_value(payload,['ownerName','beneficiaryName','اسم المالك','اسم المستفيد']),'reference_url':_find_value(payload,['referenceUrl','detailsUrl','الرابط']),'details':payload}


def nextno(connection, prefix, table):
    return prefix + str(connection.execute('select coalesce(max(id),0)+1 from ' + table).fetchone()[0]).zfill(6)


def parse_optional_int(value):
    if value in (None, '', 0, '0'):
        return None
    return int(value)


def normalize_priority(value):
    return value if value in PRIORITIES else 'متوسطة'


RECORD_TYPES = {
    'client': ('clients', 'clients'), 'project': ('projects', 'projects'),
    'work_order': ('work_orders', 'projects'), 'sample': ('samples', 'samples'),
    'test': ('tests', 'tests'), 'report': ('reports', 'reports'),
    'equipment': ('equipment', 'equipment'), 'user': ('users', 'users'),
    'catalog': ('test_catalog', 'catalog')
}


def record_allowed(user, entity_type):
    item = RECORD_TYPES.get(entity_type)
    return bool(item and (has_perm(user, item[1]) or (entity_type == 'catalog' and has_perm(user, 'quality'))))


def save_record_file(connection, user, data):
    entity_type = str(data.get('entity_type') or '')
    if not record_allowed(user, entity_type):
        raise PermissionError('لا تملك صلاحية هذا السجل')
    entity_id = parse_optional_int(data.get('entity_id'))
    table = RECORD_TYPES[entity_type][0]
    if not entity_id or not connection.execute('select id from ' + table + ' where id=?', (entity_id,)).fetchone():
        raise ValueError('السجل المحدد غير موجود')
    original_name = os.path.basename(str(data.get('file_name') or ''))
    extension = os.path.splitext(original_name)[1].lower()
    encoded = str(data.get('file_base64') or '')
    if not encoded or extension not in {'.pdf', '.doc', '.docx', '.xls', '.xlsx'}:
        raise ValueError('يسمح فقط بملفات PDF أو Word أو Excel')
    if len(encoded) > 35_000_000:
        raise ValueError('حجم الملف يتجاوز 25MB')
    try:
        content = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise ValueError('ملف مرفوع غير صالح')
    if len(content) > 25 * 1024 * 1024:
        raise ValueError('حجم الملف يتجاوز 25MB')
    os.makedirs(RECORD_UPLOADS, exist_ok=True)
    stored_name = secrets.token_urlsafe(18) + extension
    with open(os.path.join(RECORD_UPLOADS, stored_name), 'wb') as uploaded:
        uploaded.write(content)
    connection.execute('insert into record_attachments(entity_type,entity_id,original_name,stored_name,uploaded_by) values(?,?,?,?,?)',
                       (entity_type, entity_id, original_name, stored_name, user['id']))
    return stored_name


def migrate_schema(connection):
    additions = {
        'users': [
            ('phone', 'phone TEXT')
        ],
        'projects': [
            ('priority', "priority TEXT NOT NULL DEFAULT 'متوسطة'"),
            ('description', 'description TEXT'),
            ('contractor_name', 'contractor_name TEXT'),
            ('consultant_name', 'consultant_name TEXT'),
            ('start_date', 'start_date TEXT'),
            ('due_date', 'due_date TEXT'),
            ('progress', 'progress INTEGER NOT NULL DEFAULT 0'),
            ('manager_id', 'manager_id INTEGER'),
            ('reviewed_by', 'reviewed_by INTEGER'),
            ('reviewed_at', 'reviewed_at TEXT'),
            ('approved_by', 'approved_by INTEGER'),
            ('approved_at', 'approved_at TEXT'),
            ('updated_at', 'updated_at TEXT')
        ],
        'field_visits': [
            ('balady_permit_no', 'balady_permit_no TEXT'),
            ('balady_municipality', 'balady_municipality TEXT'),
            ('balady_permit_type', 'balady_permit_type TEXT'),
            ('balady_permit_status', 'balady_permit_status TEXT'),
            ('balady_reference_url', 'balady_reference_url TEXT')
        ]
    }
    for table, columns in additions.items():
        existing = {row['name'] for row in connection.execute('pragma table_info(' + table + ')')}
        for name, definition in columns:
            if name not in existing:
                connection.execute('alter table ' + table + ' add column ' + definition)
    connection.execute('create index if not exists idx_projects_due_date on projects(due_date)')


def init():
    os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
    connection = db()
    with open(os.path.join(BASE, 'schema.sql'), encoding='utf-8') as schema:
        connection.executescript(schema.read())
    migrate_schema(connection)
    with open(OFFICIAL_CATALOG, encoding='utf-8') as catalog_file:
        official_catalog = json.load(catalog_file)
    for category, entries in official_catalog.items():
        for code, name_ar in entries:
            connection.execute('''
                insert into test_catalog(code,name_ar,name_en,category,standard,version,active)
                values(?,?,?,?,?,'معتمد',1)
                on conflict(code) do update set name_ar=excluded.name_ar,name_en=excluded.name_en,
                    category=excluded.category,standard=excluded.standard,version=excluded.version,active=1
            ''', (code, name_ar, name_ar, category, 'ASTM ' + code))
    if connection.execute('select count(*) from users').fetchone()[0] == 0:
        password = os.environ.get('LIMS_BOOTSTRAP_PASSWORD')
        if not password or len(password) < 12:
            connection.close()
            raise RuntimeError('يتطلب أول تشغيل تعيين LIMS_BOOTSTRAP_PASSWORD محلياً إلى كلمة مرور من 12 حرفاً على الأقل.')
        phone = os.environ.get('LIMS_BOOTSTRAP_PHONE', '').strip()
        if not valid_e164(phone):
            connection.close()
            raise RuntimeError('يتطلب أول تشغيل تعيين LIMS_BOOTSTRAP_PHONE برقم المدير بصيغة دولية، مثل +9665XXXXXXXX، لاستخدام OTP.')
        connection.execute(
            'insert into users(username,password_hash,full_name,role,phone) values(?,?,?,?,?)',
            ('admin', hp(password), 'مدير المختبر', 'admin', phone)
        )
        print('تم إنشاء حساب admin الأول باستخدام كلمة المرور المحلية التي وفرتها.')
    connection.commit()
    connection.close()


def audit(connection, user_id, action, entity, entity_id, details):
    connection.execute(
        'insert into audit_log(user_id,action,entity,entity_id,details) values(?,?,?,?,?)',
        (user_id, action, entity, entity_id, details)
    )


def queue_sync(connection, entity, entity_id, operation, payload):
    connection.execute(
        'insert into sync_queue(entity,entity_id,operation,payload_json) values(?,?,?,?)',
        (entity, entity_id, operation, json.dumps(payload, ensure_ascii=False))
    )


def user_from(handler):
    authorization = handler.headers.get('Authorization', '')
    if authorization.startswith('Bearer '):
        return SESSIONS.get(authorization[7:])
    for item in handler.headers.get('Cookie', '').split(';'):
        item = item.strip()
        if item.startswith('LIMS_SESSION='):
            return SESSIONS.get(item.split('=', 1)[1])
    return None


def twilio_verify_ready():
    return all(os.environ.get(key, '').strip() for key in (
        'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_VERIFY_SERVICE_SID'
    ))


def valid_e164(phone):
    return phone.startswith('+') and phone[1:].isdigit() and 8 <= len(phone) <= 16


def phone_in_use(connection, phone, exclude_user_id=None):
    if not phone:
        return False
    query = 'select 1 from users where phone=?'
    params = [phone]
    if exclude_user_id is not None:
        query += ' and id<>?'
        params.append(exclude_user_id)
    return connection.execute(query, params).fetchone() is not None


def twilio_verify_request(endpoint, fields):
    """Use Verify credentials from server environment; never return them to clients."""
    account_sid = os.environ['TWILIO_ACCOUNT_SID']
    auth_token = os.environ['TWILIO_AUTH_TOKEN']
    service_sid = os.environ['TWILIO_VERIFY_SERVICE_SID']
    credentials = base64.b64encode(f'{account_sid}:{auth_token}'.encode()).decode()
    request = urllib.request.Request(
        f'https://verify.twilio.com/v2/Services/{service_sid}/{endpoint}',
        data=urlencode(fields).encode(),
        headers={
            'Authorization': 'Basic ' + credentials,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        },
        method='POST'
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def otp_delivery_error(channel, error):
    """Map Twilio transport failures to safe, actionable client errors.

    Twilio's response can contain account and destination details.  Those must
    stay in the provider response, so the API returns only a channel-specific
    status that lets the sign-in screen offer the appropriate fallback.
    """
    status = getattr(error, 'code', None)
    if status in (401, 403):
        return 'otp_provider_not_configured'
    if status == 429:
        return 'otp_resend_too_soon'
    if channel == 'whatsapp':
        return 'otp_whatsapp_unavailable'
    if channel == 'call':
        return 'otp_call_unavailable'
    return 'otp_sms_unavailable'


def create_whatsapp_draft(connection, created_by, related_entity, related_id, message, recipient_user_id=None):
    """Store a reviewable message draft; no WhatsApp transport is invoked here."""
    connection.execute(
        '''insert into whatsapp_drafts(recipient_user_id,related_entity,related_id,message_text,created_by)
           values(?,?,?,?,?)''',
        (recipient_user_id, related_entity, related_id, message.strip(), created_by)
    )


def publish_event(entity, operation, entity_id):
    """Notify connected same-origin sessions without transmitting record data."""
    event = {'entity': entity, 'operation': operation, 'id': entity_id}
    with EVENT_SUBSCRIBERS_LOCK:
        subscribers = list(EVENT_SUBSCRIBERS)
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(event)
        except queue.Full:
            # A slow browser will receive the next update or use its normal refresh.
            pass


def start_otp_challenge(connection, login_id, password, channel='sms'):
    """Validate the first factor, then request a time-limited OTP challenge."""
    if channel not in ('sms', 'call', 'whatsapp'):
        return None, 'invalid_otp_channel', 400, None
    user = connection.execute(
        'select * from users where (username=? or phone=?) and active=1',
        (login_id, login_id)
    ).fetchone()
    if not user or not checkpw(password, user['password_hash']):
        return None, 'invalid_credentials', 401, None
    phone = str(user['phone'] or '').strip()
    if not valid_e164(phone):
        return None, 'phone_not_configured', 409, None
    if not twilio_verify_ready():
        return None, 'otp_provider_not_configured', 503, None
    now = time.monotonic()
    request_key = (user['id'], channel)
    retry_after = OTP_RESEND_SECONDS - (now - OTP_REQUESTS.get(request_key, 0))
    if retry_after > 0:
        return None, 'otp_resend_too_soon', 429, int(retry_after) + 1
    try:
        twilio_verify_request('Verifications', {'To': phone, 'Channel': channel})
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        audit(connection, user['id'], 'OTP_FAILED', 'user', user['id'], 'Twilio Verify request failed')
        connection.commit()
        error_code = otp_delivery_error(channel, error)
        return None, error_code, 429 if error_code == 'otp_resend_too_soon' else 502, None
    OTP_REQUESTS[request_key] = now
    audit(connection, user['id'], 'OTP_REQUESTED', 'user', user['id'], 'Twilio Verify {} requested'.format(channel))
    connection.commit()
    return user, None, 200, None


def password_login(connection, login_id, password):
    user = connection.execute('select * from users where (username=? or phone=?) and active=1', (login_id, login_id)).fetchone()
    if not user or not checkpw(password, user['password_hash']):
        return None, None, 'invalid_credentials'
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = dict(user)
    audit(connection, user['id'], 'PASSWORD_LOGIN', 'user', user['id'], 'Password authenticated sign-in')
    connection.commit()
    return user, token, None


class H(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def cors_origin(self):
        origin = self.headers.get('Origin', '').rstrip('/')
        return origin if ALLOWED_ORIGIN and origin == ALLOWED_ORIGIN else None

    def send_cors_headers(self):
        origin = self.cors_origin()
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Vary', 'Origin')

    def send_json(self, data, code=200, extra_headers=None):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_cors_headers()
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        raw = self.rfile.read(length) if length else b'{}'
        return json.loads(raw or b'{}')

    def static(self, filename, content_type):
        target = os.path.join(BASE, filename)
        if not os.path.isfile(target):
            return self.send_json({'error': 'الملف غير موجود'}, 404)
        with open(target, 'rb') as asset:
            body = asset.read()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not urlparse(self.path).path.startswith('/api/') or not self.cors_origin():
            return self.send_json({'error': 'المصدر غير مسموح'}, 403)
        self.send_response(204)
        self.send_cors_headers()
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Max-Age', '600')
        self.end_headers()

    def require_permission(self, user, permission):
        if not has_perm(user, permission):
            self.send_json({'error': 'ليس لديك الصلاحية المطلوبة'}, 403)
            return False
        return True

    def stream_events(self):
        subscriber = queue.Queue(maxsize=20)
        with EVENT_SUBSCRIBERS_LOCK:
            EVENT_SUBSCRIBERS.add(subscriber)
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()
            self.wfile.write(b'retry: 5000\n\n')
            self.wfile.flush()
            # Reconnect after a bounded interval to avoid holding a worker forever.
            for _ in range(3):
                try:
                    event = subscriber.get(timeout=20)
                    message = 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
                except queue.Empty:
                    message = ': keepalive\n\n'
                self.wfile.write(message.encode('utf-8'))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with EVENT_SUBSCRIBERS_LOCK:
                EVENT_SUBSCRIBERS.discard(subscriber)

    def project_rows(self, connection):
        query = '''
            select p.*, c.name client_name, u.full_name manager_name,
              (select count(*) from work_orders w where w.project_id=p.id) work_orders_count,
              (select count(*) from samples s where s.project_id=p.id) samples_count,
              (select count(*) from tests t join samples s on s.id=t.sample_id where s.project_id=p.id) tests_count,
              (select count(*) from reports r join tests t on t.id=r.test_id join samples s on s.id=t.sample_id where s.project_id=p.id) reports_count
            from projects p
              left join clients c on c.id=p.client_id
              left join users u on u.id=p.manager_id
            order by case when p.due_date is null then 1 else 0 end, p.due_date, p.id desc
        '''
        return [dict(row) for row in connection.execute(query).fetchall()]

    def dashboard(self, connection, user):
        projects = self.project_rows(connection)
        q = lambda sql, params=(): [dict(row) for row in connection.execute(sql, params).fetchall()]
        work_orders = q('''
            select w.*, p.code project_code, p.name project_name, u.full_name assignee_name
            from work_orders w
            join projects p on p.id=w.project_id
            left join users u on u.id=w.assigned_to
            order by case when w.due_date is null then 1 else 0 end, w.due_date, w.id desc
        ''')
        counts = {
            key: connection.execute('select count(*) from ' + table).fetchone()[0]
            for key, table in (
                ('projects', 'projects'), ('work_orders', 'work_orders'), ('samples', 'samples'),
                ('tests', 'tests'), ('reports', 'reports'), ('equipment', 'equipment'),
                ('field_visits', 'field_visits'), ('sync_queue', 'sync_queue')
            )
        }
        alerts = {
            'blocked_projects': q("select id,code,name,priority,due_date from projects where status='موقوف' order by priority desc,id desc"),
            'overdue_work_orders': q("select w.id,w.order_no,w.title,w.due_date,p.code project_code from work_orders w join projects p on p.id=w.project_id where w.due_date is not null and w.due_date < date('now') and w.status != 'مكتمل' order by w.due_date"),
            'awaiting_review': q("select id,code,name,'project' entity from projects where status='قيد المراجعة' union all select id,license_no,'زيارة ميدانية','field_visit' entity from field_visits where status='قيد المراجعة' order by id desc")
        }
        counts['whatsapp_drafts'] = connection.execute(
            "select count(*) from whatsapp_drafts where status='draft'"
        ).fetchone()[0]
        counts['whatsapp_ready'] = connection.execute(
            "select count(*) from whatsapp_drafts where status='ready'"
        ).fetchone()[0]
        return {
            'counts': counts,
            'projects': projects,
            'work_orders': work_orders,
            'clients': q('select * from clients order by id desc'),
            'samples': q('''
                select s.*,p.name project_name,p.code project_code,
                    (select count(*) from tests t where t.sample_id=s.id and t.status='مخطط') planned_tests_count
                from samples s left join projects p on p.id=s.project_id order by s.id desc
            '''),
            'tests': q('select t.*,s.sample_no,tc.code,tc.name_ar,tc.standard,pr.mdd,pr.omc,u.full_name technician_name from tests t join samples s on s.id=t.sample_id join test_catalog tc on tc.id=t.catalog_id left join proctor_results pr on pr.test_id=t.id left join users u on u.id=t.technician_id order by t.id desc'),
            'reports': q('select r.*,t.test_no,tc.name_ar,s.sample_no from reports r join tests t on t.id=r.test_id join samples s on s.id=t.sample_id join test_catalog tc on tc.id=t.catalog_id order by r.id desc'),
            'equipment': q('select * from equipment order by id desc'),
            'audit': q('select a.*,u.full_name from audit_log a left join users u on u.id=a.user_id order by a.id desc limit 150'),
            'activity': q('select created_at,action,details from audit_log order by id desc limit 15'),
            'alerts': alerts,
            'sync': q("select id,entity,entity_id,operation,status,attempts,created_at,last_error from sync_queue where status='queued' order by id desc limit 30"),
            'technicians': q("select id,full_name,username from users where active=1 and role in ('technician','field') order by full_name"),
            'whatsapp_drafts': q('''select d.*,u.full_name recipient_name from whatsapp_drafts d
                left join users u on u.id=d.recipient_user_id ''' + (
                    "order by d.id desc limit 100" if user.get('role') in {'admin', 'manager'}
                    else "where d.recipient_user_id=%d order by d.id desc limit 100" % int(user['id'])
                ))
        }
    def project_workspace(self, connection, project_id):
        project = connection.execute('''
            select p.*,c.name client_name,u.full_name manager_name
            from projects p left join clients c on c.id=p.client_id left join users u on u.id=p.manager_id
            where p.id=?
        ''', (project_id,)).fetchone()
        if not project:
            return None
        q = lambda sql: [dict(row) for row in connection.execute(sql, (project_id,)).fetchall()]
        return {
            'project': dict(project),
            'work_orders': q('select w.*,u.full_name assignee_name from work_orders w left join users u on u.id=w.assigned_to where w.project_id=? order by w.id desc'),
            'samples': q('select * from samples where project_id=? order by id desc'),
            'tests': q('select t.test_no,t.status,t.completed_at,tc.name_ar,tc.standard,s.sample_no from tests t join samples s on s.id=t.sample_id join test_catalog tc on tc.id=t.catalog_id where s.project_id=? order by t.id desc'),
            'results': q('select t.test_no,tc.name_ar,td.field_name,coalesce(td.value_num,td.value_text) value,td.unit from test_data td join tests t on t.id=td.test_id join samples s on s.id=t.sample_id join test_catalog tc on tc.id=t.catalog_id where s.project_id=? order by t.id desc,td.id'),
            'reports': q('select r.report_no,r.status,r.issued_at,t.test_no,tc.name_ar from reports r join tests t on t.id=r.test_id join samples s on s.id=t.sample_id join test_catalog tc on tc.id=t.catalog_id where s.project_id=? order by r.id desc'),
            'field_visits': q('select id,license_no,status,location,created_at from field_visits where project_id=? order by id desc')
        }

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        static_files = {
            '/': ('index.html', 'text/html; charset=utf-8'),
            '/style.css': ('style.css', 'text/css; charset=utf-8'),
            '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
            '/runtime-config.js': ('runtime-config.js', 'application/javascript; charset=utf-8'),
            '/sw.js': ('sw.js', 'application/javascript; charset=utf-8'),
            '/manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json; charset=utf-8'),
            '/logo.jpg': ('logo.jpg', 'image/jpeg'),
            '/i18n.js': ('i18n.js', 'application/javascript; charset=utf-8'),
            '/company-profile.pdf': ('company-profile.pdf', 'application/pdf')
        }
        if path in static_files:
            return self.static(*static_files[path])

        user = user_from(self)
        if path.startswith('/api/') and not user:
            return self.send_json({'error': 'غير مسجل الدخول'}, 401)

        connection = db()
        try:
            if path == '/api/events':
                if not self.require_permission(user, 'dashboard'):
                    return
                return self.stream_events()

            if path == '/api/users':
                if not self.require_permission(user, 'users'):
                    return
                rows = connection.execute('select id,username,full_name,role,phone,active,created_at from users order by id desc').fetchall()
                return self.send_json([dict(row) for row in rows])

            if path == '/api/whatsapp/drafts':
                if not self.require_permission(user, 'dashboard'):
                    return
                if user.get('role') in {'admin', 'manager'}:
                    rows = connection.execute('''select d.*,u.full_name recipient_name from whatsapp_drafts d
                        left join users u on u.id=d.recipient_user_id order by d.id desc limit 100''').fetchall()
                else:
                    rows = connection.execute('''select d.*,u.full_name recipient_name from whatsapp_drafts d
                        left join users u on u.id=d.recipient_user_id
                        where d.recipient_user_id=? order by d.id desc limit 100''', (user['id'],)).fetchall()
                return self.send_json([dict(row) for row in rows])

            if path == '/api/catalog':
                rows = [dict(row) for row in connection.execute('''select tc.*, cr.astm_attachment_id,cr.worksheet_attachment_id,cr.results_attachment_id
                    from test_catalog tc left join catalog_resources cr on cr.test_catalog_id=tc.id where tc.active=1 order by tc.category,tc.name_ar''').fetchall()]
                return self.send_json(rows)

            if path == '/api/attachments':
                entity_type = str(parse_qs(parsed.query).get('entity_type', [''])[0])
                entity_id = parse_optional_int(parse_qs(parsed.query).get('entity_id', [''])[0])
                if not record_allowed(user, entity_type):
                    return self.send_json({'error': 'غير مصرح'}, 403)
                return self.send_json([dict(row) for row in connection.execute(
                    'select id,original_name,created_at from record_attachments where entity_type=? and entity_id=? order by id desc',
                    (entity_type, entity_id)).fetchall()])

            if path.startswith('/api/attachments/files/'):
                attachment_id = parse_optional_int(path.rsplit('/', 1)[-1])
                row = connection.execute('select a.*,u.role from record_attachments a left join users u on u.id=a.uploaded_by where a.id=?', (attachment_id,)).fetchone()
                if not row or not record_allowed(user, row['entity_type']):
                    return self.send_json({'error': 'الملف غير موجود أو غير مصرح'}, 404)
                target = os.path.join(RECORD_UPLOADS, row['stored_name'])
                if not os.path.isfile(target):
                    return self.send_json({'error': 'الملف غير موجود'}, 404)
                extension = os.path.splitext(row['stored_name'])[1].lower()
                types = {'.pdf':'application/pdf','.doc':'application/msword','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','.xls':'application/vnd.ms-excel','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
                return self.static(os.path.relpath(target, BASE), types.get(extension, 'application/octet-stream'))

            if path == '/api/quality':
                if not self.require_permission(user, 'quality'):
                    return
                return self.send_json({
                    'documents': [dict(row) for row in connection.execute('select * from quality_documents order by category,code,id desc').fetchall()],
                    'proficiency': [dict(row) for row in connection.execute('select * from proficiency_tests order by participation_date desc,id desc').fetchall()],
                    'staff': [dict(row) for row in connection.execute('select * from quality_staff order by active desc,full_name').fetchall()]
                })

            if path.startswith('/api/quality/files/'):
                if not self.require_permission(user, 'quality'):
                    return
                filename = os.path.basename(path)
                target = os.path.join(QUALITY_UPLOADS, filename)
                if not filename or not os.path.isfile(target):
                    return self.send_json({'error': 'الملف غير موجود'}, 404)
                content_type = 'application/pdf' if filename.endswith('.pdf') else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' if filename.endswith('.docx') else 'application/msword'
                return self.static(os.path.relpath(target, BASE), content_type)

            if path == '/api/dashboard':
                if not self.require_permission(user, 'dashboard'):
                    return
                return self.send_json(self.dashboard(connection, user))

            if path == '/api/projects':
                if not self.require_permission(user, 'projects'):
                    return
                return self.send_json(self.project_rows(connection))

            if path.startswith('/api/projects/') and path.endswith('/workspace'):
                if not self.require_permission(user, 'projects'):
                    return
                project_id = int(path.split('/')[3])
                result = self.project_workspace(connection, project_id)
                return self.send_json(result or {'error': 'المشروع غير موجود'}, 200 if result else 404)

            if path == '/api/work-orders':
                if not self.require_permission(user, 'projects'):
                    return
                query = parse_qs(parsed.query)
                project_id = query.get('project_id', [None])[0]
                sql = '''
                    select w.*,p.code project_code,p.name project_name,u.full_name assignee_name
                    from work_orders w join projects p on p.id=w.project_id
                    left join users u on u.id=w.assigned_to
                '''
                params = ()
                if project_id:
                    sql += ' where w.project_id=?'
                    params = (int(project_id),)
                sql += ' order by w.id desc'
                return self.send_json([dict(row) for row in connection.execute(sql, params).fetchall()])

            if path == '/api/balady/permit':
                if not self.require_permission(user, 'field'):
                    return
                license_no = parse_qs(parsed.query).get('license', [''])[0].strip()
                if not license_no:
                    return self.send_json({'error': 'رقم الرخصة مطلوب'}, 400)
                try:
                    return self.send_json(fetch_balady_permit(license_no))
                except LookupError as error:
                    return self.send_json({'error': str(error)}, 404)
                except PermissionError as error:
                    return self.send_json({'error': str(error)}, 502)
                except RuntimeError as error:
                    return self.send_json({'error': str(error)}, 503)

            if path == '/api/field/search':
                if not self.require_permission(user, 'field'):
                    return
                license_no = parse_qs(parsed.query).get('license', [''])[0].strip()
                rows = connection.execute('select * from field_visits where license_no=? order by id desc limit 20', (license_no,)).fetchall() if license_no else []
                return self.send_json([dict(row) for row in rows])

            if path == '/api/field/recent':
                if not self.require_permission(user, 'field'):
                    return
                rows = connection.execute('''
                    select f.*,u.full_name,p.code project_code,s.sample_no
                    from field_visits f
                    left join users u on u.id=f.created_by
                    left join projects p on p.id=f.project_id
                    left join samples s on s.id=f.sample_id
                    order by f.id desc limit 30
                ''').fetchall()
                return self.send_json([dict(row) for row in rows])

            if path == '/api/sync/queue':
                if not self.require_permission(user, 'sync'):
                    return
                rows = connection.execute("select id,entity,entity_id,operation,status,attempts,created_at,last_error from sync_queue order by id desc limit 200").fetchall()
                return self.send_json([dict(row) for row in rows])

            if path.startswith('/api/report/'):
                if not self.require_permission(user, 'reports'):
                    return
                test_id = int(path.rsplit('/', 1)[1])
                row = connection.execute('''
                    select r.report_no,r.issued_at,r.status,t.*,s.sample_no,s.material,tc.code,tc.name_ar,tc.standard,tc.category,pr.mdd,pr.omc
                    from reports r
                    join tests t on t.id=r.test_id
                    join samples s on s.id=t.sample_id
                    join test_catalog tc on tc.id=t.catalog_id
                    left join proctor_results pr on pr.test_id=t.id
                    where t.id=?
                ''', (test_id,)).fetchone()
                if not row:
                    return self.send_json({'error': 'التقرير غير موجود'}, 404)
                data = {'inputs': {}, 'results': {}}
                for value in connection.execute('select section,field_name,value_text,value_num,unit,seq from test_data where test_id=? order by section,seq,id', (test_id,)):
                    data[value['section']][value['field_name']] = value['value_num'] if value['value_num'] is not None else value['value_text']
                lab = connection.execute("select value from settings where key='lab_name'").fetchone()
                report = dict(row)
                report['data'] = data
                report['lab_name'] = lab['value'] if lab and lab['value'] else 'مختبر أساس'
                return self.send_json(report)

            return self.send_json({'error': 'غير موجود'}, 404)
        except (ValueError, sqlite3.Error) as error:
            return self.send_json({'error': str(error)}, 400)
        finally:
            connection.close()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/auth/login':
            try:
                data = self.body()
            except json.JSONDecodeError:
                return self.send_json({'ok': False, 'error': 'invalid_request'}, 400)
            connection = db()
            username = str(data.get('username', '')).strip()
            user, token, error = password_login(connection, username, str(data.get('password', '')))
            if error:
                connection.close()
                return self.send_json({'ok': False, 'error': error}, 401)
            phone = str(user['phone'] or '').strip()
            connection.close()
            return self.send_json({'ok': True, 'token': token, 'user': {'username': user['username'], 'name': user['full_name'], 'role': user['role'], 'phone': phone}}, extra_headers={'Set-Cookie': 'LIMS_SESSION=' + token + '; Path=/; HttpOnly; Secure; SameSite=Strict'})

        if path == '/api/auth/verify':
            return self.send_json({'ok': False, 'error': 'otp_disabled'}, 410)
            '''
            try:
                data = self.body()
            except json.JSONDecodeError:
                return self.send_json({'ok': False, 'error': 'invalid_request'}, 400)
            connection = db()
            username = str(data.get('username', '')).strip()
            code = str(data.get('otp', '')).strip()
            user = connection.execute('select * from users where (username=? or phone=?) and active=1', (username, username)).fetchone()
            phone = str(user['phone'] or '').strip() if user else ''
            if not user or not valid_e164(phone) or not (code.isdigit() and len(code) == 6):
                connection.close()
                return self.send_json({'ok': False, 'error': 'invalid_otp'}, 401)
            if not twilio_verify_ready():
                connection.close()
                return self.send_json({'ok': False, 'error': 'otp_provider_not_configured'}, 503)
            try:
                result = twilio_verify_request('VerificationCheck', {'To': phone, 'Code': code})
            except (urllib.error.HTTPError, urllib.error.URLError):
                audit(connection, user['id'], 'OTP_FAILED', 'user', user['id'], 'Twilio Verify check failed')
                connection.commit()
                connection.close()
                return self.send_json({'ok': False, 'error': 'otp_provider_error'}, 502)
            if result.get('status') != 'approved':
                connection.close()
                return self.send_json({'ok': False, 'error': 'invalid_otp'}, 401)
            token = secrets.token_urlsafe(32)
            SESSIONS[token] = dict(user)
            audit(connection, user['id'], 'OTP_VERIFIED', 'user', user['id'], 'Twilio Verify approved')
            connection.commit()
            connection.close()
            return self.send_json(
                {'ok': True, 'token': token, 'user': {'username': user['username'], 'name': user['full_name'], 'role': user['role'], 'phone': phone}},
                extra_headers={'Set-Cookie': 'LIMS_SESSION=' + token + '; Path=/; HttpOnly; Secure; SameSite=Strict'}
            )
            '''

        if path == '/api/login':
            return self.send_json({'error': 'استخدم /api/auth/login لتسجيل الدخول بكلمة المرور'}, 410)

        if path == '/api/logout':
            authorization = self.headers.get('Authorization', '')
            if authorization.startswith('Bearer '):
                SESSIONS.pop(authorization[7:], None)
            for item in self.headers.get('Cookie', '').split(';'):
                item = item.strip()
                if item.startswith('LIMS_SESSION='):
                    SESSIONS.pop(item.split('=', 1)[1], None)
            return self.send_json({'ok': True})

        user = user_from(self)
        if not user:
            return self.send_json({'error': 'غير مسجل الدخول'}, 401)
        try:
            data = self.body()
        except json.JSONDecodeError:
            return self.send_json({'error': 'بيانات JSON غير صالحة'}, 400)

        connection = db()
        try:
            if path == '/api/auth/change-password':
                current_password = str(data.get('current_password') or '')
                new_password = str(data.get('new_password') or '')
                confirm_password = str(data.get('confirm_password') or '')
                account = connection.execute('select id,password_hash from users where id=? and active=1', (user['id'],)).fetchone()
                if not account or not checkpw(current_password, account['password_hash']):
                    return self.send_json({'error': 'كلمة المرور الحالية غير صحيحة'}, 400)
                if len(new_password) < 12:
                    return self.send_json({'error': 'كلمة المرور الجديدة يجب ألا تقل عن 12 حرفاً'}, 400)
                if new_password != confirm_password:
                    return self.send_json({'error': 'تأكيد كلمة المرور غير مطابق'}, 400)
                connection.execute('update users set password_hash=? where id=?', (hp(new_password), user['id']))
                audit(connection, user['id'], 'تغيير كلمة المرور الذاتية', 'user', user['id'], user['username'])
                connection.commit()
                return self.send_json({'ok': True})

            if path == '/api/users/create':
                if not self.require_permission(user, 'users'):
                    return
                username = str(data.get('username', '')).strip()
                full_name = str(data.get('full_name', '')).strip()
                password = str(data.get('password', ''))
                role = data.get('role', 'technician')
                phone = str(data.get('phone', '')).strip()
                if not username or not full_name or len(password) < 12 or role not in ROLE_PERMS:
                    return self.send_json({'error': 'بيانات المستخدم غير مكتملة أو كلمة المرور أقل من 12 حرفاً'}, 400)
                if phone and not valid_e164(phone):
                    return self.send_json({'error': 'رقم الجوال يجب أن يكون بصيغة دولية مثل +9665XXXXXXXX'}, 400)
                if phone_in_use(connection, phone):
                    return self.send_json({'error': 'رقم الجوال مسجل لمستخدم آخر'}, 409)
                connection.execute('insert into users(username,password_hash,full_name,role,phone,active) values(?,?,?,?,?,1)', (username, hp(password), full_name, role, phone))
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                audit(connection, user['id'], 'إضافة مستخدم', 'user', entity_id, username)
                # Do not enqueue passwords or their hashes: the queue contains only
                # the account metadata needed by an authorized sync consumer.
                queue_sync(connection, 'user', entity_id, 'create', {
                    'username': username, 'full_name': full_name, 'role': role,
                    'phone': phone, 'active': True
                })
                connection.commit()
                publish_event('user', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id, 'sync': 'queued'})

            if path == '/api/users/update':
                if not self.require_permission(user, 'users'):
                    return
                entity_id = int(data.get('id'))
                target = connection.execute('select * from users where id=?', (entity_id,)).fetchone()
                if not target:
                    return self.send_json({'error': 'المستخدم غير موجود'}, 404)
                role = data.get('role', target['role'])
                active = 1 if data.get('active', bool(target['active'])) else 0
                password = str(data.get('password', ''))
                phone = str(data.get('phone', target['phone'] or '')).strip()
                if role not in ROLE_PERMS or (entity_id == user['id'] and active == 0):
                    return self.send_json({'error': 'تعديل المستخدم غير صالح'}, 400)
                if password and len(password) < 12:
                    return self.send_json({'error': 'كلمة المرور يجب ألا تقل عن 12 حرفاً'}, 400)
                if phone and not valid_e164(phone):
                    return self.send_json({'error': 'رقم الجوال يجب أن يكون بصيغة دولية مثل +9665XXXXXXXX'}, 400)
                if phone_in_use(connection, phone, entity_id):
                    return self.send_json({'error': 'رقم الجوال مسجل لمستخدم آخر'}, 409)
                connection.execute('update users set full_name=?,role=?,phone=?,active=? where id=?', (data.get('full_name', target['full_name']), role, phone, active, entity_id))
                if password:
                    connection.execute('update users set password_hash=? where id=?', (hp(password), entity_id))
                audit(connection, user['id'], 'تعديل مستخدم', 'user', entity_id, target['username'])
                queue_sync(connection, 'user', entity_id, 'update', {
                    'username': target['username'],
                    'full_name': str(data.get('full_name', target['full_name'])).strip(),
                    'role': role, 'phone': phone, 'active': bool(active)
                })
                connection.commit()
                publish_event('user', 'update', entity_id)
                return self.send_json({'ok': True, 'id': entity_id, 'sync': 'queued'})

            if path.startswith('/api/whatsapp/drafts/') and path.endswith('/ready'):
                if not require_role(user, {'manager'}):
                    return self.send_json({'error': 'مراجعة مسودات واتساب للمدير فقط'}, 403)
                draft_id = int(path.split('/')[4])
                updated = connection.execute(
                    "update whatsapp_drafts set status='ready',reviewed_at=CURRENT_TIMESTAMP where id=? and status='draft'", (draft_id,)
                ).rowcount
                if not updated:
                    return self.send_json({'error': 'المسودة غير موجودة أو تمت مراجعتها'}, 404)
                audit(connection, user['id'], 'مراجعة مسودة واتساب', 'whatsapp_draft', draft_id, 'Ready for manual send')
                connection.commit()
                publish_event('whatsapp_draft', 'ready', draft_id)
                return self.send_json({'ok': True, 'id': draft_id})

            if path == '/api/tests/assign':
                if not require_role(user, {'manager'}):
                    return self.send_json({'error': 'إسناد الاختبار للمدير فقط'}, 403)
                test_id = int(data.get('test_id'))
                technician_id = int(data.get('technician_id'))
                test = connection.execute('''select t.*,s.sample_no,tc.code,tc.name_ar
                    from tests t join samples s on s.id=t.sample_id join test_catalog tc on tc.id=t.catalog_id where t.id=?''', (test_id,)).fetchone()
                technician = connection.execute("select id,full_name,role from users where id=? and active=1 and role in ('technician','field')", (technician_id,)).fetchone()
                if not test or not technician:
                    return self.send_json({'error': 'الاختبار أو الفني غير موجود'}, 404)
                connection.execute("update tests set technician_id=?,status='مسند' where id=?", (technician_id, test_id))
                message = ('🔬 تكليف اختبار — مختبر أساس\n'
                    'الفني: {name}\nالعينة: {sample}\nالاختبار: {test_name} ({code})\n'
                    'رقم الاختبار: {test_no}\nيرجى تنفيذ الاختبار وتسجيل النتيجة في النظام.').format(
                        name=technician['full_name'], sample=test['sample_no'], test_name=test['name_ar'],
                        code=test['code'], test_no=test['test_no'])
                create_whatsapp_draft(connection, user['id'], 'test_assignment', test_id, message, technician_id)
                queue_sync(connection, 'test', test_id, 'assign', {'technician_id': technician_id, 'status': 'مسند'})
                audit(connection, user['id'], 'إسناد اختبار لفني', 'test', test_id, test['test_no'] + ' → ' + technician['full_name'])
                connection.commit()
                publish_event('test', 'assign', test_id)
                return self.send_json({'ok': True, 'id': test_id})

            if path == '/api/projects':
                if not self.require_permission(user, 'projects'):
                    return
                name = str(data.get('name', '')).strip()
                if not name:
                    return self.send_json({'error': 'اسم المشروع مطلوب'}, 400)
                progress = max(0, min(100, int(data.get('progress', 0) or 0)))
                status = data.get('status', 'مخطط')
                if status not in PROJECT_STATUSES:
                    return self.send_json({'error': 'حالة المشروع غير صالحة'}, 400)
                code = nextno(connection, 'PR-', 'projects')
                values = (
                    code, name, parse_optional_int(data.get('client_id')), data.get('location'), status,
                    normalize_priority(data.get('priority')), data.get('description'), data.get('contractor_name'),
                    data.get('consultant_name'), data.get('start_date') or None, data.get('due_date') or None,
                    progress, parse_optional_int(data.get('manager_id'))
                )
                connection.execute('''
                    insert into projects(code,name,client_id,location,status,priority,description,contractor_name,consultant_name,start_date,due_date,progress,manager_id,updated_at)
                    values(?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ''', values)
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                queue_sync(connection, 'project', entity_id, 'create', {'code': code, 'name': name, 'status': status})
                audit(connection, user['id'], 'إضافة مشروع', 'project', entity_id, code + ' - ' + name)
                connection.commit()
                publish_event('project', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id, 'code': code})

            if path == '/api/projects/update':
                if not self.require_permission(user, 'projects'):
                    return
                entity_id = int(data.get('id'))
                project = connection.execute('select * from projects where id=?', (entity_id,)).fetchone()
                if not project:
                    return self.send_json({'error': 'المشروع غير موجود'}, 404)
                name = str(data.get('name', project['name'])).strip()
                if not name:
                    return self.send_json({'error': 'اسم المشروع مطلوب'}, 400)
                progress = max(0, min(100, int(data.get('progress', project['progress']) or 0)))
                connection.execute('''
                    update projects set name=?,client_id=?,location=?,priority=?,description=?,contractor_name=?,consultant_name=?,start_date=?,due_date=?,progress=?,manager_id=?,updated_at=CURRENT_TIMESTAMP
                    where id=?
                ''', (
                    name, parse_optional_int(data.get('client_id', project['client_id'])), data.get('location', project['location']),
                    normalize_priority(data.get('priority', project['priority'])), data.get('description', project['description']),
                    data.get('contractor_name', project['contractor_name']), data.get('consultant_name', project['consultant_name']),
                    data.get('start_date', project['start_date']) or None, data.get('due_date', project['due_date']) or None,
                    progress, parse_optional_int(data.get('manager_id', project['manager_id'])), entity_id
                ))
                queue_sync(connection, 'project', entity_id, 'update', {'code': project['code'], 'name': name, 'progress': progress})
                audit(connection, user['id'], 'تعديل مشروع', 'project', entity_id, project['code'])
                connection.commit()
                publish_event('project', 'update', entity_id)
                return self.send_json({'ok': True})

            if path == '/api/projects/status':
                if not self.require_permission(user, 'projects'):
                    return
                entity_id = int(data.get('id'))
                status = data.get('status')
                if status not in PROJECT_STATUSES:
                    return self.send_json({'error': 'حالة المشروع غير صالحة'}, 400)
                project = connection.execute('select * from projects where id=?', (entity_id,)).fetchone()
                if not project:
                    return self.send_json({'error': 'المشروع غير موجود'}, 404)
                if status == 'قيد المراجعة' and not require_role(user, {'manager'}):
                    return self.send_json({'error': 'إحالة المشروع للمراجعة للمدير فقط'}, 403)
                if status == 'معتمد' and user.get('role') != 'admin':
                    return self.send_json({'error': 'اعتماد المشروع لمدير النظام فقط'}, 403)
                if status == 'قيد المراجعة':
                    connection.execute('update projects set status=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP where id=?', (status, user['id'], entity_id))
                elif status == 'معتمد':
                    connection.execute('update projects set status=?,approved_by=?,approved_at=CURRENT_TIMESTAMP,progress=100,updated_at=CURRENT_TIMESTAMP where id=?', (status, user['id'], entity_id))
                else:
                    connection.execute('update projects set status=?,updated_at=CURRENT_TIMESTAMP where id=?', (status, entity_id))
                queue_sync(connection, 'project', entity_id, 'status', {'code': project['code'], 'status': status})
                audit(connection, user['id'], 'تغيير حالة مشروع', 'project', entity_id, project['code'] + ' → ' + status)
                connection.commit()
                publish_event('project', 'status', entity_id)
                return self.send_json({'ok': True})

            if path == '/api/work-orders':
                if not self.require_permission(user, 'projects'):
                    return
                project_id = parse_optional_int(data.get('project_id'))
                title = str(data.get('title', '')).strip()
                if not project_id or not title:
                    return self.send_json({'error': 'المشروع وعنوان أمر العمل مطلوبان'}, 400)
                if not connection.execute('select id from projects where id=?', (project_id,)).fetchone():
                    return self.send_json({'error': 'المشروع غير موجود'}, 404)
                status = data.get('status', 'مفتوح')
                if status not in WORK_ORDER_STATUSES:
                    return self.send_json({'error': 'حالة أمر العمل غير صالحة'}, 400)
                order_no = nextno(connection, 'WO-', 'work_orders')
                connection.execute('''
                    insert into work_orders(order_no,project_id,title,description,status,priority,scheduled_date,due_date,assigned_to,created_by,updated_at)
                    values(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ''', (
                    order_no, project_id, title, data.get('description'), status, normalize_priority(data.get('priority')),
                    data.get('scheduled_date') or None, data.get('due_date') or None, parse_optional_int(data.get('assigned_to')), user['id']
                ))
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                queue_sync(connection, 'work_order', entity_id, 'create', {'order_no': order_no, 'project_id': project_id, 'title': title, 'status': status})
                assignee = connection.execute('select full_name from users where id=?', (parse_optional_int(data.get('assigned_to')),)).fetchone()
                create_whatsapp_draft(
                    connection, user['id'], 'work_order', entity_id,
                    '📋 أمر عمل جديد — مختبر أساس\nرقم: {no}\nالعنوان: {title}\nالحالة: {status}\nالمكلّف: {assignee}\nيرجى متابعة الأمر من النظام.'.format(
                        no=order_no, title=title, status=status, assignee=assignee['full_name'] if assignee else 'غير محدد'
                    ), parse_optional_int(data.get('assigned_to'))
                )
                audit(connection, user['id'], 'إضافة أمر عمل', 'work_order', entity_id, order_no + ' - ' + title)
                connection.commit()
                publish_event('work_order', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id, 'order_no': order_no})

            if path == '/api/field/status':
                if not self.require_permission(user, 'field'):
                    return
                entity_id = int(data.get('id'))
                status = data.get('status')
                if status not in FIELD_STATUSES:
                    return self.send_json({'error': 'حالة غير صالحة'}, 400)
                if status == 'قيد المراجعة' and not require_role(user, {'manager'}):
                    return self.send_json({'error': 'المراجعة للمدير فقط'}, 403)
                if status == 'معتمدة' and not require_role(user, {'manager'}):
                    return self.send_json({'error': 'الاعتماد للمدير فقط'}, 403)
                if status == 'قيد المراجعة':
                    connection.execute('update field_visits set status=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP where id=?', (status, user['id'], entity_id))
                elif status == 'معتمدة':
                    connection.execute('update field_visits set status=?,approved_by=?,approved_at=CURRENT_TIMESTAMP where id=?', (status, user['id'], entity_id))
                else:
                    connection.execute('update field_visits set status=? where id=?', (status, entity_id))
                audit(connection, user['id'], 'تغيير حالة زيارة ميدانية', 'field_visit', entity_id, status)
                connection.commit()
                publish_event('field_visit', 'status', entity_id)
                return self.send_json({'ok': True})

            if path == '/api/field/visits':
                if not self.require_permission(user, 'field'):
                    return
                license_no = str(data.get('license_no', '')).strip()
                status = data.get('status', 'مسودة')
                if not license_no or status not in FIELD_STATUSES:
                    return self.send_json({'error': 'بيانات الزيارة غير مكتملة'}, 400)
                connection.execute('''
                    insert into field_visits(license_no,contractor_name,project_name,sector_name,layer_no,location,latitude,longitude,tests_json,notes,status,created_by,project_id,sample_id,balady_permit_no,balady_municipality,balady_permit_type,balady_permit_status,balady_reference_url)
                    values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    license_no, data.get('contractor_name'), data.get('project_name'), data.get('sector_name'), data.get('layer_no'),
                    data.get('location'), data.get('latitude'), data.get('longitude'), json.dumps(data.get('tests', []), ensure_ascii=False),
                    data.get('notes'), status, user['id'], parse_optional_int(data.get('project_id')), parse_optional_int(data.get('sample_id')),
                    data.get('balady_permit_no'), data.get('balady_municipality'), data.get('balady_permit_type'), data.get('balady_permit_status'), data.get('balady_reference_url')
                ))
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                queue_sync(connection, 'field_visit', entity_id, 'create', {'license_no': license_no, 'status': status})
                create_whatsapp_draft(connection, user['id'], 'field_visit', entity_id,
                    '📍 زيارة ميدانية جديدة — مختبر أساس\nالرخصة: {license}\nالموقع: {location}\nالحالة: {status}\nتم إنشاء مسودة للتواصل الداخلي.'.format(
                        license=license_no, location=data.get('location') or 'غير محدد', status=status))
                audit(connection, user['id'], 'إضافة زيارة ميدانية', 'field_visit', entity_id, license_no)
                connection.commit()
                publish_event('field_visit', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id})

            if path == '/api/clients':
                if not self.require_permission(user, 'clients'):
                    return
                name = str(data.get('name', '')).strip()
                if not name:
                    return self.send_json({'error': 'اسم العميل مطلوب'}, 400)
                connection.execute('insert into clients(name,phone,email) values(?,?,?)', (name, data.get('phone'), data.get('email')))
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                audit(connection, user['id'], 'إضافة عميل', 'client', entity_id, name)
                connection.commit()
                publish_event('client', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id})

            if path == '/api/samples':
                if not self.require_permission(user, 'samples'):
                    return
                sample_no = str(data.get('sample_no', '')).strip()
                material = str(data.get('material', '')).strip()
                if not sample_no or not material or not data.get('received_date'):
                    return self.send_json({'error': 'بيانات العينة غير مكتملة'}, 400)
                connection.execute('insert into samples(sample_no,project_id,material,source,received_date,notes) values(?,?,?,?,?,?)', (
                    sample_no, parse_optional_int(data.get('project_id')), material, data.get('source'), data.get('received_date'), data.get('notes')
                ))
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                planned = connection.execute('select id,code from test_catalog where category=? and active=1 order by name_ar', (material,)).fetchall()
                for catalog_item in planned:
                    test_no = nextno(connection, 'TST-', 'tests')
                    connection.execute('''
                        insert into tests(test_no,sample_id,catalog_id,status,technician_id)
                        values(?,?,?,?,?)
                    ''', (test_no, entity_id, catalog_item['id'], 'مخطط', None))
                queue_sync(connection, 'sample', entity_id, 'create', {'sample_no': sample_no, 'project_id': data.get('project_id')})
                create_whatsapp_draft(
                    connection, user['id'], 'sample', entity_id,
                    '🧪 عينة جديدة — مختبر أساس\nالعينة: {sample}\nالمادة: {material}\nخطة الاختبارات الرسمية: {count} اختباراً\nتم إنشاء المسودة للمراجعة قبل النشر في مجتمع الشركة.'.format(
                        sample=sample_no, material=material, count=len(planned)
                    )
                )
                audit(connection, user['id'], 'إضافة عينة وخطة اختبارات تلقائية', 'sample', entity_id, sample_no + ' (' + str(len(planned)) + ' اختباراً)')
                connection.commit()
                publish_event('sample', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id, 'planned_count': len(planned)})

            if path == '/api/equipment':
                if not self.require_permission(user, 'equipment'):
                    return
                name = str(data.get('name', '')).strip()
                if not name:
                    return self.send_json({'error': 'اسم الجهاز مطلوب'}, 400)
                connection.execute('insert into equipment(name,serial_no,manufacturer,model,last_calibration,next_calibration,certificate_no,notes) values(?,?,?,?,?,?,?,?)', (
                    name, data.get('serial_no'), data.get('manufacturer'), data.get('model'), data.get('last_calibration'),
                    data.get('next_calibration'), data.get('certificate_no'), data.get('notes')
                ))
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                audit(connection, user['id'], 'إضافة جهاز', 'equipment', entity_id, name)
                connection.commit()
                publish_event('equipment', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id})

            if path == '/api/quality/documents':
                if not self.require_permission(user, 'quality'):
                    return
                category = str(data.get('category', '')).strip()
                code = str(data.get('code', '')).strip()
                title = str(data.get('title', '')).strip()
                if category not in {'procedure', 'worksheet', 'admin_form'} or not code or not title:
                    return self.send_json({'error': 'بيانات وثيقة الجودة غير مكتملة'}, 400)
                document_ref = str(data.get('document_ref') or '').strip()
                file_data = str(data.get('file_base64') or '')
                file_name = os.path.basename(str(data.get('file_name') or ''))
                if file_data:
                    extension = os.path.splitext(file_name)[1].lower()
                    if extension not in {'.pdf', '.doc', '.docx'} or len(file_data) > 35_000_000:
                        return self.send_json({'error': 'يسمح فقط بملفات PDF أو Word حتى 25MB'}, 400)
                    try:
                        content = base64.b64decode(file_data, validate=True)
                    except ValueError:
                        return self.send_json({'error': 'ملف مرفوع غير صالح'}, 400)
                    if len(content) > 25 * 1024 * 1024:
                        return self.send_json({'error': 'حجم الملف يتجاوز 25MB'}, 400)
                    os.makedirs(QUALITY_UPLOADS, exist_ok=True)
                    stored_name = secrets.token_urlsafe(18) + extension
                    with open(os.path.join(QUALITY_UPLOADS, stored_name), 'wb') as uploaded:
                        uploaded.write(content)
                    document_ref = '/api/quality/files/' + stored_name
                connection.execute('insert into quality_documents(category,code,title,revision,status,owner,document_ref,notes) values(?,?,?,?,?,?,?,?)', (category, code, title, data.get('revision'), data.get('status') or 'ساري', data.get('owner'), document_ref, data.get('notes')))
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                audit(connection, user['id'], 'إضافة وثيقة جودة', 'quality_document', entity_id, code)
                connection.commit(); publish_event('quality_document', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id})

            if path == '/api/attachments':
                try:
                    stored_name = save_record_file(connection, user, data)
                except PermissionError as error:
                    return self.send_json({'error': str(error)}, 403)
                except ValueError as error:
                    return self.send_json({'error': str(error)}, 400)
                attachment_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                audit(connection, user['id'], 'رفع مرفق سجل', data.get('entity_type'), data.get('entity_id'), data.get('file_name'))
                connection.commit()
                return self.send_json({'ok': True, 'id': attachment_id, 'ref': '/api/attachments/files/' + str(attachment_id), 'stored_name': stored_name})

            if path == '/api/catalog/resources':
                if not self.require_permission(user, 'quality'):
                    return
                catalog_id = parse_optional_int(data.get('catalog_id'))
                resource_type = str(data.get('resource_type') or '')
                columns = {'astm': 'astm_attachment_id', 'worksheet': 'worksheet_attachment_id', 'results': 'results_attachment_id'}
                if not catalog_id or resource_type not in columns or not connection.execute('select id from test_catalog where id=?', (catalog_id,)).fetchone():
                    return self.send_json({'error': 'بيانات الاختبار أو نوع المورد غير صحيح'}, 400)
                upload_data = dict(data); upload_data['entity_type'] = 'catalog'; upload_data['entity_id'] = catalog_id
                try:
                    save_record_file(connection, user, upload_data)
                except (PermissionError, ValueError) as error:
                    return self.send_json({'error': str(error)}, 400)
                attachment_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                column = columns[resource_type]
                connection.execute('insert into catalog_resources(test_catalog_id,' + column + ') values(?,?) on conflict(test_catalog_id) do update set ' + column + '=excluded.' + column + ',updated_at=CURRENT_TIMESTAMP', (catalog_id, attachment_id))
                audit(connection, user['id'], 'ربط مورد اختبار', 'test_catalog', catalog_id, resource_type)
                connection.commit(); publish_event('catalog_resource', 'update', catalog_id)
                return self.send_json({'ok': True, 'id': attachment_id, 'ref': '/api/attachments/files/' + str(attachment_id)})

            if path == '/api/bulk/import':
                entity_type = str(data.get('entity_type') or '')
                rows = data.get('rows') or []
                required_perm = {'clients':'clients','projects':'projects','work_orders':'projects','samples':'samples'}.get(entity_type)
                if not required_perm or not self.require_permission(user, required_perm):
                    return
                if not isinstance(rows, list) or not rows or len(rows) > 500:
                    return self.send_json({'error': 'ارفع من 1 إلى 500 صف في كل مرة'}, 400)
                imported, skipped = 0, []
                for number, row in enumerate(rows, 2):
                    if not isinstance(row, dict):
                        skipped.append(number); continue
                    try:
                        if entity_type == 'clients':
                            name = str(row.get('الاسم') or row.get('name') or '').strip()
                            if not name: raise ValueError()
                            connection.execute('insert into clients(name,phone,email) values(?,?,?)', (name, row.get('الهاتف') or row.get('phone'), row.get('البريد') or row.get('email')))
                        elif entity_type == 'projects':
                            name = str(row.get('اسم المشروع') or row.get('name') or '').strip()
                            if not name: raise ValueError()
                            client_name = str(row.get('العميل') or row.get('client') or '').strip()
                            client_id = None
                            if client_name:
                                client = connection.execute('select id from clients where name=?', (client_name,)).fetchone()
                                if not client:
                                    connection.execute('insert into clients(name) values(?)', (client_name,)); client_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                                else: client_id = client['id']
                            connection.execute('insert into projects(code,name,client_id,location,priority,description,start_date,due_date,progress,updated_at) values(?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)',
                                (nextno(connection,'PR-','projects'), name, client_id, row.get('الموقع') or row.get('location'), normalize_priority(row.get('الأولوية') or row.get('priority')), row.get('الوصف') or row.get('description'), row.get('البداية') or row.get('start_date'), row.get('الاستحقاق') or row.get('due_date'), int(row.get('التقدم') or row.get('progress') or 0)))
                        elif entity_type == 'work_orders':
                            title = str(row.get('أمر العمل') or row.get('title') or '').strip(); project_id = parse_optional_int(row.get('معرف المشروع') or row.get('project_id'))
                            if not title or not project_id or not connection.execute('select id from projects where id=?', (project_id,)).fetchone(): raise ValueError()
                            connection.execute('insert into work_orders(order_no,project_id,title,description,priority,scheduled_date,due_date,created_by,updated_at) values(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)',
                                (nextno(connection,'WO-','work_orders'),project_id,title,row.get('الوصف') or row.get('description'),normalize_priority(row.get('الأولوية') or row.get('priority')),row.get('الموعد') or row.get('scheduled_date'),row.get('الاستحقاق') or row.get('due_date'),user['id']))
                        else:
                            material = str(row.get('المادة') or row.get('material') or '').strip(); project_id = parse_optional_int(row.get('معرف المشروع') or row.get('project_id'))
                            if not material: raise ValueError()
                            connection.execute('insert into samples(sample_no,project_id,material,source,received_date,notes) values(?,?,?,?,?,?)',
                                (nextno(connection,'SMP-','samples'),project_id,material,row.get('المصدر') or row.get('source'),row.get('تاريخ الاستلام') or row.get('received_date') or time.strftime('%Y-%m-%d'),row.get('ملاحظات') or row.get('notes')))
                        imported += 1
                    except (ValueError, TypeError, sqlite3.Error):
                        skipped.append(number)
                audit(connection, user['id'], 'استيراد جماعي', entity_type, 0, str(imported) + ' صف')
                connection.commit(); publish_event(entity_type, 'bulk_import', 0)
                return self.send_json({'ok': True, 'imported': imported, 'skipped': skipped})

            if path == '/api/quality/files':
                if not self.require_permission(user, 'quality'):
                    return
                file_data = str(data.get('file_base64') or '')
                file_name = os.path.basename(str(data.get('file_name') or ''))
                extension = os.path.splitext(file_name)[1].lower()
                if not file_data or extension not in {'.pdf', '.doc', '.docx'} or len(file_data) > 35_000_000:
                    return self.send_json({'error': 'يسمح فقط بملفات PDF أو Word حتى 25MB'}, 400)
                try:
                    content = base64.b64decode(file_data, validate=True)
                except ValueError:
                    return self.send_json({'error': 'ملف مرفوع غير صالح'}, 400)
                if len(content) > 25 * 1024 * 1024:
                    return self.send_json({'error': 'حجم الملف يتجاوز 25MB'}, 400)
                os.makedirs(QUALITY_UPLOADS, exist_ok=True)
                stored_name = secrets.token_urlsafe(18) + extension
                with open(os.path.join(QUALITY_UPLOADS, stored_name), 'wb') as uploaded:
                    uploaded.write(content)
                audit(connection, user['id'], 'رفع ملف جودة', 'quality_file', 0, file_name)
                connection.commit()
                return self.send_json({'ok': True, 'ref': '/api/quality/files/' + stored_name})

            if path == '/api/quality/proficiency':
                if not self.require_permission(user, 'quality'):
                    return
                test_name = str(data.get('test_name', '')).strip()
                if not test_name:
                    return self.send_json({'error': 'اسم اختبار الكفاءة مطلوب'}, 400)
                connection.execute('insert into proficiency_tests(test_name,material,standard,provider,participation_date,result,z_score,report_ref,notes) values(?,?,?,?,?,?,?,?,?)', (test_name, data.get('material'), data.get('standard'), data.get('provider'), data.get('participation_date'), data.get('result'), data.get('z_score'), data.get('report_ref'), data.get('notes')))
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                audit(connection, user['id'], 'إضافة مشاركة اختبار كفاءة', 'proficiency_test', entity_id, test_name)
                connection.commit(); publish_event('proficiency_test', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id})

            if path == '/api/quality/staff':
                if not self.require_permission(user, 'quality'):
                    return
                full_name = str(data.get('full_name', '')).strip()
                if not full_name:
                    return self.send_json({'error': 'اسم الموظف مطلوب'}, 400)
                connection.execute('insert into quality_staff(full_name,job_title,specialty,experience_years,qualification_ref,cv_ref,active,notes) values(?,?,?,?,?,?,?,?)', (full_name, data.get('job_title'), data.get('specialty'), data.get('experience_years'), data.get('qualification_ref'), data.get('cv_ref'), 1 if data.get('active', True) else 0, data.get('notes')))
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                audit(connection, user['id'], 'إضافة سجل موظف للجودة', 'quality_staff', entity_id, full_name)
                connection.commit(); publish_event('quality_staff', 'create', entity_id)
                return self.send_json({'ok': True, 'id': entity_id})

            if path == '/api/tests/proctor':
                if not self.require_permission(user, 'tests'):
                    return
                return self.create_proctor(connection, user, data)

            if path == '/api/tests/generic':
                if not self.require_permission(user, 'tests'):
                    return
                catalog = connection.execute('select * from test_catalog where id=?', (data.get('catalog_id'),)).fetchone()
                if not catalog:
                    return self.send_json({'error': 'الاختبار غير موجود'}, 404)
                sample_id = parse_optional_int(data.get('sample_id'))
                if not sample_id:
                    return self.send_json({'error': 'معرف العينة مطلوب'}, 400)
                test_no = data.get('test_no') or nextno(connection, 'TST-', 'tests')
                connection.execute('''
                    insert into tests(test_no,sample_id,catalog_id,status,technician_id,started_at,completed_at)
                    values(?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ''', (test_no, sample_id, catalog['id'], data.get('status', 'مكتمل'), user['id'], data.get('started_at')))
                test_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                for section, values in (('inputs', data.get('inputs', {})), ('results', data.get('results', {}))):
                    if isinstance(values, dict):
                        for key, value in values.items():
                            if value in (None, ''):
                                continue
                            try:
                                numeric_value, text_value = float(value), None
                            except (TypeError, ValueError):
                                numeric_value, text_value = None, str(value)
                            connection.execute('insert into test_data(test_id,section,field_name,value_text,value_num,unit) values(?,?,?,?,?,?)', (
                                test_id, section, key, text_value, numeric_value, data.get('units', {}).get(key)
                            ))
                report_no = nextno(connection, 'AST-R-', 'reports')
                connection.execute('insert into reports(report_no,test_id,status) values(?,?,?)', (report_no, test_id, 'مسودة'))
                queue_sync(connection, 'test', test_id, 'create', {'test_no': test_no, 'catalog': catalog['code']})
                create_whatsapp_draft(connection, user['id'], 'test', test_id,
                    '🔬 تم تسجيل نتيجة اختبار كمسودة — مختبر أساس\nرقم الاختبار: {no}\nالاختبار: {name}\nالتقرير: {report}\nلا تُنشر النتائج خارج النظام قبل الاعتماد.'.format(no=test_no, name=catalog['name_ar'], report=report_no))
                audit(connection, user['id'], 'إضافة اختبار', 'test', test_id, test_no + ' - ' + catalog['name_ar'])
                connection.commit()
                publish_event('test', 'create', test_id)
                return self.send_json({'ok': True, 'test_id': test_id, 'report_no': report_no})

            if path == '/api/reports/status':
                if not self.require_permission(user, 'reports'):
                    return
                report_id = int(data.get('id'))
                status = data.get('status')
                if status not in {'مسودة', 'قيد المراجعة', 'معتمد', 'مرفوض'}:
                    return self.send_json({'error': 'حالة التقرير غير صالحة'}, 400)
                if status == 'قيد المراجعة' and not require_role(user, {'manager'}):
                    return self.send_json({'error': 'المراجعة للمدير فقط'}, 403)
                if status == 'معتمد' and user.get('role') != 'admin':
                    return self.send_json({'error': 'الاعتماد لمدير النظام فقط'}, 403)
                if status == 'معتمد':
                    connection.execute('update reports set status=?,approved_by=?,issued_at=CURRENT_TIMESTAMP where id=?', (status, user['id'], report_id))
                else:
                    connection.execute('update reports set status=? where id=?', (status, report_id))
                report = connection.execute('select report_no from reports where id=?', (report_id,)).fetchone()
                create_whatsapp_draft(connection, user['id'], 'report', report_id,
                    '📄 تحديث تقرير — مختبر أساس\nرقم التقرير: {no}\nالحالة: {status}\nهذه مسودة للمراجعة قبل مشاركتها في مجتمع الشركة.'.format(no=report['report_no'], status=status))
                audit(connection, user['id'], 'تغيير حالة تقرير', 'report', report_id, status)
                connection.commit()
                publish_event('report', 'status', report_id)
                return self.send_json({'ok': True})

            return self.send_json({'error': 'مسار غير معروف'}, 404)
        except sqlite3.IntegrityError as error:
            connection.rollback()
            return self.send_json({'error': 'بيانات مكررة أو مرجع غير صحيح: ' + str(error)}, 400)
        except (TypeError, ValueError, sqlite3.Error) as error:
            connection.rollback()
            return self.send_json({'error': str(error)}, 400)
        finally:
            connection.close()

    def create_proctor(self, connection, user, data):
        catalog = connection.execute('select id from test_catalog where code=?', (data.get('standard_code'),)).fetchone()
        sample_id = parse_optional_int(data.get('sample_id'))
        points = data.get('points', [])
        if not catalog or not sample_id or len(points) < 2:
            return self.send_json({'error': 'بيانات اختبار البروكتور غير مكتملة'}, 400)
        test_no = data.get('test_no') or nextno(connection, 'TST-', 'tests')
        connection.execute('''
            insert into tests(test_no,sample_id,catalog_id,status,technician_id,started_at,completed_at)
            values(?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ''', (test_no, sample_id, catalog['id'], 'مكتمل', user['id'], data.get('started_at')))
        test_id = connection.execute('select last_insert_rowid()').fetchone()[0]
        for index, point in enumerate(points, 1):
            connection.execute('insert into proctor_points(test_id,point_no,moisture,mold_soil_wet,wet_density,dry_density) values(?,?,?,?,?,?)', (
                test_id, index, point['moisture'], point['mold_soil_wet'], point.get('wet_density'), point.get('dry_density')
            ))
        connection.execute('insert into proctor_results(test_id,mdd,omc) values(?,?,?)', (test_id, data['mdd'], data['omc']))
        report_no = nextno(connection, 'AST-R-', 'reports')
        connection.execute('insert into reports(report_no,test_id,status) values(?,?,?)', (report_no, test_id, 'مسودة'))
        queue_sync(connection, 'test', test_id, 'create', {'test_no': test_no, 'catalog': data.get('standard_code')})
        create_whatsapp_draft(connection, user['id'], 'test', test_id,
            '🔬 تم تسجيل اختبار بروكتور كمسودة — مختبر أساس\nرقم الاختبار: {no}\nالتقرير: {report}\nلا تُنشر النتائج خارج النظام قبل الاعتماد.'.format(no=test_no, report=report_no))
        audit(connection, user['id'], 'إضافة اختبار', 'test', test_id, test_no + ' - ' + data.get('standard_code'))
        connection.commit()
        publish_event('test', 'create', test_id)
        return self.send_json({'ok': True, 'test_id': test_id, 'report_no': report_no})


if __name__ == '__main__':
    init()
    print('LIMS مختبر أساس: http://127.0.0.1:' + str(PORT))
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()
