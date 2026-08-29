#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, sqlite3, hashlib, secrets, hmac, math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
BASE=os.path.dirname(os.path.abspath(__file__)); DB=os.path.join(BASE,'lims.db'); PORT=8080; SESSIONS={}

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def hp(p):
 s=secrets.token_bytes(16); d=hashlib.pbkdf2_hmac('sha256',p.encode(),s,200000); return s.hex()+':'+d.hex()
def checkpw(p,h):
 try:
  s,d=h.split(':'); x=hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),200000).hex(); return hmac.compare_digest(x,d)
 except: return False

def init():
 c=db(); c.executescript(open(os.path.join(BASE,'schema.sql'),encoding='utf8').read())
 if c.execute('select count(*) from users').fetchone()[0]==0: c.execute('insert into users(username,password_hash,full_name,role) values(?,?,?,?)',('admin',hp('1234'),'مدير المختبر','admin'))
 if c.execute('select count(*) from test_catalog').fetchone()[0]==0: raise RuntimeError('test catalog missing')
 c.commit(); c.close()

def user_from(h):
 for x in h.headers.get('Cookie','').split(';'):
  if x.strip().startswith('LIMS_SESSION='): return SESSIONS.get(x.strip().split('=',1)[1])

ROLE_PERMS={
 'admin': {'*'},
 'manager': {'dashboard','field','clients','projects','samples','tests','catalog','reports','equipment','audit','users'},
 'technician': {'dashboard','field','clients','projects','samples','tests','catalog','reports','equipment'},
 'field': {'dashboard','field','clients','projects','samples'}
}
def has_perm(u,perm): return u and (u.get('role')=='admin' or perm in ROLE_PERMS.get(u.get('role'),set()) or '*' in ROLE_PERMS.get(u.get('role'),set()))
def require_role(u,roles): return u and (u.get('role') in roles or u.get('role')=='admin')

def audit(uid,action,entity,eid,details):
 c=db(); c.execute('insert into audit_log(user_id,action,entity,entity_id,details) values(?,?,?,?,?)',(uid,action,entity,eid,details)); c.commit(); c.close()

def rowdict(r): return dict(r) if r else None

def nextno(c,prefix,table,col): return prefix+str(c.execute(f'select coalesce(max(id),0)+1 from {table}').fetchone()[0]).zfill(6)

