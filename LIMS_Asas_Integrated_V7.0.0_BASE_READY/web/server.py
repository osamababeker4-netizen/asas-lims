#!/usr/bin/env python3
"""ASAS LIMS Central API - stdlib only.
Development-ready central service. Put behind HTTPS/reverse proxy for production.
"""
import base64, hashlib, hmac, json, os, secrets, sqlite3, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import urllib.error

ROOT = Path(__file__).parent.resolve()
DB = ROOT / 'asas_lims_central.sqlite3'
HOST = os.getenv('ASAS_HOST','0.0.0.0')
PORT = int(os.getenv('ASAS_PORT','8080'))
SECRET_FILE = ROOT / '.server_secret'
LOCK = threading.RLock()
TOKEN_TTL = 8*60*60

def secret():
    if SECRET_FILE.exists(): return SECRET_FILE.read_bytes().strip()
    s = secrets.token_bytes(32); SECRET_FILE.write_bytes(s); return s
SECRET = secret()

def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def hash_pw(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 240000)
    return base64.urlsafe_b64encode(salt).decode()+'.'+base64.urlsafe_b64encode(dk).decode()

def verify_pw(password, stored):
    try:
        a,b=stored.split('.',1); salt=base64.urlsafe_b64decode(a); expected=base64.urlsafe_b64decode(b)
        got=hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 240000)
        return hmac.compare_digest(got,expected)
    except Exception: return False

def token_for(user):
    payload={'sub':user['username'],'role':user['role'],'exp':int(time.time())+TOKEN_TTL}
    raw=json.dumps(payload,separators=(',',':')).encode(); p=base64.urlsafe_b64encode(raw).decode().rstrip('=')
    sig=hmac.new(SECRET,p.encode(),hashlib.sha256).hexdigest()
    return p+'.'+sig

def user_from_token(tok):
    try:
        p,s=tok.split('.',1); expected=hmac.new(SECRET,p.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(s,expected): return None
        raw=base64.urlsafe_b64decode(p+'==='); data=json.loads(raw)
        if data['exp'] < time.time(): return None
        return data
    except Exception: return None

def db_conn():
    c=sqlite3.connect(DB, timeout=10); c.row_factory=sqlite3.Row; return c

def init_db():
    with db_conn() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS system_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, phone TEXT, password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, action TEXT, entity TEXT, entity_id TEXT, details TEXT, at TEXT NOT NULL)')
        # Event storage is deliberately separate from system_state: field clients can
        # safely sync one offline operation at a time without overwriting a snapshot.
        c.execute('CREATE TABLE IF NOT EXISTS sync_events (device_id TEXT NOT NULL, queue_id INTEGER NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL, operation TEXT NOT NULL, payload TEXT NOT NULL, received_at TEXT NOT NULL, PRIMARY KEY(device_id,queue_id))')
        c.execute('CREATE TABLE IF NOT EXISTS sync_entities (entity TEXT NOT NULL, entity_id TEXT NOT NULL, payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL, PRIMARY KEY(entity,entity_id))')
        if not c.execute('SELECT 1 FROM users WHERE username=?',('admin',)).fetchone():
            bootstrap=os.getenv('ASAS_BOOTSTRAP_PASSWORD') or secrets.token_urlsafe(18)
            if not os.getenv('ASAS_BOOTSTRAP_PASSWORD'): print('WARNING: generated one-time initial admin password:', bootstrap)
            c.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',('admin','مدير النظام','admin','',hash_pw(bootstrap),1,now()))
        if not c.execute('SELECT 1 FROM system_state WHERE id=1').fetchone():
            c.execute('INSERT INTO system_state VALUES(1,?,?,?)',('{}',1,now()))

def get_state():
    with LOCK, db_conn() as c:
        r=c.execute('SELECT payload,version,updated_at FROM system_state WHERE id=1').fetchone()
        return {'state':json.loads(r['payload']),'version':r['version'],'updatedAt':r['updated_at']}

def put_state(payload, expected_version=None):
    text=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
    with LOCK, db_conn() as c:
        r=c.execute('SELECT version FROM system_state WHERE id=1').fetchone(); current=r['version']
        if expected_version is not None and int(expected_version)!=current:
            return {'ok':False,'conflict':True,'serverVersion':current}
        nv=current+1
        c.execute('UPDATE system_state SET payload=?,version=?,updated_at=? WHERE id=1',(text,nv,now()))
        return {'ok':True,'version':nv,'updatedAt':now()}


def messaging_config():
    return {
        'whatsapp': bool(os.getenv('WHATSAPP_ACCESS_TOKEN') and os.getenv('WHATSAPP_PHONE_NUMBER_ID')),
        'telegram': bool(os.getenv('TELEGRAM_BOT_TOKEN')),
        'mode': 'official_api_when_configured_else_draft'
    }

