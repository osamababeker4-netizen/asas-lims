#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import io
import hashlib
import hmac
import json
import os
import queue
import secrets
import re
import sqlite3
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
APP_VERSION = '10.1.0-expanded-field'
DB = os.environ.get('LIMS_DB_PATH', os.path.join(BASE, 'lims.db'))
OFFICIAL_CATALOG = os.path.join(BASE, 'official_test_catalog.json')
QUALITY_UPLOADS = os.environ.get('LIMS_QUALITY_UPLOADS', os.path.join(BASE, 'uploads', 'quality'))
RECORD_UPLOADS = os.environ.get('LIMS_RECORD_UPLOADS', os.path.join(BASE, 'uploads', 'records'))
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
SESSION_TTL_SECONDS = int(os.environ.get('LIMS_SESSION_TTL_SECONDS', str(12 * 60 * 60)))
MAX_JSON_BODY_BYTES = int(os.environ.get('LIMS_MAX_JSON_BODY_BYTES', str(40 * 1024 * 1024)))
LOGIN_WINDOW_SECONDS = int(os.environ.get('LIMS_LOGIN_WINDOW_SECONDS', '900'))
LOGIN_MAX_ATTEMPTS = int(os.environ.get('LIMS_LOGIN_MAX_ATTEMPTS', '5'))
LOGIN_ATTEMPTS = {}
LOGIN_ATTEMPTS_LOCK = threading.Lock()
BACKUP_DIR = os.environ.get('LIMS_BACKUP_DIR', os.path.join(BASE, 'backups'))

PROJECT_STATUSES = {'مخطط', 'نشط', 'موقوف', 'قيد المراجعة', 'معتمد', 'مكتمل', 'مفتوح'}
WORK_ORDER_STATUSES = {'مفتوح', 'قيد التنفيذ', 'بانتظار المراجعة', 'موقوف', 'مكتمل'}
FIELD_STATUSES = {'مسودة', 'مرسلة', 'قيد المراجعة', 'معتمدة', 'مرفوضة'}
PRIORITIES = {'منخفضة', 'متوسطة', 'عالية', 'حرجة'}

ROLE_PERMS = {
    'admin': {'*'},
    'general_manager': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports', 'equipment', 'quality', 'audit', 'trash', 'users', 'sync', 'settings'},
    'technical_manager': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports', 'equipment', 'audit', 'sync', 'settings'},
    'laboratory_manager': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports', 'equipment', 'audit', 'sync', 'settings'},
    # مدير الجودة مخوّل كمدير شامل: إضافة وتعديل واعتماد وإدارة المستخدمين والإعدادات.
    'quality_manager': {'*'},
    'quality_officer': {'dashboard', 'quality'},
    'calibration_officer': {'dashboard', 'quality'},
    'document_controller': {'dashboard', 'quality'},
    'manager': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports', 'equipment', 'quality', 'audit', 'trash', 'users', 'sync', 'settings'},
    'quality': {'dashboard', 'quality'},
    'technician': {'dashboard', 'field', 'clients', 'projects', 'samples', 'tests', 'catalog', 'reports'},
    'field': {'dashboard', 'field', 'clients', 'projects', 'samples'}
}


def db():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA busy_timeout=5000')
    connection.execute('PRAGMA journal_mode=WAL')
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
    if not user:
        return False
    permissions = ROLE_PERMS.get(user.get('role'), set())
    return user.get('role') == 'admin' or '*' in permissions or user.get('role') in roles


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
    'catalog': ('test_catalog', 'catalog'), 'field_visit': ('field_visits', 'field')
}

SMART_SECTIONS = {
    'dashboard': ('dashboard', 'dashboard'), 'projects': ('project', 'projects'),
    'workOrders': ('work_order', 'projects'), 'field': ('field_visit', 'field'),
    'clients': ('client', 'clients'), 'samples': ('sample', 'samples'),
    'tests': ('test', 'tests'), 'catalog': ('catalog', 'catalog'),
    'reports': ('report', 'reports'), 'communications': ('communications', 'settings'),
    'quality': ('quality', 'quality'), 'company': ('company', 'dashboard'),
    'technicalLibrary': ('technical_library', 'quality'),
    'companyVault': ('company_vault', 'users'),
    'audit': ('audit', 'audit'), 'trash': ('trash', 'trash'), 'users': ('user', 'users'), 'settings': ('settings', 'settings'),
    'equipment': ('equipment', 'equipment')
}

SMART_FILE_TYPES = {
    '.pdf':'PDF', '.doc':'Word', '.docx':'Word', '.xls':'Excel', '.xlsx':'Excel', '.csv':'بيانات CSV',
    '.txt':'نص', '.jpg':'صورة', '.jpeg':'صورة', '.png':'صورة', '.webp':'صورة', '.heic':'صورة',
    '.zip':'حزمة مضغوطة', '.dwg':'رسم هندسي', '.dxf':'رسم هندسي'
}

MATERIAL_GROUP_KEYWORDS = {
    'خرسانة': ('خرسانة','خرساني','concrete','cement','مكعب','cube','cylinder','اسطوانة','slump','هبوط','compressive','compression','c39','c143','c31','c192','c42','c78','c496'),
    'تربة': ('تربة','تربه','soil','subgrade','ردم','fill','proctor','atterberg','حدود اتربرج','cbr','moisture content','محتوى الرطوبة','sand cone','الكثافة الحقلية','d1557','d698','d4318','d1883','d2216','d6938','d2487'),
    'أسفلت': ('أسفلت','اسفلت','asphalt','bitumen','bituminous','marshall','marshal','مارشال','gmm','gmb','binder','رابط اسفلتي','اختراق','penetration','d6927','d2041','d2726','d979','d5','d5444','d6307','d2172'),
    'الحقل وNDT': ('الحقل','ميداني','field','ndt','non destructive','nondestructive','rcdetector','rc detector','rebar detector','cover meter','rebar corrosion','half cell','ultrasonic','upvt','u910','schmidt','hammer','road profiler','roughness','iri','d6132','d7091','c597')
}


def smart_searchable_text(original_name, content, extension):
    chunks = [str(original_name or '')]
    if extension in {'.txt', '.csv'}:
        chunks.append(content[:2 * 1024 * 1024].decode('utf-8', errors='ignore'))
    elif extension in {'.docx', '.xlsx'}:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                for item in archive.infolist():
                    if item.file_size > 2 * 1024 * 1024 or not item.filename.lower().endswith('.xml'):
                        continue
                    chunks.append(archive.read(item).decode('utf-8', errors='ignore'))
                    if sum(len(chunk) for chunk in chunks) > 3 * 1024 * 1024:
                        break
        except (zipfile.BadZipFile, OSError):
            pass
    else:
        chunks.append(content[:2 * 1024 * 1024].decode('latin-1', errors='ignore'))
    return normalized_excel_header(' '.join(chunks))


def detect_material_group(original_name, content):
    extension = os.path.splitext(original_name)[1].lower()
    text = smart_searchable_text(original_name, content, extension)
    scores = {group: sum(1 for keyword in keywords if normalized_excel_header(keyword) in text)
              for group, keywords in MATERIAL_GROUP_KEYWORDS.items()}
    best_group, best_score = max(scores.items(), key=lambda item: item[1])
    return best_group if best_score else 'أخرى'


def smart_section_allowed(user, section):
    item = SMART_SECTIONS.get(section)
    return bool(item and has_perm(user, item[1]))


def detect_smart_target(connection, section, file_name):
    entity_type = SMART_SECTIONS[section][0]
    definitions = {
        'projects': ('projects', "code || ' ' || name"),
        'workOrders': ('work_orders', "order_no || ' ' || title"),
        'clients': ('clients', 'name'), 'samples': ('samples', 'sample_no'),
        'tests': ('tests', 'test_no'), 'reports': ('reports', 'report_no'),
        'equipment': ('equipment', "coalesce(equipment_code,'') || ' ' || coalesce(serial_no,'') || ' ' || name"),
        'users': ('users', "username || ' ' || full_name"), 'catalog': ('test_catalog', "code || ' ' || name_ar")
    }
    if section not in definitions:
        return entity_type, 0, 'مصنف داخل القسم'
    table, expression = definitions[section]
    haystack = normalized_excel_header(os.path.splitext(file_name)[0])
    best = None
    for row in connection.execute('select id,' + expression + ' as search_value from ' + table).fetchall():
        value = normalized_excel_header(row['search_value'])
        tokens = [part for part in re.split(r'\s+', value) if len(part) >= 4]
        haystack_tokens = set(re.split(r'\s+', haystack))
        score = max(([len(part) for part in tokens if part in haystack_tokens] or [0]))
        if value and value in haystack:
            score = max(score, len(value) + 20)
        if score >= 4 and (not best or score > best[0]):
            best = (score, row['id'])
    return entity_type, (best[1] if best else 0), ('مرتبط تلقائيًا' if best else 'يحتاج مراجعة')