class H(BaseHTTPRequestHandler):
 def send_json(self,d,code=200):
  b=json.dumps(d,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def body(self):
  n=int(self.headers.get('Content-Length','0')); return json.loads(self.rfile.read(n) or b'{}')
 def static(self,p,typ):
  b=open(os.path.join(BASE,p),'rb').read(); self.send_response(200); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  p=urlparse(self.path).path
  if p=='/': return self.static('index.html','text/html; charset=utf-8')
  if p=='/style.css': return self.static('style.css','text/css; charset=utf-8')
  if p=='/app.js': return self.static('app.js','application/javascript; charset=utf-8')
  u=user_from(self)
  if p.startswith('/api/') and not u: return self.send_json({'error':'غير مسجل الدخول'},401)
  c=db()
  try:
   if p=='/api/users':
    if not has_perm(u,'users'): return self.send_json({'error':'ليس لديك صلاحية إدارة المستخدمين'},403)
    rows=c.execute('select id,username,full_name,role,active,created_at from users order by id desc').fetchall()
    return self.send_json([dict(x) for x in rows])
   if p=='/api/catalog': return self.send_json([dict(x) for x in c.execute('select * from test_catalog where active=1 order by category,name_ar').fetchall()])
   if p=='/api/field/search':
    from urllib.parse import parse_qs
    license_no=parse_qs(urlparse(self.path).query).get('license',[''])[0].strip()
    rows=c.execute('select * from field_visits where license_no=? order by id desc limit 20',(license_no,)).fetchall() if license_no else []
    return self.send_json([dict(x) for x in rows])
   if p=='/api/field/recent':
    rows=c.execute('select f.*,u.full_name,p.code project_code,s.sample_no from field_visits f left join users u on u.id=f.created_by left join projects p on p.id=f.project_id left join samples s on s.id=f.sample_id order by f.id desc limit 30').fetchall()
    return self.send_json([dict(x) for x in rows])
   if p=='/api/field/status':
    if not has_perm(u,'field'): return self.send_json({'error':'ليس لديك صلاحية البرنامج الميداني'},403)
    rows=c.execute('select f.id,f.status,f.license_no,f.project_name,f.sample_id,f.created_at,u.full_name from field_visits f left join users u on u.id=f.created_by order by f.id desc limit 100').fetchall()
    return self.send_json([dict(x) for x in rows])
   if p=='/api/dashboard':
    q=lambda s:[dict(x) for x in c.execute(s).fetchall()]
    out={'counts':{k:c.execute(f'select count(*) from {t}').fetchone()[0] for k,t in [('projects','projects'),('samples','samples'),('tests','tests'),('reports','reports'),('equipment','equipment'),('field_visits','field_visits')]},
     'clients':q('select * from clients order by id desc'),'projects':q('select p.*,c.name client_name from projects p left join clients c on c.id=p.client_id order by p.id desc'),
     'samples':q('select s.*,p.name project_name from samples s left join projects p on p.id=s.project_id order by s.id desc'),
     'tests':q('select t.*,s.sample_no,tc.code,tc.name_ar,tc.standard,pr.mdd,pr.omc from tests t join samples s on s.id=t.sample_id join test_catalog tc on tc.id=t.catalog_id left join proctor_results pr on pr.test_id=t.id order by t.id desc'),
     'reports':q('select r.*,t.test_no,tc.name_ar from reports r join tests t on t.id=r.test_id join test_catalog tc on tc.id=t.catalog_id order by r.id desc'),
     'equipment':q('select * from equipment order by id desc'),'audit':q('select a.*,u.full_name from audit_log a left join users u on u.id=a.user_id order by a.id desc limit 150'),'activity':q('select created_at,action,details from audit_log order by id desc limit 15')}
    return self.send_json(out)
   if p.startswith('/api/report/'):
    tid=int(p.rsplit('/',1)[1]); x=c.execute('select r.report_no,r.issued_at,r.status,t.*,s.sample_no,s.material,tc.code,tc.name_ar,tc.standard,tc.category,pr.mdd,pr.omc from reports r join tests t on t.id=r.test_id join samples s on s.id=t.sample_id join test_catalog tc on tc.id=t.catalog_id left join proctor_results pr on pr.test_id=t.id where t.id=?',(tid,)).fetchone()
    if not x:return self.send_json({'error':'التقرير غير موجود'},404)
    data={'inputs':{},'results':{}}
    for z in c.execute('select section,field_name,value_text,value_num,unit,seq from test_data where test_id=? order by section,seq,id',(tid,)).fetchall(): data[z['section']][z['field_name']]=z['value_num'] if z['value_num'] is not None else z['value_text']
    d=dict(x); d['data']=data; d['lab_name']=c.execute("select value from settings where key='lab_name'").fetchone()['value']; return self.send_json(d)
   return self.send_json({'error':'غير موجود'},404)
  finally:c.close()
 def do_POST(self):
  p=urlparse(self.path).path
  if p=='/api/login':
   d=self.body(); c=db(); u=c.execute('select * from users where username=? and active=1',(d.get('username',''),)).fetchone(); c.close()
   if not u or not checkpw(d.get('password',''),u['password_hash']): return self.send_json({'error':'اسم المستخدم أو كلمة المرور غير صحيحة'},401)
   tok=secrets.token_urlsafe(32); SESSIONS[tok]=dict(u); self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Set-Cookie',f'LIMS_SESSION={tok}; HttpOnly; SameSite=Lax; Path=/'); self.end_headers(); self.wfile.write(json.dumps({'ok':True,'user':{'full_name':u['full_name'],'role':u['role']}},ensure_ascii=False).encode()); return
  if p=='/api/logout':
   for x in self.headers.get('Cookie','').split(';'):
    if x.strip().startswith('LIMS_SESSION='): SESSIONS.pop(x.strip().split('=',1)[1],None)
   return self.send_json({'ok':True})
  u=user_from(self)
  if not u:return self.send_json({'error':'غير مسجل الدخول'},401)
  d=self.body(); c=db()
  try:
   if p=='/api/users/create':
    if not has_perm(u,'users'): return self.send_json({'error':'ليس لديك صلاحية إدارة المستخدمين'},403)
    username=str(d.get('username','')).strip(); full_name=str(d.get('full_name','')).strip(); role=d.get('role','technician')
    password=str(d.get('password',''))
    if not username or not full_name or len(password)<4 or role not in ROLE_PERMS: return self.send_json({'error':'بيانات المستخدم غير مكتملة'},400)
    c.execute('insert into users(username,password_hash,full_name,role,active) values(?,?,?,?,1)',(username,hp(password),full_name,role)); eid=c.execute('select last_insert_rowid()').fetchone()[0]; c.commit(); audit(u['id'],'إضافة مستخدم','user',eid,username); return self.send_json({'ok':True,'id':eid})
   if p=='/api/users/update':
    if not has_perm(u,'users'): return self.send_json({'error':'ليس لديك صلاحية إدارة المستخدمين'},403)
    uid=int(d.get('id')); target=c.execute('select * from users where id=?',(uid,)).fetchone()
    if not target: return self.send_json({'error':'المستخدم غير موجود'},404)
    role=d.get('role',target['role']); active=1 if d.get('active',bool(target['active'])) else 0
    if role not in ROLE_PERMS: return self.send_json({'error':'الدور غير صالح'},400)
    if uid==u['id'] and active==0: return self.send_json({'error':'لا يمكن تعطيل حسابك الحالي'},400)
    c.execute('update users set full_name=?,role=?,active=? where id=?',(d.get('full_name',target['full_name']),role,active,uid))
    if d.get('password'): c.execute('update users set password_hash=? where id=?',(hp(str(d['password'])),uid))
    c.commit(); audit(u['id'],'تعديل مستخدم','user',uid,target['username']); return self.send_json({'ok':True})
   if p=='/api/field/status':
    if not has_perm(u,'field'): return self.send_json({'error':'ليس لديك صلاحية البرنامج الميداني'},403)
    vid=int(d.get('id')); status=d.get('status')
    if status not in {'مسودة','مرسلة','قيد المراجعة','معتمدة','مرفوضة'}: return self.send_json({'error':'حالة غير صالحة'},400)
    if status=='قيد المراجعة' and not require_role(u,{'manager'}): return self.send_json({'error':'المراجعة للمدير فقط'},403)
    if status=='معتمدة' and not require_role(u,{'manager'}): return self.send_json({'error':'الاعتماد للمدير فقط'},403)
    if status=='قيد المراجعة': c.execute('update field_visits set status=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP where id=?',(status,u['id'],vid))
    elif status=='معتمدة': c.execute('update field_visits set status=?,approved_by=?,approved_at=CURRENT_TIMESTAMP where id=?',(status,u['id'],vid))
    else: c.execute('update field_visits set status=? where id=?',(status,vid))
    c.commit(); audit(u['id'],'تغيير حالة زيارة ميدانية','field_visit',vid,status); return self.send_json({'ok':True})
   if p=='/api/field/visits':
    if not has_perm(u,'field'): return self.send_json({'error':'ليس لديك صلاحية البرنامج الميداني'},403)
    tests=d.get('tests',[])
    status=d.get('status','مسودة');
    if status not in {'مسودة','مرسلة','قيد المراجعة','معتمدة','مرفوضة'}: return self.send_json({'error':'حالة الزيارة غير صالحة'},400)
    c.execute('insert into field_visits(license_no,contractor_name,project_name,sector_name,layer_no,location,latitude,longitude,tests_json,notes,status,created_by,project_id,sample_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(d.get('license_no','').strip(),d.get('contractor_name'),d.get('project_name'),d.get('sector_name'),d.get('layer_no'),d.get('location'),d.get('latitude'),d.get('longitude'),json.dumps(tests,ensure_ascii=False),d.get('notes'),status,u['id'],d.get('project_id') or None,d.get('sample_id') or None))
    eid=c.execute('select last_insert_rowid()').fetchone()[0]; c.commit(); audit(u['id'],'إضافة زيارة ميدانية','field_visit',eid,d.get('license_no','')); return self.send_json({'ok':True,'id':eid})
   if p=='/api/clients':
    if not has_perm(u,'clients'): return self.send_json({'error':'ليس لديك صلاحية العملاء'},403)
    c.execute('insert into clients(name,phone,email) values(?,?,?)',(d['name'],d.get('phone'),d.get('email'))); eid=c.execute('select last_insert_rowid()').fetchone()[0]; c.commit(); audit(u['id'],'إضافة','client',eid,d['name']); return self.send_json({'ok':True,'id':eid})
   if p=='/api/projects':
    if not has_perm(u,'projects'): return self.send_json({'error':'ليس لديك صلاحية المشاريع'},403)
    code=nextno(c,'PR-','projects','id'); c.execute('insert into projects(code,name,client_id,location) values(?,?,?,?)',(code,d['name'],d.get('client_id') or None,d.get('location'))); eid=c.execute('select last_insert_rowid()').fetchone()[0]; c.commit(); audit(u['id'],'إضافة','project',eid,code); return self.send_json({'ok':True,'id':eid,'code':code})
   if p=='/api/samples':
    if not has_perm(u,'samples'): return self.send_json({'error':'ليس لديك صلاحية العينات'},403)
    c.execute('insert into samples(sample_no,project_id,material,source,received_date,notes) values(?,?,?,?,?,?)',(d['sample_no'],d.get('project_id') or None,d['material'],d.get('source'),d['received_date'],d.get('notes'))); eid=c.execute('select last_insert_rowid()').fetchone()[0]; c.commit(); audit(u['id'],'إضافة','sample',eid,d['sample_no']); return self.send_json({'ok':True,'id':eid})
   if p=='/api/equipment':
    if not has_perm(u,'equipment'): return self.send_json({'error':'ليس لديك صلاحية الأجهزة'},403)
    c.execute('insert into equipment(name,serial_no,manufacturer,model,last_calibration,next_calibration,certificate_no,notes) values(?,?,?,?,?,?,?,?)',(d['name'],d.get('serial_no'),d.get('manufacturer'),d.get('model'),d.get('last_calibration'),d.get('next_calibration'),d.get('certificate_no'),d.get('notes'))); eid=c.execute('select last_insert_rowid()').fetchone()[0]; c.commit(); audit(u['id'],'إضافة','equipment',eid,d['name']); return self.send_json({'ok':True,'id':eid})
   if p=='/api/tests/proctor':
    if not has_perm(u,'tests'): return self.send_json({'error':'ليس لديك صلاحية الاختبارات'},403)
    return self.create_proctor(c,u,d)
   if p=='/api/tests/generic':
    if not has_perm(u,'tests'): return self.send_json({'error':'ليس لديك صلاحية الاختبارات'},403)
    cat=c.execute('select * from test_catalog where id=?',(d['catalog_id'],)).fetchone()
    if not cat:return self.send_json({'error':'الاختبار غير موجود'},404)
    testno=d.get('test_no') or nextno(c,'TST-','tests','id'); c.execute('insert into tests(test_no,sample_id,catalog_id,status,technician_id,started_at,completed_at) values(?,?,?,?,?,?,CURRENT_TIMESTAMP)',(testno,int(d['sample_id']),cat['id'],d.get('status','مكتمل'),u['id'],d.get('started_at'))); tid=c.execute('select last_insert_rowid()').fetchone()[0]
    for section,vals in [('inputs',d.get('inputs',{})),('results',d.get('results',{}))]:
     if isinstance(vals,dict):
      for k,v in vals.items():
       num=None; txt=None
       if v is None or v=='': continue
       try:num=float(v) if not isinstance(v,bool) else None
       except:txt=str(v)
       c.execute('insert into test_data(test_id,section,field_name,value_text,value_num,unit) values(?,?,?,?,?,?)',(tid,section,k,txt,num,d.get('units',{}).get(k)))
    rn=nextno(c,'AST-R-','reports','id'); c.execute('insert into reports(report_no,test_id,status) values(?,?,?)',(rn,tid,'مسودة')); c.commit(); audit(u['id'],'إضافة اختبار','test',tid,f"{testno} - {cat['name_ar']}"); return self.send_json({'ok':True,'test_id':tid,'report_no':rn})
   return self.send_json({'error':'مسار غير معروف'},404)
  except sqlite3.IntegrityError as e:
   c.rollback(); return self.send_json({'error':'بيانات مكررة أو مرجع غير صحيح: '+str(e)},400)
  except Exception as e:
   c.rollback(); return self.send_json({'error':str(e)},400)
  finally:c.close()
 def create_proctor(self,c,u,d):
  cat=c.execute('select id from test_catalog where code=?',(d['standard_code'],)).fetchone();
  if not cat:return self.send_json({'error':'معيار البروكتور غير موجود'},400)
  testno=d.get('test_no') or nextno(c,'TST-','tests','id'); c.execute('insert into tests(test_no,sample_id,catalog_id,status,technician_id,started_at,completed_at) values(?,?,?,?,?,?,CURRENT_TIMESTAMP)',(testno,int(d['sample_id']),cat['id'],'مكتمل',u['id'],d.get('started_at'))); tid=c.execute('select last_insert_rowid()').fetchone()[0]
  for i,z in enumerate(d.get('points',[]),1): c.execute('insert into proctor_points(test_id,point_no,moisture,mold_soil_wet,wet_density,dry_density) values(?,?,?,?,?,?)',(tid,i,z['moisture'],z['mold_soil_wet'],z.get('wet_density'),z.get('dry_density')))
  c.execute('insert into proctor_results(test_id,mdd,omc) values(?,?,?)',(tid,d['mdd'],d['omc'])); rn=nextno(c,'AST-R-','reports','id'); c.execute('insert into reports(report_no,test_id,status) values(?,?,?)',(rn,tid,'مسودة')); c.commit(); audit(u['id'],'إضافة اختبار','test',tid,f"{testno} - {d['standard_code']}"); return self.send_json({'ok':True,'test_id':tid,'report_no':rn})

if __name__=='__main__':
 init(); print(f'LIMS مختبر أساس: http://127.0.0.1:{PORT}'); ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