def telegram_send(chat_id, text):
    token=os.getenv('TELEGRAM_BOT_TOKEN','')
    url=f'https://api.telegram.org/bot{token}/sendMessage'
    data=json.dumps({'chat_id':chat_id,'text':text}).encode()
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=15) as r: return json.loads(r.read())

def whatsapp_send(to, text):
    token=os.getenv('WHATSAPP_ACCESS_TOKEN',''); phone_id=os.getenv('WHATSAPP_PHONE_NUMBER_ID','')
    url=f'https://graph.facebook.com/v23.0/{phone_id}/messages'
    data=json.dumps({'messaging_product':'whatsapp','to':to,'type':'text','text':{'preview_url':False,'body':text}}).encode()
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json','Authorization':'Bearer '+token},method='POST')
    with urllib.request.urlopen(req,timeout=15) as r: return json.loads(r.read())

def audit(username,action,entity,eid,details):
    with LOCK, db_conn() as c: c.execute('INSERT INTO audit(username,action,entity,entity_id,details,at) VALUES(?,?,?,?,?,?)',(username,action,entity,eid,details,now()))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def send_json(self,code,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','SAMEORIGIN'); self.send_header('Referrer-Policy','strict-origin-when-cross-origin'); self.end_headers(); self.wfile.write(raw)
    def body(self):
        n=int(self.headers.get('Content-Length','0')); return json.loads(self.rfile.read(n) or '{}')
    def auth(self):
        h=self.headers.get('Authorization',''); return user_from_token(h[7:]) if h.startswith('Bearer ') else None
    def do_OPTIONS(self):
        self.send_response(204); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization, X-State-Version'); self.send_header('Access-Control-Allow-Methods','GET,PUT,POST,OPTIONS'); self.end_headers()
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/health': return self.send_json(200,{'ok':True,'service':'ASAS LIMS Central API','version':'7.1.0','time':now()})
        if path=='/api/state':
            if not self.auth(): return self.send_json(401,{'ok':False,'error':'unauthorized'})
            return self.send_json(200,get_state())
        if path=='/api/audit':
            if not self.auth(): return self.send_json(401,{'ok':False,'error':'unauthorized'})
            with db_conn() as c: rows=[dict(x) for x in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 500')]
            return self.send_json(200,{'items':rows})
        if path=='/api/me':
            u=self.auth(); return self.send_json(200,{'ok':True,'user':u} if u else {'ok':False,'error':'unauthorized'})
        if path=='/api/messaging/config':
            if not self.auth(): return self.send_json(401,{'ok':False,'error':'unauthorized'})
            return self.send_json(200,{'ok':True,'config':messaging_config()})
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path
        if path=='/api/auth/login':
            try:
                d=self.body(); username=str(d.get('username','')).strip(); password=str(d.get('password',''))
                with db_conn() as c: u=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
                if not u or not u['active'] or not verify_pw(password,u['password_hash']): return self.send_json(401,{'ok':False,'error':'invalid_credentials'})
                otp=f'{secrets.randbelow(1000000):06d}'; exp=int(time.time())+300
                with db_conn() as c:
                    c.execute('CREATE TABLE IF NOT EXISTS otp (username TEXT PRIMARY KEY, code TEXT, exp INTEGER)')
                    c.execute('INSERT INTO otp VALUES(?,?,?) ON CONFLICT(username) DO UPDATE SET code=excluded.code,exp=excluded.exp',(username,otp,exp))
                audit(username,'LOGIN_OTP','USER',username,'OTP issued')
                response={'ok':True,'challenge':True,'expiresIn':300,'user':{'username':u['username'],'name':u['name'],'role':u['role'],'phone':u['phone']}}
                if os.getenv('ASAS_DEV_RETURN_OTP')=='1': response['otp']=otp
                return self.send_json(200,response)
            except Exception as e: return self.send_json(400,{'ok':False,'error':str(e)})
        if path=='/api/auth/verify':
            try:
                d=self.body(); username=str(d.get('username','')); code=str(d.get('otp',''))
                with db_conn() as c: r=c.execute('SELECT code,exp FROM otp WHERE username=?',(username,)).fetchone(); u=c.execute('SELECT username,name,role,phone,active FROM users WHERE username=?',(username,)).fetchone()
                if not r or not u or not u['active'] or int(r['exp'])<int(time.time()) or not hmac.compare_digest(r['code'],code): return self.send_json(401,{'ok':False,'error':'invalid_otp'})
                audit(username,'LOGIN','USER',username,'OTP verified'); return self.send_json(200,{'ok':True,'token':token_for(dict(u)),'user':dict(u)})
            except Exception as e: return self.send_json(400,{'ok':False,'error':str(e)})
        if path=='/api/messaging/send':
            u=self.auth()
            if not u: return self.send_json(401,{'ok':False,'error':'unauthorized'})
            try:
                d=self.body(); channel=str(d.get('channel','')); to=str(d.get('to','')).strip(); text=str(d.get('text','')).strip()
                if not to or not text: return self.send_json(400,{'ok':False,'error':'recipient_and_text_required'})
                if channel=='Telegram':
                    if not os.getenv('TELEGRAM_BOT_TOKEN'): return self.send_json(409,{'ok':False,'error':'telegram_not_configured','draft':True})
                    result=telegram_send(to,text)
                elif channel=='WhatsApp':
                    if not (os.getenv('WHATSAPP_ACCESS_TOKEN') and os.getenv('WHATSAPP_PHONE_NUMBER_ID')): return self.send_json(409,{'ok':False,'error':'whatsapp_not_configured','draft':True})
                    result=whatsapp_send(to,text)
                else: return self.send_json(400,{'ok':False,'error':'unsupported_channel'})
                audit(u['sub'],'MESSAGE_SEND',channel,to,'Official API send')
                return self.send_json(200,{'ok':True,'result':result})
            except Exception as e:
                return self.send_json(502,{'ok':False,'error':'provider_error','details':str(e)})
        if path=='/api/sync/queue':
            u=self.auth()
            if not u: return self.send_json(401,{'ok':False,'error':'unauthorized'})
            try:
                d=self.body(); device_id=str(d.get('deviceId','')).strip(); events=d.get('events',[])
                if not device_id or not isinstance(events,list) or len(events)>100:
                    return self.send_json(400,{'ok':False,'error':'invalid_sync_batch'})
                accepted=[]; conflicts=[]
                with LOCK, db_conn() as c:
                    for e in events:
                        qid=int(e['id']); entity=str(e['entity']); entity_id=str(e['entityId'])
                        operation=str(e.get('operation','UPSERT')); payload=e.get('payload',{})
                        if not entity or not entity_id or not isinstance(payload,dict):
                            return self.send_json(400,{'ok':False,'error':'invalid_sync_event'})
                        seen=c.execute('SELECT 1 FROM sync_events WHERE device_id=? AND queue_id=?',(device_id,qid)).fetchone()
                        if seen:
                            accepted.append({'id':qid,'duplicate':True}); continue
                        current=c.execute('SELECT payload,version FROM sync_entities WHERE entity=? AND entity_id=?',(entity,entity_id)).fetchone()
                        base=e.get('baseVersion')
                        # A create may not silently overwrite an independently-created
                        # record. Updates carry baseVersion when the client has a known
                        # central revision; legacy UPSERTs remain supported.
                        if current and ((base is not None and int(base)!=current['version']) or (base is None and operation=='CREATE')):
                            conflicts.append({'id':qid,'entity':entity,'entityId':entity_id,'serverVersion':current['version'],'remotePayload':json.loads(current['payload'])}); continue
                        version=(current['version']+1) if current else 1
                        text=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
                        c.execute('INSERT INTO sync_events VALUES(?,?,?,?,?,?,?)',(device_id,qid,entity,entity_id,operation,text,now()))
                        c.execute('INSERT INTO sync_entities(entity,entity_id,payload,version,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(entity,entity_id) DO UPDATE SET payload=excluded.payload,version=excluded.version,updated_at=excluded.updated_at',(entity,entity_id,text,version,now()))
                        accepted.append({'id':qid,'version':version})
                    c.commit()
                for e in accepted: audit(u['sub'],'FIELD_SYNC',str(e.get('id')),'QUEUE_EVENT','accepted')
                return self.send_json(200,{'ok':True,'accepted':accepted,'conflicts':conflicts})
            except (KeyError,TypeError,ValueError) as e: return self.send_json(400,{'ok':False,'error':'invalid_sync_event','details':str(e)})
            except Exception as e: return self.send_json(500,{'ok':False,'error':'sync_failed','details':str(e)})
        return self.send_json(404,{'ok':False,'error':'not_found'})
    def do_PUT(self):
        path=urlparse(self.path).path
        if path!='/api/state': return self.send_json(404,{'ok':False,'error':'not_found'})
        u=self.auth()
        if not u: return self.send_json(401,{'ok':False,'error':'unauthorized'})
        if u.get('role') not in ('admin','reviewer','technician','user'): return self.send_json(403,{'ok':False,'error':'forbidden'})
        try:
            data=self.body(); expected=self.headers.get('X-State-Version'); result=put_state(data,expected)
            if result.get('conflict'): return self.send_json(409,result)
            audit(u['sub'],'STATE_UPDATE','SYSTEM','1','Central state updated'); return self.send_json(200,result)
        except Exception as e: return self.send_json(400,{'ok':False,'error':str(e)})
    def log_message(self,fmt,*args): print('%s - %s' % (self.address_string(),fmt%args))

if __name__=='__main__':
    init_db(); print(f'ASAS LIMS Web V7.1 Central API: http://localhost:{PORT}'); ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