def store_smart_file(connection, user, section, original_name, content):
    original_name = os.path.basename(str(original_name or '')).strip()
    extension = os.path.splitext(original_name)[1].lower()
    if not original_name or extension not in SMART_FILE_TYPES:
        raise ValueError('نوع الملف غير مدعوم: ' + (extension or 'بدون امتداد'))
    if len(content) > 25 * 1024 * 1024:
        raise ValueError('حجم الملف يتجاوز 25MB: ' + original_name)
    entity_type, entity_id, status = detect_smart_target(connection, section, original_name)
    material_group = detect_material_group(original_name, content)
    os.makedirs(RECORD_UPLOADS, exist_ok=True)
    stored_name = secrets.token_urlsafe(18) + extension
    with open(os.path.join(RECORD_UPLOADS, stored_name), 'wb') as uploaded:
        uploaded.write(content)
    connection.execute('''insert into record_attachments(entity_type,entity_id,original_name,stored_name,uploaded_by,section,file_category,material_group,classification_status,mime_type)
        values(?,?,?,?,?,?,?,?,?,?)''', (entity_type, entity_id, original_name, stored_name, user['id'], section,
        SMART_FILE_TYPES[extension], material_group, status, extension.lstrip('.')))
    return {'id': connection.execute('select last_insert_rowid()').fetchone()[0], 'name': original_name,
            'category': SMART_FILE_TYPES[extension], 'material_group': material_group, 'status': status, 'entity_id': entity_id}


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
    allowed = {'.pdf', '.doc', '.docx', '.xls', '.xlsx'}
    if entity_type == 'field_visit':
        allowed |= {'.jpg', '.jpeg', '.png', '.webp', '.heic'}
    if not encoded or extension not in allowed:
        raise ValueError('نوع الملف غير مدعوم لهذا السجل')
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
            ('phone', 'phone TEXT'),
            ('avatar_data_url', 'avatar_data_url TEXT')
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
        ],
        'whatsapp_drafts': [('draft_name', 'draft_name TEXT')],
        'equipment': [
            ('equipment_code', 'equipment_code TEXT'), ('range_text', 'range_text TEXT'),
            ('section', 'section TEXT'), ('verification_status', 'verification_status TEXT'),
            ('maintenance_status', 'maintenance_status TEXT'), ('calibrated_to', 'calibrated_to TEXT'),
            ('service_date', 'service_date TEXT')
        ],
        'record_attachments': [
            ('section', 'section TEXT'), ('file_category', 'file_category TEXT'),
            ('material_group', "material_group TEXT NOT NULL DEFAULT 'أخرى'"),
            ('classification_status', 'classification_status TEXT'), ('mime_type', 'mime_type TEXT')
        ]
    }
    for table, columns in additions.items():
        existing = {row['name'] for row in connection.execute('pragma table_info(' + table + ')')}
        for name, definition in columns:
            if name not in existing:
                connection.execute('alter table ' + table + ' add column ' + definition)
    connection.execute('''create table if not exists upload_receipts(
        upload_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        section TEXT NOT NULL,
        response_json TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    connection.execute('create index if not exists idx_upload_receipts_created on upload_receipts(created_at)')
    connection.execute('create index if not exists idx_projects_due_date on projects(due_date)')
    connection.execute(
        "update settings set value=? where key='whatsapp_group_url' and (value is null or value='' or value=?)",
        ('https://chat.whatsapp.com/LxqH7L6GorGEhMfUTYthgG?s=sh&p=a&mlu=4&ilr=4',
         'https://chat.whatsapp.com/CWalJYwXsocKtYiqsJsMSh')
    )


def refresh_user_sessions(user_id, **changes):
    """Keep identity fields current across every open session for a user."""
    for session in SESSIONS.values():
        account = session.get('user', session)
        if int(account.get('id', 0)) == int(user_id):
            account.update(changes)


def init():
    os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
    connection = db()
    with open(os.path.join(BASE, 'schema.sql'), encoding='utf-8') as schema:
        connection.executescript(schema.read())
    migrate_schema(connection)
    with open(OFFICIAL_CATALOG, encoding='utf-8') as catalog_file:
        official_catalog = json.load(catalog_file)
    for category, entries in official_catalog.items():
        for entry in entries:
            code, name_ar = entry[0], entry[1]
            name_en = entry[2] if len(entry) > 2 else name_ar
            standard = entry[3] if len(entry) > 3 else 'ASTM ' + code
            connection.execute('''
                insert into test_catalog(code,name_ar,name_en,category,standard,version,active)
                values(?,?,?,?,?,'معتمد',1)
                on conflict(code) do update set name_ar=excluded.name_ar,name_en=excluded.name_en,
                    category=excluded.category,standard=excluded.standard,version=excluded.version,active=1
            ''', (code, name_ar, name_en, category, standard))
    if connection.execute('select count(*) from users').fetchone()[0] == 0:
        password = os.environ.get('LIMS_BOOTSTRAP_PASSWORD')
        if not password:
            connection.close()
            raise RuntimeError('يتطلب أول تشغيل تعيين LIMS_BOOTSTRAP_PASSWORD إلى كلمة مرور غير فارغة.')
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


def rows_for_json(connection, sql, params=()):
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def insert_snapshot_row(connection, table, row):
    if not row:
        return
    columns = list(row.keys())
    connection.execute(
        'insert or replace into {}({}) values({})'.format(
            table, ','.join(columns), ','.join('?' for _ in columns)
        ),
        tuple(row[column] for column in columns)
    )


def snapshot_deleted_record(connection, entity, entity_id):
    """Capture one important operational record and everything needed to restore it."""
    payload = {'entity_type': entity, 'original_id': entity_id, 'attachments': []}
    if entity == 'project':
        payload['record'] = rowdict(connection.execute('select * from projects where id=?', (entity_id,)).fetchone())
        payload['work_orders'] = rows_for_json(connection, 'select * from work_orders where project_id=? order by id', (entity_id,))
        payload['samples'] = [snapshot_deleted_record(connection, 'sample', row['id']) for row in connection.execute('select id from samples where project_id=? order by id', (entity_id,))]
        work_ids = [row['id'] for row in payload['work_orders']]
        clauses = ["(entity_type='project' and entity_id=?)"]
        params = [entity_id]
        if work_ids:
            marks = ','.join('?' for _ in work_ids); clauses.append("(entity_type='work_order' and entity_id in (" + marks + "))"); params += work_ids
        payload['attachments'] = rows_for_json(connection, 'select * from record_attachments where ' + ' or '.join(clauses), params)
        payload['linked_field_visits'] = [row['id'] for row in connection.execute('select id from field_visits where project_id=?', (entity_id,))]
        payload['linked_quotations'] = [row['id'] for row in connection.execute('select id from quotations where project_id=?', (entity_id,))]
        payload['linked_contracts'] = [row['id'] for row in connection.execute('select id from contracts where project_id=?', (entity_id,))]
        payload['linked_complaints'] = [row['id'] for row in connection.execute('select id from customer_complaints where project_id=?', (entity_id,))]
    elif entity == 'work_order':
        payload['record'] = rowdict(connection.execute('select * from work_orders where id=?', (entity_id,)).fetchone())
        payload['attachments'] = rows_for_json(connection, "select * from record_attachments where entity_type='work_order' and entity_id=?", (entity_id,))
    elif entity == 'equipment':
        payload['record'] = rowdict(connection.execute('select * from equipment where id=?', (entity_id,)).fetchone())
        payload['calibration_records'] = rows_for_json(connection, 'select * from calibration_records where equipment_id=? order by id', (entity_id,))
        payload['maintenance_records'] = rows_for_json(connection, 'select * from maintenance_records where equipment_id=? order by id', (entity_id,))
        payload['attachments'] = rows_for_json(connection, "select * from record_attachments where entity_type='equipment' and entity_id=?", (entity_id,))
    elif entity == 'quality_document':
        payload['record'] = rowdict(connection.execute('select * from quality_documents where id=?', (entity_id,)).fetchone())
        payload['attachments'] = rows_for_json(connection, "select * from record_attachments where entity_type='quality_document' and entity_id=?", (entity_id,))
    elif entity == 'client':
        payload['record'] = rowdict(connection.execute('select * from clients where id=?', (entity_id,)).fetchone())
        payload['linked_projects'] = [row['id'] for row in connection.execute('select id from projects where client_id=?', (entity_id,))]
        payload['linked_quotations'] = [row['id'] for row in connection.execute('select id from quotations where client_id=?', (entity_id,))]
        payload['linked_contracts'] = [row['id'] for row in connection.execute('select id from contracts where client_id=?', (entity_id,))]
        payload['linked_complaints'] = [row['id'] for row in connection.execute('select id from customer_complaints where client_id=?', (entity_id,))]
        payload['attachments'] = rows_for_json(connection, "select * from record_attachments where entity_type='client' and entity_id=?", (entity_id,))
    elif entity == 'sample':
        payload['record'] = rowdict(connection.execute('select * from samples where id=?', (entity_id,)).fetchone())
        payload['tests'] = rows_for_json(connection, 'select * from tests where sample_id=? order by id', (entity_id,))
        test_ids = [row['id'] for row in payload['tests']]
        if test_ids:
            marks = ','.join('?' for _ in test_ids)
            payload['reports'] = rows_for_json(connection, 'select * from reports where test_id in (' + marks + ') order by id', test_ids)
            payload['test_data'] = rows_for_json(connection, 'select * from test_data where test_id in (' + marks + ') order by id', test_ids)
            payload['proctor_points'] = rows_for_json(connection, 'select * from proctor_points where test_id in (' + marks + ') order by id', test_ids)
            payload['proctor_results'] = rows_for_json(connection, 'select * from proctor_results where test_id in (' + marks + ')', test_ids)
            report_ids = [row['id'] for row in payload['reports']]
            clauses = ["(entity_type='sample' and entity_id=?)", "(entity_type='test' and entity_id in (" + marks + "))"]
            params = [entity_id] + test_ids
            if report_ids:
                report_marks = ','.join('?' for _ in report_ids)
                clauses.append("(entity_type='report' and entity_id in (" + report_marks + "))")
                params += report_ids
            payload['attachments'] = rows_for_json(connection, 'select * from record_attachments where ' + ' or '.join(clauses), params)
        payload['linked_field_visits'] = [row['id'] for row in connection.execute('select id from field_visits where sample_id=?', (entity_id,))]
    elif entity == 'test':
        payload['record'] = rowdict(connection.execute('select * from tests where id=?', (entity_id,)).fetchone())
        payload['reports'] = rows_for_json(connection, 'select * from reports where test_id=? order by id', (entity_id,))
        payload['test_data'] = rows_for_json(connection, 'select * from test_data where test_id=? order by id', (entity_id,))
        payload['proctor_points'] = rows_for_json(connection, 'select * from proctor_points where test_id=? order by id', (entity_id,))
        payload['proctor_results'] = rows_for_json(connection, 'select * from proctor_results where test_id=?', (entity_id,))
        report_ids = [row['id'] for row in payload['reports']]
        clauses = ["(entity_type='test' and entity_id=?)"]
        params = [entity_id]
        if report_ids:
            marks = ','.join('?' for _ in report_ids)
            clauses.append("(entity_type='report' and entity_id in (" + marks + "))")
            params += report_ids
        payload['attachments'] = rows_for_json(connection, 'select * from record_attachments where ' + ' or '.join(clauses), params)
    elif entity == 'report':
        payload['record'] = rowdict(connection.execute('select * from reports where id=?', (entity_id,)).fetchone())
        payload['attachments'] = rows_for_json(connection, "select * from record_attachments where entity_type='report' and entity_id=?", (entity_id,))
    return payload


def restore_deleted_record(connection, payload):
    entity = payload['entity_type']
    if entity == 'project':
        insert_snapshot_row(connection, 'projects', payload['record'])
        for row in payload.get('work_orders', []): insert_snapshot_row(connection, 'work_orders', row)
        for sample in payload.get('samples', []): restore_deleted_record(connection, sample)
        ids = payload.get('linked_field_visits', [])
        if ids:
            connection.execute('update field_visits set project_id=? where id in (' + ','.join('?' for _ in ids) + ')', [payload['original_id']] + ids)
        for table, key in (('quotations','linked_quotations'),('contracts','linked_contracts'),('customer_complaints','linked_complaints')):
            ids = payload.get(key, [])
            if ids:
                connection.execute('update ' + table + ' set project_id=? where id in (' + ','.join('?' for _ in ids) + ')', [payload['original_id']] + ids)
    elif entity == 'work_order':
        insert_snapshot_row(connection, 'work_orders', payload['record'])
    elif entity == 'equipment':
        insert_snapshot_row(connection, 'equipment', payload['record'])
        for table in ('calibration_records', 'maintenance_records'):
            for row in payload.get(table, []): insert_snapshot_row(connection, table, row)
    elif entity == 'quality_document':
        insert_snapshot_row(connection, 'quality_documents', payload['record'])
    elif entity == 'client':
        insert_snapshot_row(connection, 'clients', payload['record'])
        for table, key in (('projects','linked_projects'),('quotations','linked_quotations'),('contracts','linked_contracts'),('customer_complaints','linked_complaints')):
            ids = payload.get(key, [])
            if ids:
                connection.execute('update ' + table + ' set client_id=? where id in (' + ','.join('?' for _ in ids) + ')', [payload['original_id']] + ids)
    elif entity == 'sample':
        insert_snapshot_row(connection, 'samples', payload['record'])
        for row in payload.get('tests', []): insert_snapshot_row(connection, 'tests', row)
        for table in ('test_data', 'proctor_points', 'proctor_results', 'reports'):
            for row in payload.get(table, []): insert_snapshot_row(connection, table, row)
        ids = payload.get('linked_field_visits', [])
        if ids:
            connection.execute('update field_visits set sample_id=? where id in (' + ','.join('?' for _ in ids) + ')', [payload['original_id']] + ids)
    elif entity == 'test':
        insert_snapshot_row(connection, 'tests', payload['record'])
        for table in ('test_data', 'proctor_points', 'proctor_results', 'reports'):
            for row in payload.get(table, []): insert_snapshot_row(connection, table, row)
    elif entity == 'report':
        insert_snapshot_row(connection, 'reports', payload['record'])
    for row in payload.get('attachments', []):
        insert_snapshot_row(connection, 'record_attachments', row)


def user_from(handler):
    token = None
    authorization = handler.headers.get('Authorization', '')
    if authorization.startswith('Bearer '):
        token = authorization[7:]
    if not token:
        for item in handler.headers.get('Cookie', '').split(';'):
            item = item.strip()
            if item.startswith('LIMS_SESSION='):
                token = item.split('=', 1)[1]
                break
    session = SESSIONS.get(token) if token else None
    if not session:
        return None
    if 'expires_at' not in session:  # Compatibility for sessions created before this release.
        return session
    if session['expires_at'] <= time.time():
        SESSIONS.pop(token, None)
        return None
    return session['user']


def create_session(user):
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {'user': dict(user), 'expires_at': time.time() + SESSION_TTL_SECONDS}
    return token


def login_attempt_key(handler, login_id):
    forwarded = handler.headers.get('X-Forwarded-For', '').split(',', 1)[0].strip()
    client = forwarded or (handler.client_address[0] if handler.client_address else 'unknown')
    return client + '|' + str(login_id).strip().lower()


def login_rate_status(key):
    now = time.monotonic()
    with LOGIN_ATTEMPTS_LOCK:
        attempts = [stamp for stamp in LOGIN_ATTEMPTS.get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
        LOGIN_ATTEMPTS[key] = attempts
        if len(attempts) < LOGIN_MAX_ATTEMPTS:
            return 0
        return max(1, int(LOGIN_WINDOW_SECONDS - (now - attempts[0])))


def record_login_failure(key):
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.setdefault(key, []).append(time.monotonic())


def clear_login_failures(key):
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.pop(key, None)


def twilio_verify_ready():
    return all(os.environ.get(key, '').strip() for key in (
        'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_VERIFY_SERVICE_SID'
    ))



def telegram_ready():
    return bool(os.environ.get('TELEGRAM_BOT_TOKEN', '').strip() and os.environ.get('TELEGRAM_CHAT_ID', '').strip())


def telegram_send_text(text):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat_id:
        raise RuntimeError('telegram_not_configured')
    payload = urllib.parse.urlencode({
        'chat_id': chat_id,
        'text': str(text or '')[:4096],
        'disable_web_page_preview': 'true'
    }).encode('utf-8')
    request = urllib.request.Request(
        'https://api.telegram.org/bot{}/sendMessage'.format(token),
        data=payload,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST'
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.loads(response.read().decode('utf-8'))
    if not result.get('ok'):
        raise RuntimeError('telegram_send_failed')
    return result.get('result', {})



def telegram_send_photo(photo_data_url, caption=''):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat_id:
        raise RuntimeError('telegram_not_configured')
    value = str(photo_data_url or '')
    if not value.startswith('data:image/') or ';base64,' not in value:
        raise ValueError('telegram_invalid_photo')
    header, encoded = value.split(';base64,', 1)
    mime = header[5:].lower()
    if mime not in ('image/jpeg', 'image/png', 'image/webp'):
        raise ValueError('telegram_invalid_photo')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('telegram_invalid_photo')
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('telegram_photo_too_large')
    extension = 'jpg' if mime == 'image/jpeg' else mime.split('/', 1)[1]
    filename = 'asas-field-photo.' + extension
    boundary = '----ASAS' + secrets.token_hex(12)
    chunks = []
    def add_field(name, value):
        chunks.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"\r\n\r\n' + str(value) + '\r\n').encode('utf-8'))
    add_field('chat_id', chat_id)
    if caption:
        add_field('caption', str(caption)[:1024])
    chunks.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="photo"; filename="' + filename + '"\r\nContent-Type: ' + mime + '\r\n\r\n').encode('utf-8'))
    chunks.append(raw)
    chunks.append(b'\r\n')
    chunks.append(('--' + boundary + '--\r\n').encode('utf-8'))
    request = urllib.request.Request(
        'https://api.telegram.org/bot{}/sendPhoto'.format(token),
        data=b''.join(chunks),
        headers={'Content-Type': 'multipart/form-data; boundary=' + boundary},
        method='POST'
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode('utf-8'))
    if not result.get('ok'):
        raise RuntimeError('telegram_photo_send_failed')
    return result.get('result', {})



def telegram_send_media_group(photo_data_urls, caption=''):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat_id:
        raise RuntimeError('telegram_not_configured')
    photos = list(photo_data_urls or [])[:10]
    if not photos:
        return []
    boundary = '----ASAS' + secrets.token_hex(12)
    chunks = []
    media = []
    for index, value in enumerate(photos):
        value = str(value or '')
        if not value.startswith('data:image/') or ';base64,' not in value:
            raise ValueError('telegram_invalid_photo')
        header, encoded = value.split(';base64,', 1)
        mime = header[5:].lower()
        if mime not in ('image/jpeg', 'image/png', 'image/webp'):
            raise ValueError('telegram_invalid_photo')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('telegram_invalid_photo')
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError('telegram_photo_too_large')
        field = 'photo{}'.format(index)
        item = {'type': 'photo', 'media': 'attach://' + field}
        if index == 0 and caption:
            item['caption'] = str(caption)[:1024]
        media.append(item)
        extension = 'jpg' if mime == 'image/jpeg' else mime.split('/', 1)[1]
        chunks.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + field + '"; filename="asas-field-' + str(index + 1) + '.' + extension + '"\r\nContent-Type: ' + mime + '\r\n\r\n').encode('utf-8'))
        chunks.append(raw)
        chunks.append(b'\r\n')
    def add_field(name, value):
        chunks.insert(0, ('--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"\r\n\r\n' + str(value) + '\r\n').encode('utf-8'))
    add_field('media', json.dumps(media, ensure_ascii=False))
    add_field('chat_id', chat_id)
    chunks.append(('--' + boundary + '--\r\n').encode('utf-8'))
    request = urllib.request.Request(
        'https://api.telegram.org/bot{}/sendMediaGroup'.format(token),
        data=b''.join(chunks),
        headers={'Content-Type': 'multipart/form-data; boundary=' + boundary},
        method='POST'
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode('utf-8'))
    if not result.get('ok'):
        raise RuntimeError('telegram_media_group_send_failed')
    return result.get('result', [])

def valid_e164(phone):
    return phone.startswith('+') and phone[1:].isdigit() and 8 <= len(phone) <= 16

def normalize_phone(phone, default_code='+966'):
    raw = str(phone or '').strip()
    if not raw:
        return ''
    digits = re.sub(r'\D', '', raw)
    if digits.startswith('00'):
        digits = digits[2:]
    code_digits = re.sub(r'\D', '', default_code)
    while digits.startswith(code_digits + code_digits):
        digits = digits[len(code_digits):]
    if raw.startswith('+') or digits.startswith(code_digits):
        return '+' + digits
    return default_code + digits.lstrip('0')


def excel_date(value):
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        number = float(text)
        if 1 <= number <= 100000:
            return (datetime(1899, 12, 30) + timedelta(days=number)).strftime('%Y-%m-%d')
    except ValueError:
        pass
    return text


def parse_xlsx_sheets(encoded):
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise ValueError('ملف Excel غير صالح')
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('ملف Excel يتجاوز 10MB')
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
          'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
          'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValueError('ملف Excel غير صالح أو تالف')
    with archive:
        if sum(item.file_size for item in archive.infolist()) > 60 * 1024 * 1024:
            raise ValueError('محتوى ملف Excel كبير جداً')
        shared = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            shared = [''.join(node.text or '' for node in item.findall('.//m:t', ns)) for item in root.findall('m:si', ns)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {item.attrib['Id']: item.attrib['Target'] for item in rels.findall('p:Relationship', ns)}

        def column_index(reference):
            match = re.match(r'[A-Z]+', reference or '')
            value = 0
            for char in (match.group(0) if match else 'A'):
                value = value * 26 + ord(char) - 64
            return value - 1

        parsed_sheets = []
        for sheet in workbook.findall('m:sheets/m:sheet', ns):
            target = targets.get(sheet.attrib.get('{%s}id' % ns['r']), '')
            path = target.lstrip('/') if target.startswith('/xl/') else 'xl/' + target.lstrip('/')
            if path not in archive.namelist():
                continue
            root = ET.fromstring(archive.read(path))
            rows = []
            for row in root.findall('.//m:sheetData/m:row', ns):
                values = {}
                for cell in row.findall('m:c', ns):
                    index = column_index(cell.attrib.get('r', ''))
                    kind = cell.attrib.get('t')
                    value_node = cell.find('m:v', ns)
                    if kind == 'inlineStr':
                        value = ''.join(node.text or '' for node in cell.findall('.//m:t', ns))
                    else:
                        value = value_node.text if value_node is not None else ''
                        if kind == 's' and value:
                            shared_index = int(value)
                            value = shared[shared_index] if shared_index < len(shared) else ''
                    values[index] = str(value or '').strip()
                if values:
                    rows.append([values.get(i, '') for i in range(max(values) + 1)])
            parsed_sheets.append((sheet.attrib.get('name', ''), rows))

    return parsed_sheets


def normalized_excel_header(value):
    value = str(value or '').strip().lower().replace('_', ' ')
    value = re.sub(r'[\u200e\u200f\ufeff]', '', value)
    value = re.sub(r'[^\w\u0600-\u06ff]+', ' ', value, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', value).strip()


EXCEL_IMPORT_ALIASES = {
    'clients': {
        'name': ['الاسم', 'اسم العميل', 'العميل', 'name', 'client name', 'customer name'],
        'phone': ['الهاتف', 'رقم الجوال', 'الجوال', 'phone', 'mobile', 'mobile number'],
        'email': ['البريد', 'البريد الإلكتروني', 'email', 'email address']},
    'projects': {
        'name': ['اسم المشروع', 'المشروع', 'name', 'project name'],
        'client': ['العميل', 'اسم العميل', 'client', 'client name'],
        'location': ['الموقع', 'location', 'site'], 'priority': ['الأولوية', 'priority'],
        'start_date': ['البداية', 'تاريخ البداية', 'start date'], 'due_date': ['الاستحقاق', 'تاريخ الاستحقاق', 'due date', 'end date'],
        'progress': ['التقدم', 'نسبة الإنجاز', 'progress'], 'description': ['الوصف', 'description', 'details']},
    'work_orders': {
        'title': ['أمر العمل', 'عنوان أمر العمل', 'title', 'work order', 'work order title'],
        'project_id': ['معرف المشروع', 'رقم المشروع', 'project id'], 'project': ['المشروع', 'اسم المشروع', 'project', 'project name'],
        'priority': ['الأولوية', 'priority'], 'scheduled_date': ['الموعد', 'تاريخ الجدولة', 'scheduled date'],
        'due_date': ['الاستحقاق', 'تاريخ الاستحقاق', 'due date'], 'description': ['الوصف', 'description', 'details']},
    'samples': {
        'material': ['المادة', 'نوع المادة', 'material', 'material type'],
        'project_id': ['معرف المشروع', 'رقم المشروع', 'project id'], 'project': ['المشروع', 'اسم المشروع', 'project', 'project name'],
        'source': ['المصدر', 'source', 'sample source'], 'received_date': ['تاريخ الاستلام', 'received date', 'date received'],
        'notes': ['ملاحظات', 'الملاحظات', 'notes', 'note']},
    'proficiency': {
        'test_name': ['اسم الاختبار', 'الاختبار', 'test name', 'proficiency test'], 'material': ['المادة', 'material'],
        'standard': ['المعيار', 'standard'], 'provider': ['مقدم الخدمة', 'المزود', 'provider', 'service provider'],
        'participation_date': ['تاريخ المشاركة', 'participation date', 'date'], 'result': ['النتيجة', 'result'],
        'z_score': ['z score', 'z-score', 'درجة z'], 'report_ref': ['مرجع التقرير', 'report reference', 'report ref'],
        'notes': ['ملاحظات', 'notes', 'note']},
    'staff': {
        'full_name': ['الاسم الكامل', 'اسم الموظف', 'full name', 'employee name'], 'job_title': ['المسمى الوظيفي', 'job title', 'position'],
        'specialty': ['التخصص', 'specialty'], 'experience_years': ['سنوات الخبرة', 'years of experience', 'experience years'],
        'qualification_ref': ['مرجع المؤهل', 'qualification reference', 'qualification ref'],
        'cv_ref': ['مرجع السيرة الذاتية', 'cv reference', 'cv ref'], 'notes': ['ملاحظات', 'notes', 'note']}
}


def parse_entity_xlsx(encoded, entity_type):
    aliases = EXCEL_IMPORT_ALIASES.get(entity_type)
    if not aliases:
        raise ValueError('نوع الاستيراد غير مدعوم')
    lookup = {normalized_excel_header(alias): field for field, names in aliases.items() for alias in names}
    primary = {'clients':'name', 'projects':'name', 'work_orders':'title', 'samples':'material',
               'proficiency':'test_name', 'staff':'full_name'}[entity_type]
    date_fields = {'start_date', 'due_date', 'scheduled_date', 'received_date', 'participation_date'}
    candidates = []
    for sheet_name, rows in parse_xlsx_sheets(encoded):
        for header_index, header in enumerate(rows[:35]):
            columns = {index: lookup[normalized_excel_header(value)] for index, value in enumerate(header)
                       if normalized_excel_header(value) in lookup}
            if primary not in columns.values() or len(set(columns.values())) < 2:
                continue
            records = []
            for row in rows[header_index + 1:]:
                payload = {field: (row[index].strip() if index < len(row) else '') for index, field in columns.items()}
                if not payload.get(primary):
                    continue
                for field in date_fields.intersection(payload):
                    payload[field] = excel_date(payload[field])
                records.append(payload)
            candidates.append((len(records), len(set(columns.values())), sheet_name, records))
    if not candidates or max(item[0] for item in candidates) == 0:
        raise ValueError('لم يتم العثور على جدول صالح أو عناوين أعمدة معروفة داخل ملف Excel')
    _, _, sheet_name, records = max(candidates, key=lambda item: (item[0], item[1]))
    return sheet_name, records


def parse_equipment_xlsx(encoded):
    parsed_sheets = parse_xlsx_sheets(encoded)

    aliases = {
        'equipment name': 'name', 'اسم الجهاز': 'name',
        'equipment serial no.': 'serial_no', 'equipment serial no': 'serial_no', 'الرقم التسلسلي': 'serial_no',
        'equipment id': 'equipment_code', 'رقم الجهاز': 'equipment_code', 'كود الجهاز': 'equipment_code',
        'range': 'range_text', 'النطاق': 'range_text', 'section': 'section', 'القسم': 'section',
        'verification status': 'verification_status', 'حالة التحقق': 'verification_status',
        'maintenance status': 'maintenance_status', 'حالة الصيانة': 'maintenance_status',
        'calibrated to': 'calibrated_to', 'معاير حتى': 'calibrated_to',
        'date of inter service': 'service_date', 'تاريخ الخدمة': 'service_date',
        'note': 'notes', 'notes': 'notes', 'ملاحظات': 'notes'
    }
    candidates = []
    for sheet_name, rows in parsed_sheets:
        header_index = next((i for i, row in enumerate(rows[:25]) if any(str(value).strip().lower() == 'equipment name' for value in row)), None)
        if header_index is None:
            continue
        columns = {}
        for index, value in enumerate(rows[header_index]):
            key = re.sub(r'\s+', ' ', str(value).strip().lower())
            if key in aliases:
                columns[index] = aliases[key]
        records = []
        for row in rows[header_index + 1:]:
            payload = {field: (row[index] if index < len(row) else '') for index, field in columns.items()}
            sequence = row[1].strip() if len(row) > 1 else (row[0].strip() if row else '')
            if not payload.get('name') or not re.fullmatch(r'\d+(?:\.0+)?', sequence):
                continue
            payload['calibrated_to'] = excel_date(payload.get('calibrated_to'))
            payload['service_date'] = excel_date(payload.get('service_date'))
            verification = payload.get('verification_status', '').lower()
            payload['status'] = 'غير ساري' if ('not valid' in verification or 'needed' in verification) else 'ساري'
            records.append(payload)
        candidates.append((len(records), sheet_name, records))
    if not candidates or max(item[0] for item in candidates) == 0:
        raise ValueError('لم يتم العثور على جدول أجهزة صالح داخل ملف Excel')
    _, sheet_name, records = max(candidates, key=lambda item: item[0])
    return sheet_name, records


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
    """Compatibility shim: communication now uses direct channel links."""
    return None


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
    token = create_session(user)
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
        if length > MAX_JSON_BODY_BYTES:
            raise ValueError('حجم الطلب يتجاوز الحد المسموح')
        raw = self.rfile.read(length) if length else b'{}'
        return json.loads(raw or b'{}')

    def static(self, filename, content_type, extra_headers=None):
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
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
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
            self.send_cors_headers()
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
            'equipment': q("select * from equipment order by coalesce(section,''),coalesce(equipment_code,''),name,id"),
            'audit': q("select a.*,u.full_name from audit_log a left join users u on u.id=a.user_id where a.entity in ('client','project','work_order','sample','test','report','field_visit','equipment','quality_document','user') and a.action not like 'حذف %' order by a.id desc limit 150"),
            'activity': q("select created_at,action,details from audit_log where entity in ('client','project','work_order','sample','test','report','field_visit','equipment','quality_document','user') and action not like 'حذف %' order by id desc limit 15"),
            'alerts': alerts,
            'sync': q("select id,entity,entity_id,operation,status,attempts,created_at,last_error from sync_queue where status='queued' order by id desc limit 30"),
            'technicians': q("select id,full_name,username from users where active=1 and role in ('technician','field') order by full_name")
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
            '/index.html': ('index.html', 'text/html; charset=utf-8'),
            '/style.css': ('style.css', 'text/css; charset=utf-8'),
            '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
            '/app-password.js': ('app-password.js', 'application/javascript; charset=utf-8'),
            '/quality-management.js': ('quality-management.js', 'application/javascript; charset=utf-8'),
            '/runtime-config.js': ('runtime-config.js', 'application/javascript; charset=utf-8'),
            '/sw.js': ('sw.js', 'application/javascript; charset=utf-8'),
            '/manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json; charset=utf-8'),
            '/logo.jpg': ('logo.jpg', 'image/jpeg'),
            '/logo.png': ('logo.png', 'image/png'),
            '/asas-home-banner.jpg': ('asas-home-banner.jpg', 'image/jpeg'),
            '/asas-home-banner.png': ('asas-home-banner.png', 'image/png'),
            '/asas-home-banner-mobile.png': ('asas-home-banner-mobile.png', 'image/png'),
            '/engineering-pages-bg.jpg': ('engineering-pages-bg.jpg', 'image/jpeg'),
            '/whatsapp-logo.svg': ('whatsapp-logo.svg', 'image/svg+xml; charset=utf-8'),
            '/telegram-logo.svg': ('telegram-logo.svg', 'image/svg+xml; charset=utf-8'),
            '/i18n.js': ('i18n.js', 'application/javascript; charset=utf-8'),
            '/branch-map.js': ('branch-map.js', 'application/javascript; charset=utf-8'),
            '/field-test-guide.html': ('field-test-guide.html', 'text/html; charset=utf-8'),
            '/company-profile.pdf': ('company-profile.pdf', 'application/pdf')
        }
        if path in static_files:
            return self.static(*static_files[path])

        if path == '/api/health':
            try:
                connection = db()
                connection.execute('select 1').fetchone()
                connection.close()
                return self.send_json({'status': 'ok', 'database': 'ready', 'service': 'asas-lims', 'version': APP_VERSION})
            except sqlite3.Error:
                return self.send_json({'status': 'degraded', 'database': 'unavailable', 'service': 'asas-lims', 'version': APP_VERSION}, 503)

        user = user_from(self)
        if path.startswith('/api/') and not user:
            return self.send_json({'error': 'غير مسجل الدخول'}, 401)

        connection = db()
        try:
            if path == '/api/events':
                if not self.require_permission(user, 'dashboard'):
                    return
                return self.stream_events()

            if path == '/api/system/status':
                if not self.require_permission(user, 'settings'):
                    return
                integrity = connection.execute('PRAGMA quick_check').fetchone()[0]
                queued = connection.execute("select count(*) from sync_queue where status='queued'").fetchone()[0]
                return self.send_json({
                    'version': APP_VERSION,
                    'status': 'ok' if integrity == 'ok' else 'degraded',
                    'database_integrity': integrity,
                    'database_size_bytes': os.path.getsize(DB) if os.path.exists(DB) else 0,
                    'queued_sync_items': queued,
                    'active_sessions': len(SESSIONS),
                    'session_ttl_seconds': SESSION_TTL_SECONDS
                })

            if path == '/api/users':
                if not self.require_permission(user, 'users'):
                    return
                rows = connection.execute('select id,username,full_name,role,phone,avatar_data_url,active,created_at from users order by id desc').fetchall()
                return self.send_json([dict(row) for row in rows])

            if path == '/api/me':
                row = connection.execute(
                    'select id,username,full_name,role,phone,avatar_data_url,active from users where id=? and active=1',
                    (user['id'],)
                ).fetchone()
                if not row:
                    return self.send_json({'error': 'الحساب غير متاح'}, 401)
                return self.send_json(dict(row))

            if path == '/api/settings':
                if not self.require_permission(user, 'settings'):
                    return
                return self.send_json({row['key']: row['value'] for row in connection.execute('select key,value from settings').fetchall()})

            if path == '/api/communication-links':
                rows = connection.execute(
                    "select key,value from settings where key in ('whatsapp_group_url','telegram_url')"
                ).fetchall()
                return self.send_json({row['key']: row['value'] for row in rows})

            if path == '/api/whatsapp/drafts':
                if not self.require_permission(user, 'dashboard'):
                    return
                if require_role(user, {'manager'}):
                    rows = connection.execute('''select d.*,u.full_name recipient_name,u.phone recipient_phone from whatsapp_drafts d
                        left join users u on u.id=d.recipient_user_id order by d.id desc limit 100''').fetchall()
                else:
                    rows = connection.execute('''select d.*,u.full_name recipient_name,u.phone recipient_phone from whatsapp_drafts d
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

            if path == '/api/smart-imports':
                section = str(parse_qs(parsed.query).get('section', [''])[0])
                if not smart_section_allowed(user, section):
                    return self.send_json({'error': 'غير مصرح'}, 403)
                rows = connection.execute('''select id,original_name,file_category,coalesce(material_group,'أخرى') material_group,classification_status,entity_type,entity_id,created_at
                    from record_attachments where section=? order by material_group,file_category,original_name,id desc limit 2000''', (section,)).fetchall()
                return self.send_json([dict(row) for row in rows])

            if path.startswith('/api/attachments/files/'):
                attachment_id = parse_optional_int(path.rsplit('/', 1)[-1])
                row = connection.execute('select a.*,u.role from record_attachments a left join users u on u.id=a.uploaded_by where a.id=?', (attachment_id,)).fetchone()
                if not row or not (record_allowed(user, row['entity_type']) or smart_section_allowed(user, row['section'])):
                    return self.send_json({'error': 'الملف غير موجود أو غير مصرح'}, 404)
                target = os.path.join(RECORD_UPLOADS, row['stored_name'])
                if not os.path.isfile(target):
                    return self.send_json({'error': 'الملف غير موجود'}, 404)
                extension = os.path.splitext(row['stored_name'])[1].lower()
                types = {'.pdf':'application/pdf','.doc':'application/msword','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','.xls':'application/vnd.ms-excel','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.csv':'text/csv','.txt':'text/plain','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.webp':'image/webp','.heic':'image/heic','.dwg':'application/acad','.dxf':'application/dxf'}
                return self.static(os.path.relpath(target, BASE), types.get(extension, 'application/octet-stream'), {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(row['original_name'])})

            if path == '/api/lab-suite':
                if not self.require_permission(user, 'quality'):
                    return
                def rows(sql):
                    return [dict(row) for row in connection.execute(sql).fetchall()]
                return self.send_json({
                    'inventory': rows('select * from inventory_items order by name'),
                    'requests': rows('select * from order_requests order by id desc'),
                    'methods': rows('select * from test_methods order by id desc'),
                    'ncr': rows('select * from nonconformities order by id desc'),
                    'capa': rows('select * from corrective_actions order by id desc'),
                    'training': rows('select * from training_records order by id desc'),
                    'environment': rows('select * from environmental_monitoring order by id desc'),
                    'maintenance': rows('select * from maintenance_records order by id desc'),
                    'suppliers': rows('select * from suppliers order by name'),
                    'quotations': rows('select * from quotations order by id desc'),
                    'contracts': rows('select * from contracts order by id desc'),
                    'complaints': rows('select * from customer_complaints order by id desc')
                })

            if path == '/api/quality':
                if not self.require_permission(user, 'quality'):
                    return
                return self.send_json({
                    'documents': [dict(row) for row in connection.execute('select * from quality_documents order by category,code,id desc').fetchall()],
                    'proficiency': [dict(row) for row in connection.execute('select * from proficiency_tests order by participation_date desc,id desc').fetchall()],
                    'staff': [dict(row) for row in connection.execute('select * from quality_staff order by active desc,full_name').fetchall()]
                })

            if path == '/api/quality/management':
                if not self.require_permission(user, 'quality'):
                    return
                rows = lambda sql: [dict(row) for row in connection.execute(sql).fetchall()]
                return self.send_json({
                    'swot': rows('select s.*,u.full_name owner_name from quality_swot s left join users u on u.id=s.owner_id order by s.id desc'),
                    'risks': rows('select r.*,r.probability*r.impact score,u.full_name owner_name from quality_risks r left join users u on u.id=r.owner_id order by score desc,r.id desc'),
                    'kpis': rows('select k.*,case when k.target=0 then 0 else round(k.actual*100.0/k.target,1) end achievement,u.full_name owner_name from quality_kpis k left join users u on u.id=k.owner_id order by k.id desc'),
                    'actions': rows("select a.*,u.full_name owner_name from quality_actions a left join users u on u.id=a.owner_id order by case a.status when 'open' then 0 when 'in_progress' then 1 else 2 end,a.due_date,a.id desc")
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

            if path == '/api/trash':
                if not self.require_permission(user, 'trash'):
                    return
                rows = connection.execute('''select t.id,t.entity_type,t.original_id,t.label,t.deleted_at,u.full_name deleted_by_name
                    from trash_items t left join users u on u.id=t.deleted_by order by t.id desc limit 500''').fetchall()
                return self.send_json([dict(row) for row in rows])

            if path == '/api/trash/item':
                if not self.require_permission(user, 'trash'):
                    return
                trash_id = parse_optional_int(parse_qs(parsed.query).get('id', [''])[0])
                row = connection.execute('select id,entity_type,original_id,label,payload_json,deleted_at from trash_items where id=?', (trash_id,)).fetchone()
                if not row:
                    return self.send_json({'error': 'العنصر غير موجود في السلة'}, 404)
                result = dict(row); result['payload'] = json.loads(result.pop('payload_json'))
                return self.send_json(result)

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
            attempt_key = login_attempt_key(self, username)
            retry_after = login_rate_status(attempt_key)
            if retry_after:
                connection.close()
                return self.send_json({'ok': False, 'error': 'too_many_attempts'}, 429, {'Retry-After': str(retry_after)})
            user, token, error = password_login(connection, username, str(data.get('password', '')))
            if error:
                record_login_failure(attempt_key)
                connection.close()
                return self.send_json({'ok': False, 'error': error}, 401)
            clear_login_failures(attempt_key)
            phone = str(user['phone'] or '').strip()
            connection.close()
            return self.send_json({'ok': True, 'token': token, 'user': {'username': user['username'], 'name': user['full_name'], 'role': user['role'], 'phone': phone, 'avatar_data_url': user['avatar_data_url']}}, extra_headers={'Set-Cookie': 'LIMS_SESSION=' + token + '; Path=/; HttpOnly; Secure; SameSite=Strict'})

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
            token = create_session(user)
            audit(connection, user['id'], 'OTP_VERIFIED', 'user', user['id'], 'Twilio Verify approved')
            connection.commit()
            connection.close()
            return self.send_json(
                {'ok': True, 'token': token, 'user': {'username': user['username'], 'name': user['full_name'], 'role': user['role'], 'phone': phone, 'avatar_data_url': user['avatar_data_url']}},
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
            if path == '/api/system/backup':
                if user.get('role') not in {'admin', 'quality_manager'}:
                    return self.send_json({'error': 'النسخ الاحتياطي متاح لمدير النظام ومدير الجودة فقط'}, 403)
                os.makedirs(BACKUP_DIR, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                filename = 'asas-lims-backup-' + stamp + '.sqlite3'
                target = os.path.join(BACKUP_DIR, filename)
                destination = sqlite3.connect(target)
                try:
                    connection.backup(destination)
                finally:
                    destination.close()
                audit(connection, user['id'], 'إنشاء نسخة احتياطية', 'system', 0, filename)
                connection.commit()
                return self.send_json({'ok': True, 'file_name': filename, 'size_bytes': os.path.getsize(target)})

            if path == '/api/system/reset-operational':
                if user.get('role') not in {'admin', 'quality_manager'}:
                    return self.send_json({'error': 'تصفير النظام متاح لمدير النظام ومدير الجودة فقط'}, 403)
                if str(data.get('confirmation') or '') != 'RESET-ASAS-OPERATIONAL':
                    return self.send_json({'error': 'رمز تأكيد التصفير غير صحيح'}, 400)
                keep_names = ['أسامة']
                keep_rows = []
                for name in keep_names:
                    matches = connection.execute("select id,username,full_name,role from users where active=1 and (trim(full_name)=? or full_name like ? or trim(username)=?)", (name, '%'+name+'%', name)).fetchall()
                    if len(matches) != 1:
                        return self.send_json({'error': 'لم يتم التصفير: يجب أن يطابق الاسم «'+name+'» مستخدمًا نشطًا واحدًا فقط'}, 409)
                    keep_rows.append(matches[0])
                keep_ids = list(dict.fromkeys(row['id'] for row in keep_rows))
                if len(keep_ids) != 1:
                    return self.send_json({'error': 'لم يتم التصفير: حساب أسامة غير متطابق'}, 409)
                osama = keep_rows[0]
                if osama['role'] not in {'admin','quality_manager'}:
                    return self.send_json({'error': 'لم يتم التصفير: يجب أن يكون حساب أسامة مدير النظام أو مدير الجودة'}, 409)
                os.makedirs(BACKUP_DIR, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                backup_name = 'before-operational-reset-' + stamp + '.sqlite3'
                backup_target = os.path.join(BACKUP_DIR, backup_name)
                destination = sqlite3.connect(backup_target)
                try:
                    connection.backup(destination)
                finally:
                    destination.close()
                operational_tables = ['quotation_items','quotations','contracts','customer_complaints','corrective_actions','nonconformities','chain_of_custody','sample_result_entries','order_requests','inventory_items','maintenance_records','calibration_records','environmental_monitoring','training_records','field_visits','report_files','reports','proctor_points','proctor_results','test_data','tests','samples','work_orders','projects','clients','equipment','quality_documents','proficiency_tests','quality_staff','quality_swot','quality_risks','quality_kpis','quality_actions','record_attachments','catalog_resources','whatsapp_drafts','upload_receipts','trash_items','audit_log','sync_queue','suppliers']
                connection.execute('PRAGMA foreign_keys=OFF')
                try:
                    connection.execute('BEGIN IMMEDIATE')
                    deleted = {}
                    for table in operational_tables:
                        if connection.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone():
                            deleted[table] = connection.execute('select count(*) from '+table).fetchone()[0]
                            connection.execute('delete from '+table)
                            connection.execute("delete from sqlite_sequence where name=?", (table,))
                    placeholders = ','.join('?' for _ in keep_ids)
                    deleted['users'] = connection.execute('select count(*) from users where id not in ('+placeholders+')', keep_ids).fetchone()[0]
                    connection.execute('delete from users where id not in ('+placeholders+')', keep_ids)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.execute('PRAGMA foreign_keys=ON')
                publish_event('system', 'operational_reset', 0)
                return self.send_json({'ok': True, 'backup': backup_name, 'preserved_users': [dict(row) for row in keep_rows], 'deleted': deleted, 'queued': 0})

            if path == '/api/quality/management':
                if not self.require_permission(user, 'quality'):
                    return
                kind, title = str(data.get('type') or ''), str(data.get('title') or '').strip()
                if kind not in {'swot','risk','kpi','action'} or not title:
                    return self.send_json({'error': 'نوع السجل والعنوان مطلوبان'}, 400)
                owner_id = parse_optional_int(data.get('owner_id'))
                if owner_id and not connection.execute('select id from users where id=? and active=1',(owner_id,)).fetchone():
                    return self.send_json({'error': 'المسؤول المحدد غير موجود'}, 400)
                if kind == 'swot':
                    quadrant = str(data.get('quadrant') or '')
                    if quadrant not in {'strength','weakness','opportunity','threat'}: return self.send_json({'error':'تصنيف SWOT غير صحيح'},400)
                    cursor=connection.execute('insert into quality_swot(quadrant,title,description,owner_id,created_by) values(?,?,?,?,?)',(quadrant,title,data.get('description'),owner_id,user['id']))
                elif kind == 'risk':
                    probability=max(1,min(5,int(data.get('probability') or 1))); impact=max(1,min(5,int(data.get('impact') or 1)))
                    cursor=connection.execute('insert into quality_risks(title,category,probability,impact,mitigation,owner_id,due_date,created_by) values(?,?,?,?,?,?,?,?)',(title,data.get('category'),probability,impact,data.get('mitigation'),owner_id,data.get('due_date'),user['id']))
                elif kind == 'kpi':
                    cursor=connection.execute('insert into quality_kpis(name,unit,target,actual,period,owner_id,created_by) values(?,?,?,?,?,?,?)',(title,data.get('unit'),float(data.get('target') or 0),float(data.get('actual') or 0),data.get('period'),owner_id,user['id']))
                else:
                    cursor=connection.execute('insert into quality_actions(title,source_type,description,owner_id,due_date,created_by) values(?,?,?,?,?,?)',(title,data.get('source_type') or 'improvement',data.get('description'),owner_id,data.get('due_date'),user['id']))
                entity_id=cursor.lastrowid
                audit(connection,user['id'],'إضافة سجل جودة تشغيلي','quality_'+kind,entity_id,title)
                connection.commit(); publish_event('quality_'+kind,'create',entity_id)
                return self.send_json({'ok':True,'id':entity_id})

            if path == '/api/quality/management/delete':
                if not self.require_permission(user, 'quality'): return
                kind=str(data.get('type') or ''); entity_id=parse_optional_int(data.get('id'))
                table={'swot':'quality_swot','risk':'quality_risks','kpi':'quality_kpis','action':'quality_actions'}.get(kind)
                if not table or not entity_id: return self.send_json({'error':'السجل غير صحيح'},400)
                if not connection.execute('select id from '+table+' where id=?',(entity_id,)).fetchone(): return self.send_json({'error':'السجل غير موجود'},404)
                connection.execute('delete from '+table+' where id=?',(entity_id,)); connection.commit(); publish_event('quality_'+kind,'delete',entity_id)
                return self.send_json({'ok':True})

            if path == '/api/telegram/draft':
                if not self.require_permission(user, 'dashboard'):
                    return
                text = str(data.get('text', '')).strip()
                if not text:
                    return self.send_json({'error': 'المسودة فارغة'}, 400)
                sender_row = connection.execute('select full_name,username from users where id=?', (user['id'],)).fetchone()
                sender_name = ((sender_row['full_name'] if sender_row else '') or user.get('full_name') or (sender_row['username'] if sender_row else '') or user.get('username') or 'مستخدم أساس').strip()
                lines = text.splitlines()
                if lines and (lines[0].startswith('👤 المرسل الميداني:') or lines[0].startswith('👤 المرسل الفعلي:')):
                    lines[0] = sender_name
                    text = '\n'.join(lines)
                else:
                    text = sender_name + '\n' + text
                photos = data.get('photos') or []
                if not isinstance(photos, list):
                    photos = []
                photos = photos[:10]
                try:
                    if photos:
                        # Telegram renders a media group as one album. Put the draft text
                        # on the album itself so the photos appear first and the writing
                        # follows beneath them, without a separate "field photos" label.
                        photo_items = telegram_send_media_group(photos, text)
                        photo_ids = [item.get('message_id') for item in photo_items]
                        sent = photo_items[0] if photo_items else {}
                    else:
                        sent = telegram_send_text(text)
                        photo_items = []
                        photo_ids = []
                except (RuntimeError, ValueError) as error:
                    return self.send_json({'error': str(error)}, 503)
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                    return self.send_json({'error': 'telegram_provider_error'}, 502)
                audit(connection, user['id'], 'إرسال مسودة تليجرام', 'telegram_draft', sent.get('message_id'), '{} · صور {}'.format(text[:420], len(photo_ids)))
                connection.commit()
                publish_event('telegram_draft', sent.get('message_id'), 'sent')
                return self.send_json({'ok': True, 'message_id': sent.get('message_id'), 'photos_sent': len(photo_ids), 'sender_name': sender_name, 'layout': 'album_then_text' if photos else 'text_only'})

            if path == '/api/audit/delete':
                if user.get('role') not in {'admin', 'quality_manager'}:
                    return self.send_json({'error': 'الحذف متاح لمدير النظام ومدير الجودة فقط'}, 403)
                audit_id = parse_optional_int(data.get('id'))
                current = connection.execute('select id,action,entity,details from audit_log where id=?', (audit_id,)).fetchone()
                if not current:
                    return self.send_json({'error': 'سجل التدقيق غير موجود'}, 404)
                connection.execute('delete from audit_log where id=?', (audit_id,))
                connection.commit(); publish_event('audit', 'delete', audit_id)
                return self.send_json({'ok': True, 'deleted': 1})

            if path == '/api/audit/clear':
                if user.get('role') not in {'admin', 'quality_manager'}:
                    return self.send_json({'error': 'الحذف متاح لمدير النظام ومدير الجودة فقط'}, 403)
                count = connection.execute('select count(*) from audit_log').fetchone()[0]
                connection.execute('delete from audit_log')
                connection.commit(); publish_event('audit', 'clear', 0)
                return self.send_json({'ok': True, 'deleted': count})

            if path == '/api/sync/reset':
                if user.get('role') not in {'admin','general_manager','manager','quality_manager','laboratory_manager'}:
                    return self.send_json({'error': 'ليس لديك صلاحية إعادة بدء المزامنة'}, 403)
                count = connection.execute('select count(*) from sync_queue').fetchone()[0]
                connection.execute('delete from sync_queue')
                connection.execute("delete from sqlite_sequence where name='sync_queue'")
                connection.commit(); publish_event('sync', 'reset', 0)
                return self.send_json({'ok': True, 'deleted': count, 'queued': 0})

            if path == '/api/trash/restore':
                if not self.require_permission(user, 'trash'):
                    return
                trash_id = parse_optional_int(data.get('id'))
                row = connection.execute('select * from trash_items where id=?', (trash_id,)).fetchone()
                if not row:
                    return self.send_json({'error': 'العنصر غير موجود في السلة'}, 404)
                payload = json.loads(row['payload_json'])
                try:
                    restore_deleted_record(connection, payload)
                except sqlite3.IntegrityError:
                    connection.rollback()
                    return self.send_json({'error': 'تعذر الاستعادة لأن رقم السجل مستخدم حالياً أو أن السجل الأب غير موجود'}, 409)
                connection.execute('delete from trash_items where id=?', (trash_id,))
                queue_sync(connection, row['entity_type'], row['original_id'], 'restore', {'label': row['label']})
                audit(connection, user['id'], 'استعادة من السلة', row['entity_type'], row['original_id'], row['label'])
                connection.commit(); publish_event(row['entity_type'], 'restore', row['original_id'])
                return self.send_json({'ok': True, 'restored': 1})

            if path == '/api/trash/delete':
                if user.get('role') not in {'admin', 'quality_manager'}:
                    return self.send_json({'error': 'الحذف النهائي متاح لمدير النظام ومدير الجودة فقط'}, 403)
                trash_id = parse_optional_int(data.get('id'))
                row = connection.execute('select * from trash_items where id=?', (trash_id,)).fetchone()
                if not row:
                    return self.send_json({'error': 'العنصر غير موجود في السلة'}, 404)
                payload = json.loads(row['payload_json'])
                for attachment in payload.get('attachments', []):
                    stored_name = os.path.basename(str(attachment.get('stored_name') or ''))
                    target = os.path.join(RECORD_UPLOADS, stored_name)
                    if stored_name and os.path.isfile(target):
                        os.remove(target)
                connection.execute('delete from trash_items where id=?', (trash_id,))
                connection.commit(); publish_event('trash', 'delete', trash_id)
                return self.send_json({'ok': True, 'deleted': 1})

            if path == '/api/records/delete':
                if user.get('role') not in {'admin', 'general_manager', 'manager', 'quality_manager', 'laboratory_manager'}:
                    return self.send_json({'error': 'ليس لديك صلاحية حذف السجلات'}, 403)
                entity = str(data.get('entity') or '').strip()
                entity_id = parse_optional_int(data.get('id'))
                if not entity_id:
                    return self.send_json({'error': 'معرف السجل مطلوب'}, 400)
                names = {'client':'عميل','project':'مشروع','work_order':'أمر عمل','sample':'عينة','test':'اختبار','report':'تقرير','equipment':'جهاز','quality_document':'وثيقة جودة'}
                if entity not in names:
                    return self.send_json({'error': 'نوع السجل غير قابل للحذف'}, 400)
                payload = snapshot_deleted_record(connection, entity, entity_id)
                if not payload.get('record'):
                    return self.send_json({'error': 'السجل غير موجود'}, 404)
                label_field = {'client':'name','project':'code','work_order':'order_no','sample':'sample_no','test':'test_no','report':'report_no','equipment':'name','quality_document':'code'}[entity]
                trash_label = str(payload['record'].get(label_field) or entity_id)
                connection.execute('insert into trash_items(entity_type,original_id,label,payload_json,deleted_by) values(?,?,?,?,?)',
                                   (entity, entity_id, trash_label, json.dumps(payload, ensure_ascii=False), user['id']))
                if entity == 'project':
                    current = connection.execute('select code label from projects where id=?', (entity_id,)).fetchone()
                    sample_ids = [row['id'] for row in connection.execute('select id from samples where project_id=?', (entity_id,))]
                    for sample_id in sample_ids:
                        connection.execute("delete from record_attachments where (entity_type='sample' and entity_id=?) or (entity_type='test' and entity_id in (select id from tests where sample_id=?)) or (entity_type='report' and entity_id in (select r.id from reports r join tests t on t.id=r.test_id where t.sample_id=?))", (sample_id, sample_id, sample_id))
                        connection.execute('update field_visits set sample_id=null where sample_id=?', (sample_id,))
                        connection.execute('delete from reports where test_id in (select id from tests where sample_id=?)', (sample_id,))
                        connection.execute('delete from tests where sample_id=?', (sample_id,))
                        connection.execute('delete from samples where id=?', (sample_id,))
                    connection.execute("delete from record_attachments where (entity_type='project' and entity_id=?) or (entity_type='work_order' and entity_id in (select id from work_orders where project_id=?))", (entity_id, entity_id))
                    connection.execute('delete from work_orders where project_id=?', (entity_id,))
                    connection.execute('update field_visits set project_id=null where project_id=?', (entity_id,))
                    for table in ('quotations','contracts','customer_complaints'):
                        connection.execute('update ' + table + ' set project_id=null where project_id=?', (entity_id,))
                    connection.execute('delete from projects where id=?', (entity_id,))
                elif entity == 'work_order':
                    current = connection.execute('select order_no label from work_orders where id=?', (entity_id,)).fetchone()
                    connection.execute("delete from record_attachments where entity_type='work_order' and entity_id=?", (entity_id,))
                    connection.execute("delete from whatsapp_drafts where related_entity='work_order' and related_id=?", (entity_id,))
                    connection.execute('delete from work_orders where id=?', (entity_id,))
                elif entity == 'equipment':
                    current = connection.execute('select name label from equipment where id=?', (entity_id,)).fetchone()
                    connection.execute("delete from record_attachments where entity_type='equipment' and entity_id=?", (entity_id,))
                    connection.execute('delete from maintenance_records where equipment_id=?', (entity_id,))
                    connection.execute('delete from calibration_records where equipment_id=?', (entity_id,))
                    connection.execute('delete from equipment where id=?', (entity_id,))
                elif entity == 'quality_document':
                    current = connection.execute('select code label from quality_documents where id=?', (entity_id,)).fetchone()
                    connection.execute("delete from record_attachments where entity_type='quality_document' and entity_id=?", (entity_id,))
                    connection.execute('delete from quality_documents where id=?', (entity_id,))
                elif entity == 'client':
                    current = connection.execute('select name label from clients where id=?', (entity_id,)).fetchone()
                    if not current:
                        return self.send_json({'error': 'العميل غير موجود'}, 404)
                    for table in ('projects', 'quotations', 'contracts', 'customer_complaints'):
                        connection.execute('update ' + table + ' set client_id=null where client_id=?', (entity_id,))
                    connection.execute("delete from record_attachments where entity_type='client' and entity_id=?", (entity_id,))
                    connection.execute("delete from whatsapp_drafts where related_entity='client' and related_id=?", (entity_id,))
                    connection.execute('delete from clients where id=?', (entity_id,))
                elif entity == 'sample':
                    current = connection.execute('select sample_no label from samples where id=?', (entity_id,)).fetchone()
                    if not current:
                        return self.send_json({'error': 'العينة غير موجودة'}, 404)
                    connection.execute("delete from record_attachments where (entity_type='sample' and entity_id=?) or (entity_type='test' and entity_id in (select id from tests where sample_id=?)) or (entity_type='report' and entity_id in (select r.id from reports r join tests t on t.id=r.test_id where t.sample_id=?))", (entity_id, entity_id, entity_id))
                    connection.execute("delete from whatsapp_drafts where (related_entity='sample' and related_id=?) or (related_entity='test' and related_id in (select id from tests where sample_id=?)) or (related_entity='report' and related_id in (select r.id from reports r join tests t on t.id=r.test_id where t.sample_id=?))", (entity_id, entity_id, entity_id))
                    connection.execute('update field_visits set sample_id=null where sample_id=?', (entity_id,))
                    connection.execute('delete from reports where test_id in (select id from tests where sample_id=?)', (entity_id,))
                    connection.execute('delete from tests where sample_id=?', (entity_id,))
                    connection.execute('delete from samples where id=?', (entity_id,))
                elif entity == 'test':
                    current = connection.execute('select test_no label from tests where id=?', (entity_id,)).fetchone()
                    if not current:
                        return self.send_json({'error': 'الاختبار غير موجود'}, 404)
                    connection.execute("delete from record_attachments where (entity_type='test' and entity_id=?) or (entity_type='report' and entity_id in (select id from reports where test_id=?))", (entity_id, entity_id))
                    connection.execute("delete from whatsapp_drafts where (related_entity='test' and related_id=?) or (related_entity='report' and related_id in (select id from reports where test_id=?))", (entity_id, entity_id))
                    connection.execute('delete from reports where test_id=?', (entity_id,))
                    connection.execute('delete from tests where id=?', (entity_id,))
                else:
                    current = connection.execute('select report_no label from reports where id=?', (entity_id,)).fetchone()
                    if not current:
                        return self.send_json({'error': 'التقرير غير موجود'}, 404)
                    connection.execute("delete from record_attachments where entity_type='report' and entity_id=?", (entity_id,))
                    connection.execute("delete from whatsapp_drafts where related_entity='report' and related_id=?", (entity_id,))
                    connection.execute('delete from reports where id=?', (entity_id,))
                connection.execute('delete from sync_queue where entity=? and entity_id=?', (entity, entity_id))
                queue_sync(connection, entity, entity_id, 'delete', {'label': current['label']})
                connection.commit(); publish_event(entity, 'delete', entity_id)
                return self.send_json({'ok': True, 'deleted': 1})

            if path == '/api/auth/change-password':
                current_password = str(data.get('current_password') or '')
                new_password = str(data.get('new_password') or '')
                confirm_password = str(data.get('confirm_password') or '')
                account = connection.execute('select id,password_hash from users where id=? and active=1', (user['id'],)).fetchone()
                if not account or not checkpw(current_password, account['password_hash']):
                    return self.send_json({'error': 'كلمة المرور الحالية غير صحيحة'}, 400)
                if not new_password:
                    return self.send_json({'error': 'كلمة المرور الجديدة مطلوبة'}, 400)
                if new_password != confirm_password:
                    return self.send_json({'error': 'تأكيد كلمة المرور غير مطابق'}, 400)
                connection.execute('update users set password_hash=? where id=?', (hp(new_password), user['id']))
                audit(connection, user['id'], 'تغيير كلمة المرور الذاتية', 'user', user['id'], user['username'])
                connection.commit()
                return self.send_json({'ok': True})

            if path == '/api/profile/update':
                full_name = str(data.get('full_name') or '').strip()
                avatar = str(data.get('avatar_data_url') or '')
                if not full_name:
                    return self.send_json({'error': 'الاسم الكامل مطلوب'}, 400)
                if avatar and (not avatar.startswith('data:image/') or len(avatar) > 1_500_000):
                    return self.send_json({'error': 'صورة المستخدم غير صالحة أو كبيرة'}, 400)
                connection.execute('update users set full_name=?,avatar_data_url=? where id=?', (full_name, avatar, user['id']))
                refresh_user_sessions(user['id'], full_name=full_name, avatar_data_url=avatar)
                audit(connection, user['id'], 'تعديل الملف الشخصي', 'user', user['id'], user['username'])
                connection.commit(); publish_event('user', 'profile', user['id'])
                return self.send_json({'ok': True, 'user': {'username': user['username'], 'full_name': full_name, 'role': user['role'], 'phone': user.get('phone'), 'avatar_data_url': avatar}})

            if path == '/api/users/create':
                if not self.require_permission(user, 'users'):
                    return
                username = str(data.get('username', '')).strip()
                full_name = str(data.get('full_name', '')).strip()
                password = str(data.get('password', ''))
                role = data.get('role', 'technician')
                phone = normalize_phone(data.get('phone', ''))
                if not username:
                    return self.send_json({'error': 'اسم المستخدم مطلوب'}, 400)
                if not full_name:
                    return self.send_json({'error': 'الاسم الكامل مطلوب'}, 400)
                if not password:
                    return self.send_json({'error': 'كلمة المرور مطلوبة'}, 400)
                if role not in ROLE_PERMS:
                    return self.send_json({'error': 'الدور المحدد غير معتمد في الخادم؛ حدّث الصفحة ثم اختر الدور مرة أخرى'}, 400)
                if phone and not valid_e164(phone):
                    return self.send_json({'error': 'رقم الجوال يجب أن يكون بصيغة دولية مثل +9665XXXXXXXX'}, 400)
                if phone_in_use(connection, phone):
                    return self.send_json({'error': 'رقم الجوال مسجل لمستخدم آخر'}, 409)
                avatar = str(data.get('avatar_data_url') or '')
                if avatar and (not avatar.startswith('data:image/') or len(avatar) > 1_500_000):
                    return self.send_json({'error': 'صورة المستخدم غير صالحة أو كبيرة'}, 400)
                connection.execute('insert into users(username,password_hash,full_name,role,phone,avatar_data_url,active) values(?,?,?,?,?,?,1)', (username, hp(password), full_name, role, phone, avatar))
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
                phone = normalize_phone(data.get('phone', target['phone'] or ''))
                if role not in ROLE_PERMS or (entity_id == user['id'] and active == 0):
                    return self.send_json({'error': 'تعديل المستخدم غير صالح'}, 400)
                if phone and not valid_e164(phone):
                    return self.send_json({'error': 'رقم الجوال يجب أن يكون بصيغة دولية مثل +9665XXXXXXXX'}, 400)
                if phone_in_use(connection, phone, entity_id):
                    return self.send_json({'error': 'رقم الجوال مسجل لمستخدم آخر'}, 409)
                avatar = str(data.get('avatar_data_url', target['avatar_data_url'] or ''))
                if avatar and (not avatar.startswith('data:image/') or len(avatar) > 1_500_000):
                    return self.send_json({'error': 'صورة المستخدم غير صالحة أو كبيرة'}, 400)
                connection.execute('update users set full_name=?,role=?,phone=?,avatar_data_url=?,active=? where id=?', (data.get('full_name', target['full_name']), role, phone, avatar, active, entity_id))
                refresh_user_sessions(entity_id, full_name=data.get('full_name', target['full_name']), role=role,
                                      phone=phone, avatar_data_url=avatar, active=active)
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

            if path == '/api/settings/update':
                if user.get('role') not in {'admin','general_manager','technical_manager','laboratory_manager','quality_manager','manager'}:
                    return self.send_json({'error': 'إعدادات النظام متاحة للأدوار الإدارية فقط'}, 403)
                allowed = {'lab_name','lab_name_en','website_url','support_email','support_phone','currency','report_prefix','sample_prefix','work_order_prefix','timezone','default_language','date_format','whatsapp_group_url','telegram_url','map_provider','max_attachment_mb','enable_otp','require_report_approval','require_test_approval','require_field_gps','audit_delete_enabled','auto_sync_enabled','default_sample_status','report_due_days','result_decimal_places','unit_system','field_visit_prefix','client_prefix','sync_interval_minutes','audit_retention_days','backup_retention_days','auto_file_classification','skip_failed_uploads','direct_download_enabled','permit_provider','permit_lookup_timeout','gps_target_accuracy_m','field_photo_limit','telegram_draft_enabled','show_field_coordinates','default_home_page','table_page_size','show_saudi_clock','dashboard_refresh_seconds'}
                for key, value in data.items():
                    if key in allowed:
                        connection.execute('insert into settings(key,value) values(?,?) on conflict(key) do update set value=excluded.value', (key, str(value)[:500]))
                audit(connection, user['id'], 'تعديل إعدادات النظام', 'settings', 0, 'System settings updated')
                connection.commit(); publish_event('settings', 'update', 0)
                return self.send_json({'ok': True})

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

            if path.startswith('/api/whatsapp/drafts/') and path.endswith('/rename'):
                if not require_role(user, {'manager'}):
                    return self.send_json({'error': 'تعديل اسم المسودة للمدير فقط'}, 403)
                draft_id = int(path.split('/')[4])
                draft_name = str(data.get('draft_name') or '').strip()[:120]
                if not draft_name:
                    return self.send_json({'error': 'اسم المسودة مطلوب'}, 400)
                updated = connection.execute('update whatsapp_drafts set draft_name=? where id=?', (draft_name, draft_id)).rowcount
                if not updated:
                    return self.send_json({'error': 'المسودة غير موجودة'}, 404)
                audit(connection, user['id'], 'تعديل اسم مسودة واتساب', 'whatsapp_draft', draft_id, draft_name)
                connection.commit(); publish_event('whatsapp_draft', 'rename', draft_id)
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
                if status == 'معتمد' and not require_role(user, set()):
                    return self.send_json({'error': 'اعتماد المشروع لمدير النظام أو مدير الجودة فقط'}, 403)
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

            if path.startswith('/api/lab-suite/'):
                if not self.require_permission(user, 'quality'):
                    return
                resource = path.split('/')[-1]
                entity_id = None
                if resource == 'ncr':
                    number = str(data.get('ncr_no') or nextno(connection, 'NCR-', 'nonconformities')).strip()
                    description = str(data.get('description') or '').strip()
                    if not description:
                        return self.send_json({'error': 'وصف عدم المطابقة مطلوب'}, 400)
                    connection.execute('insert into nonconformities(ncr_no,source_type,source_id,category,severity,description,immediate_action,root_cause,status,owner_id,due_date,created_by) values(?,?,?,?,?,?,?,?,?,?,?,?)',
                        (number,data.get('source_type'),parse_optional_int(data.get('source_id')),data.get('category'),data.get('severity') or 'minor',description,data.get('immediate_action'),data.get('root_cause'),data.get('status') or 'open',parse_optional_int(data.get('owner_id')),data.get('due_date'),user['id']))
                elif resource == 'capa':
                    description = str(data.get('description') or '').strip()
                    if not description:
                        return self.send_json({'error': 'وصف الإجراء مطلوب'}, 400)
                    connection.execute('insert into corrective_actions(ncr_id,action_no,action_type,description,owner_id,due_date,status) values(?,?,?,?,?,?,?)',
                        (parse_optional_int(data.get('ncr_id')),data.get('action_no'),data.get('action_type') or 'corrective',description,parse_optional_int(data.get('owner_id')),data.get('due_date'),data.get('status') or 'open'))
                elif resource == 'training':
                    uid = parse_optional_int(data.get('user_id'))
                    title = str(data.get('training_title') or '').strip()
                    if not uid or not title:
                        return self.send_json({'error': 'الموظف واسم التدريب مطلوبان'}, 400)
                    connection.execute('insert into training_records(user_id,training_title,competency_area,provider,training_date,expiry_date,result,certificate_ref,authorization_scope,notes) values(?,?,?,?,?,?,?,?,?,?)',
                        (uid,title,data.get('competency_area'),data.get('provider'),data.get('training_date'),data.get('expiry_date'),data.get('result'),data.get('certificate_ref'),data.get('authorization_scope'),data.get('notes')))
                elif resource == 'environment':
                    area = str(data.get('area') or '').strip(); parameter = str(data.get('parameter') or '').strip()
                    if not area or not parameter:
                        return self.send_json({'error': 'المنطقة ومعيار المراقبة مطلوبان'}, 400)
                    value = data.get('value_num'); minimum = data.get('min_limit'); maximum = data.get('max_limit')
                    status = 'not_evaluated'
                    try:
                        numeric = float(value)
                        status = 'out_of_spec' if (minimum not in (None,'') and numeric < float(minimum)) or (maximum not in (None,'') and numeric > float(maximum)) else 'pass'
                    except (TypeError,ValueError):
                        pass
                    connection.execute('insert into environmental_monitoring(area,parameter,value_num,unit,min_limit,max_limit,compliance_status,recorded_by,notes) values(?,?,?,?,?,?,?,?,?)',
                        (area,parameter,value,data.get('unit'),minimum,maximum,status,user['id'],data.get('notes')))
                elif resource == 'maintenance':
                    equipment_id = parse_optional_int(data.get('equipment_id'))
                    if not equipment_id or not data.get('service_date'):
                        return self.send_json({'error': 'الجهاز وتاريخ الصيانة مطلوبان'}, 400)
                    connection.execute('insert into maintenance_records(equipment_id,maintenance_type,service_date,provider,description,parts_used,cost,next_due,status,performed_by,attachment_ref) values(?,?,?,?,?,?,?,?,?,?,?)',
                        (equipment_id,data.get('maintenance_type') or 'preventive',data.get('service_date'),data.get('provider'),data.get('description'),data.get('parts_used'),data.get('cost'),data.get('next_due'),data.get('status') or 'completed',user['id'],data.get('attachment_ref')))
                elif resource == 'complaint':
                    number = str(data.get('complaint_no') or nextno(connection, 'CMP-', 'customer_complaints')).strip()
                    subject = str(data.get('subject') or '').strip(); description = str(data.get('description') or '').strip()
                    if not subject or not description:
                        return self.send_json({'error': 'موضوع الشكوى ووصفها مطلوبان'}, 400)
                    connection.execute('insert into customer_complaints(complaint_no,client_id,project_id,subject,description,priority,status,owner_id) values(?,?,?,?,?,?,?,?)',
                        (number,parse_optional_int(data.get('client_id')),parse_optional_int(data.get('project_id')),subject,description,data.get('priority') or 'normal',data.get('status') or 'open',parse_optional_int(data.get('owner_id'))))
                else:
                    return self.send_json({'error': 'الوحدة غير مدعومة'}, 404)
                entity_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                audit(connection,user['id'],'إضافة سجل مختبري متقدم',resource,entity_id,json.dumps(data,ensure_ascii=False))
                connection.commit()
                publish_event(resource,'create',entity_id)
                return self.send_json({'ok':True,'id':entity_id})

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

            if path == '/api/equipment/import':
                if not self.require_permission(user, 'equipment'):
                    return
                sheet_name, records = parse_equipment_xlsx(str(data.get('file_base64') or ''))
                inserted = 0
                updated = 0
                for item in records:
                    existing = None
                    if item.get('equipment_code'):
                        existing = connection.execute('select id from equipment where trim(equipment_code)=trim(?)', (item['equipment_code'],)).fetchone()
                    if not existing and item.get('serial_no') and item['serial_no'] != '-':
                        existing = connection.execute('select id from equipment where trim(serial_no)=trim(?)', (item['serial_no'],)).fetchone()
                    values = (item.get('name'), item.get('serial_no'), item.get('equipment_code'), item.get('range_text'),
                              item.get('section'), item.get('verification_status'), item.get('maintenance_status'),
                              item.get('calibrated_to'), item.get('service_date'), item.get('status'), item.get('notes'))
                    if existing:
                        connection.execute('''update equipment set name=?,serial_no=?,equipment_code=?,range_text=?,section=?,
                            verification_status=?,maintenance_status=?,calibrated_to=?,service_date=?,status=?,notes=? where id=?''',
                            values + (existing['id'],))
                        updated += 1
                    else:
                        connection.execute('''insert into equipment(name,serial_no,equipment_code,range_text,section,
                            verification_status,maintenance_status,calibrated_to,service_date,status,notes)
                            values(?,?,?,?,?,?,?,?,?,?,?)''', values)
                        inserted += 1
                audit(connection, user['id'], 'استيراد أجهزة من Excel', 'equipment', 0,
                      '{}: {} جديد، {} محدّث'.format(sheet_name, inserted, updated))
                connection.commit()
                publish_event('equipment', 'import', 0)
                return self.send_json({'ok': True, 'inserted': inserted, 'updated': updated,
                                       'total': len(records), 'sheet': sheet_name})

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
                if category not in {'procedure', 'worksheet', 'admin_form'} or not title:
                    return self.send_json({'error': 'بيانات وثيقة الجودة غير مكتملة'}, 400)
                if not code:
                    numbers = [int(match.group(1)) for row in connection.execute("select code from quality_documents where code like 'AS-RS-QC-%'").fetchall() for match in [re.fullmatch(r'AS-RS-QC-(\d+)', row['code'] or '')] if match]
                    code = 'AS-RS-QC-' + str((max(numbers) if numbers else 0) + 1).zfill(2)
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

            if path == '/api/quality/documents/update':
                if not self.require_permission(user, 'quality'): return
                entity_id = parse_optional_int(data.get('id'))
                category, code, title = str(data.get('category','')).strip(), str(data.get('code','')).strip(), str(data.get('title','')).strip()
                if category not in {'procedure','worksheet','admin_form'} or not code or not title or not connection.execute('select id from quality_documents where id=?',(entity_id,)).fetchone(): return self.send_json({'error':'بيانات وثيقة الجودة غير صحيحة'},400)
                connection.execute('update quality_documents set category=?,code=?,title=?,revision=?,status=? where id=?',(category,code,title,data.get('revision'),data.get('status') or 'ساري',entity_id))
                audit(connection,user['id'],'تعديل وثيقة جودة','quality_document',entity_id,code);connection.commit();publish_event('quality_document','update',entity_id)
                return self.send_json({'ok':True,'id':entity_id})

            if path == '/api/quality/documents/delete':
                if not self.require_permission(user, 'quality'): return
                entity_id = parse_optional_int(data.get('id')); current=connection.execute('select code from quality_documents where id=?',(entity_id,)).fetchone()
                if not current: return self.send_json({'error':'وثيقة الجودة غير موجودة'},404)
                connection.execute('delete from quality_documents where id=?',(entity_id,));audit(connection,user['id'],'حذف وثيقة جودة','quality_document',entity_id,current['code']);connection.commit();publish_event('quality_document','delete',entity_id)
                return self.send_json({'ok':True})

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

            if path == '/api/smart-import':
                section = str(data.get('section') or '')
                if not smart_section_allowed(user, section):
                    return self.send_json({'error': 'لا تملك صلاحية هذا القسم'}, 403)
                upload_id = str(data.get('upload_id') or '').strip()[:160]
                if upload_id:
                    receipt = connection.execute('select response_json from upload_receipts where upload_id=? and user_id=?', (upload_id, user['id'])).fetchone()
                    if receipt:
                        try:
                            return self.send_json(json.loads(receipt['response_json']))
                        except (TypeError, json.JSONDecodeError):
                            connection.execute('delete from upload_receipts where upload_id=?', (upload_id,))
                            connection.commit()
                try:
                    encoded = str(data.get('file_base64') or '')
                    content = base64.b64decode(encoded, validate=True)
                    file_name = os.path.basename(str(data.get('file_name') or ''))
                    if not content or len(content) > 25 * 1024 * 1024:
                        raise ValueError('الملف فارغ أو يتجاوز 25MB')
                    imported, skipped = [], []
                    if os.path.splitext(file_name)[1].lower() == '.zip':
                        try:
                            archive = zipfile.ZipFile(io.BytesIO(content))
                        except zipfile.BadZipFile:
                            raise ValueError('ملف ZIP غير صالح')
                        with archive:
                            members = [item for item in archive.infolist() if not item.is_dir() and not item.filename.startswith('__MACOSX/')]
                            if len(members) > 100 or sum(item.file_size for item in members) > 100 * 1024 * 1024:
                                raise ValueError('الحزمة كبيرة؛ الحد 100 ملف و100MB بعد الفك')
                            for item in members:
                                member_name = os.path.basename(item.filename)
                                if not member_name or os.path.splitext(member_name)[1].lower() not in SMART_FILE_TYPES or member_name.lower().endswith('.zip'):
                                    if member_name:
                                        skipped.append({'name': member_name, 'reason': 'صيغة غير مدعومة داخل ZIP'})
                                    continue
                                try:
                                    imported.append(store_smart_file(connection, user, section, member_name, archive.read(item)))
                                except (ValueError, OSError) as error:
                                    skipped.append({'name': member_name, 'reason': str(error)})
                            if not imported and not skipped:
                                skipped.append({'name': file_name, 'reason': 'حزمة ZIP فارغة'})
                    else:
                        imported.append(store_smart_file(connection, user, section, file_name, content))
                except (ValueError, TypeError) as error:
                    connection.rollback()
                    return self.send_json({'error': str(error)}, 400)
                matched = sum(1 for item in imported if item['entity_id'])
                response_payload = {'ok': True, 'imported': imported, 'total': len(imported), 'matched': matched,
                                    'review': len(imported) - matched, 'skipped': skipped}
                audit(connection, user['id'], 'إرفاق وفرز ذكي', section, 0, '{} ملف، {} مرتبط'.format(len(imported), matched))
                if upload_id:
                    connection.execute('insert or replace into upload_receipts(upload_id,user_id,section,response_json) values(?,?,?,?)',
                                       (upload_id, user['id'], section, json.dumps(response_payload, ensure_ascii=False)))
                    connection.execute("delete from upload_receipts where created_at < datetime('now','-7 day')")
                connection.commit(); publish_event(section, 'smart_import', 0)
                return self.send_json(response_payload)

            if path == '/api/catalog':
                if user.get('role') not in {'admin','general_manager','technical_manager','laboratory_manager','quality_manager','quality_officer','manager'}:
                    return self.send_json({'error': 'إضافة اختبار جديد متاحة للمستخدم المخول فقط'}, 403)
                category = str(data.get('category') or '').strip()
                code = str(data.get('code') or '').strip()
                name_ar = str(data.get('name_ar') or '').strip()
                name_en = str(data.get('name_en') or '').strip()
                standard = str(data.get('standard') or '').strip()
                version = str(data.get('version') or '').strip()
                notes = str(data.get('notes') or '').strip()
                if category not in {'خرسانة','تربة','أسفلت','الحقل وNDT'}:
                    return self.send_json({'error': 'التصنيف يجب أن يكون خرسانة أو تربة أو أسفلت أو الحقل وNDT'}, 400)
                if not code or not name_ar or not standard:
                    return self.send_json({'error': 'كود الاختبار والاسم والمواصفة مطلوبة'}, 400)
                existing = connection.execute('select id,code,category from test_catalog where lower(code)=lower(?)', (code,)).fetchone()
                if existing:
                    return self.send_json({'error': 'يوجد اختبار بهذا الكود بالفعل'}, 409)
                cursor = connection.execute('''insert into test_catalog(code,name_ar,name_en,category,standard,version,notes,active)
                    values(?,?,?,?,?,?,?,1)''', (code[:80], name_ar[:240], name_en[:240], category, standard[:240], version[:80], notes[:1000]))
                catalog_id = cursor.lastrowid
                audit(connection, user['id'], 'إضافة اختبار إلى الكتالوج', 'test_catalog', catalog_id, code + ' - ' + name_ar)
                connection.commit(); publish_event('catalog', 'create', catalog_id)
                return self.send_json({'ok': True, 'id': catalog_id, 'code': code, 'category': category})

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

            if path == '/api/import/xlsx':
                entity_type = str(data.get('entity_type') or '')
                required_perm = {'clients':'clients','projects':'projects','work_orders':'projects','samples':'samples',
                                 'proficiency':'quality','staff':'quality'}.get(entity_type)
                if not required_perm or not self.require_permission(user, required_perm):
                    return
                try:
                    sheet_name, rows = parse_entity_xlsx(str(data.get('file_base64') or ''), entity_type)
                except ValueError as error:
                    return self.send_json({'error': str(error)}, 400)
                if len(rows) > 1000:
                    return self.send_json({'error': 'يحتوي الملف على أكثر من 1000 سجل؛ قسّمه إلى ملفين'}, 400)
                imported, skipped = 0, []
                for number, row in enumerate(rows, 2):
                    try:
                        if entity_type == 'clients':
                            name = str(row.get('name') or '').strip()
                            if not name: raise ValueError()
                            connection.execute('insert into clients(name,phone,email) values(?,?,?)', (name, row.get('phone'), row.get('email')))
                        elif entity_type == 'projects':
                            name = str(row.get('name') or '').strip()
                            if not name: raise ValueError()
                            client_name = str(row.get('client') or '').strip(); client_id = None
                            if client_name:
                                client = connection.execute('select id from clients where name=?', (client_name,)).fetchone()
                                if not client:
                                    connection.execute('insert into clients(name) values(?)', (client_name,)); client_id = connection.execute('select last_insert_rowid()').fetchone()[0]
                                else: client_id = client['id']
                            progress = int(float(row.get('progress') or 0))
                            connection.execute('insert into projects(code,name,client_id,location,priority,description,start_date,due_date,progress,updated_at) values(?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)',
                                (nextno(connection,'PR-','projects'), name, client_id, row.get('location'), normalize_priority(row.get('priority')), row.get('description'), row.get('start_date'), row.get('due_date'), max(0, min(100, progress))))
                        elif entity_type == 'work_orders':
                            title = str(row.get('title') or '').strip()
                            project_id = parse_optional_int(row.get('project_id'))
                            if not project_id and row.get('project'):
                                project = connection.execute('select id from projects where name=? or code=?', (row['project'], row['project'])).fetchone()
                                project_id = project['id'] if project else None
                            if not title or not project_id: raise ValueError()
                            connection.execute('insert into work_orders(order_no,project_id,title,description,priority,scheduled_date,due_date,created_by,updated_at) values(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)',
                                (nextno(connection,'WO-','work_orders'),project_id,title,row.get('description'),normalize_priority(row.get('priority')),row.get('scheduled_date'),row.get('due_date'),user['id']))
                        elif entity_type == 'samples':
                            material = str(row.get('material') or '').strip(); project_id = parse_optional_int(row.get('project_id'))
                            if not project_id and row.get('project'):
                                project = connection.execute('select id from projects where name=? or code=?', (row['project'], row['project'])).fetchone()
                                project_id = project['id'] if project else None
                            if not material: raise ValueError()
                            connection.execute('insert into samples(sample_no,project_id,material,source,received_date,notes) values(?,?,?,?,?,?)',
                                (nextno(connection,'SMP-','samples'),project_id,material,row.get('source'),row.get('received_date') or time.strftime('%Y-%m-%d'),row.get('notes')))
                        elif entity_type == 'proficiency':
                            test_name = str(row.get('test_name') or '').strip()
                            if not test_name: raise ValueError()
                            connection.execute('insert into proficiency_tests(test_name,material,standard,provider,participation_date,result,z_score,report_ref,notes) values(?,?,?,?,?,?,?,?,?)',
                                (test_name,row.get('material'),row.get('standard'),row.get('provider'),row.get('participation_date'),row.get('result'),row.get('z_score'),row.get('report_ref'),row.get('notes')))
                        else:
                            full_name = str(row.get('full_name') or '').strip()
                            if not full_name: raise ValueError()
                            experience = int(float(row.get('experience_years') or 0))
                            connection.execute('insert into quality_staff(full_name,job_title,specialty,experience_years,qualification_ref,cv_ref,active,notes) values(?,?,?,?,?,?,1,?)',
                                (full_name,row.get('job_title'),row.get('specialty'),experience,row.get('qualification_ref'),row.get('cv_ref'),row.get('notes')))
                        imported += 1
                    except (ValueError, TypeError, sqlite3.Error):
                        skipped.append(number)
                audit(connection, user['id'], 'استيراد Excel تلقائي', entity_type, 0, str(imported) + ' صف من ' + sheet_name)
                connection.commit(); publish_event(entity_type, 'xlsx_import', 0)
                return self.send_json({'ok': True, 'imported': imported, 'skipped': skipped, 'sheet': sheet_name})

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
                if status == 'معتمد' and not require_role(user, set()):
                    return self.send_json({'error': 'الاعتماد لمدير النظام أو مدير الجودة فقط'}, 403)
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
