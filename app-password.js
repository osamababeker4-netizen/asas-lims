'use strict';

const $ = function(id) { return document.getElementById(id); };
const API_BASE_URL = String(window.LIMS_API_BASE_URL || '').replace(/\/+$/, '');
const STATIC_MODE = location.hostname.endsWith('github.io') && !API_BASE_URL;
const SAUDI_TIME_ZONE = 'Asia/Riyadh';
const SAUDI_LOCALE = 'ar-SA-u-ca-gregory';
function saudiNow() { return new Date().toLocaleString(SAUDI_LOCALE, {timeZone:SAUDI_TIME_ZONE,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}); }
function saudiToday() { const parts=new Intl.DateTimeFormat('en-CA',{timeZone:SAUDI_TIME_ZONE,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()); const values={}; parts.forEach(function(p){values[p.type]=p.value;}); return values.year+'-'+values.month+'-'+values.day; }
function saudiDisplay(value) { if (!value) return '—'; const raw=String(value); const normalized=/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(raw) ? raw.replace(' ','T')+'Z' : raw; const date=new Date(normalized); return Number.isNaN(date.getTime()) ? raw : date.toLocaleString(SAUDI_LOCALE,{timeZone:SAUDI_TIME_ZONE,dateStyle:'medium',timeStyle:'medium',hour12:false}); }
function updateSaudiClock(){ const el=$('saudiClock'); if(el) setText(el,'توقيت السعودية: '+saudiNow()); }
const STORAGE_KEY = 'asas_lims_v720';
const PROJECT_STATUSES = ['مخطط', 'نشط', 'موقوف', 'قيد المراجعة', 'معتمد', 'مكتمل'];
const BOARD_STATUSES = ['مخطط', 'نشط', 'قيد المراجعة', 'موقوف', 'مكتمل'];
const PRIORITIES = ['منخفضة', 'متوسطة', 'عالية', 'حرجة'];
const WORK_ORDER_STATUSES = ['مفتوح', 'قيد التنفيذ', 'بانتظار المراجعة', 'موقوف', 'مكتمل'];
const ROLE_NAMES = {admin:'مدير النظام',general_manager:'المدير العام',technical_manager:'المدير الفني',laboratory_manager:'مدير المختبر',quality_manager:'مدير الجودة',quality_officer:'مسؤول الجودة',calibration_officer:'مسؤول المعايرة',document_controller:'مسؤول الوثائق',manager:'مدير',technician:'فني مختبر',field:'مفتش ميداني',quality:'الجودة (قديم)'};
// الكتالوج الرسمي الموحد: يظهر في الموقع المركزي، ويطابق التطبيق الميداني.
const OFFICIAL_TEST_CATALOG = Object.freeze({
  'تربة':[
    ['D6913','التدرج الحبيبي بالغرابيل','Sieve Analysis'],['D7928','التدرج الحبيبي للهيدروميتر','Hydrometer Analysis'],['D2216','المحتوى المائي','Water Content'],['D4318','حدود أتربرج (LL / PL / PI)','Atterberg Limits'],['D854','الكثافة النوعية لحبيبات التربة','Specific Gravity'],['D698','الدمك القياسي (Standard Proctor)','Standard Proctor'],['D1557','الدمك المعدل (Modified Proctor)','Modified Proctor'],['D1883','نسبة التحمل كاليفورنيا CBR','California Bearing Ratio'],['D1556','كثافة الموقع بطريقة مخروط الرمل','Sand Cone Density'],['D6938','كثافة ورطوبة الموقع بالطريقة النووية','Nuclear Density and Moisture'],['D2487','تصنيف التربة الموحد USCS','USCS Classification'],['D2435','الانضغاط والهبوط أحادي البعد','One-Dimensional Consolidation'],['D3080','القص المباشر','Direct Shear'],['D2166','الانضغاط غير المحصور UCS','Unconfined Compression'],['D2850','الضغط ثلاثي المحاور غير الموحد UU','Triaxial UU'],['D4767','الضغط ثلاثي المحاور الموحد CU/CD','Triaxial CU/CD'],['D5084','النفاذية / التوصيل الهيدروليكي','Hydraulic Conductivity'],['D4546','الانتفاخ والانهيار','Swell and Collapse'],['D4972','الأس الهيدروجيني pH للتربة','Soil pH'],['D2974','المحتوى العضوي','Organic Content']
  ],
  'خرسانة':[
    ['C172','أخذ عينات الخرسانة الطازجة','Sampling Fresh Concrete'],['C143','الهبوط Slump','Slump'],['C1064','درجة حرارة الخرسانة الطازجة','Fresh Concrete Temperature'],['C138','الكثافة والعائد ومحتوى الهواء الوزني','Density Yield and Air Content'],['C231','محتوى الهواء بطريقة الضغط','Air Content by Pressure'],['C173','محتوى الهواء بالطريقة الحجمية','Air Content by Volumetric Method'],['C31','تجهيز ومعالجة العينات في الموقع','Making and Curing Specimens'],['C39','مقاومة الضغط للأسطوانات','Compressive Strength'],['C78','مقاومة الانحناء للكمرة','Flexural Strength'],['C496','مقاومة الشد بالانشطار','Splitting Tensile Strength'],['C469','معامل المرونة ونسبة بواسون','Elastic Modulus'],['C42','فحص اللباب الخرساني','Concrete Cores'],['C403','زمن الشك بالاختراق','Time of Setting'],['C597','النبضات فوق الصوتية UPV','Ultrasonic Pulse Velocity'],['C642','الكثافة والامتصاص والفراغات','Density Absorption and Voids'],['C157','الانكماش الطولي المتصلب','Length Change'],['C1202','نفاذية أيونات الكلوريد السريعة RCPT','Rapid Chloride Permeability'],['C1152','كلوريد الخرسانة المتصلبة','Water-Soluble Chloride'],['C666','مقاومة التجميد والذوبان','Freeze-Thaw Resistance'],['C1260','قابلية التفاعل القلوي للركام','Alkali Reactivity']
  ],
  'أسفلت':[
    ['D979','أخذ عينات الخلطات الأسفلتية','Sampling Asphalt Mixtures'],['D6926','تحضير عينات مارشال','Marshall Specimen Preparation'],['D6927','ثبات وانسياب مارشال','Marshall Stability and Flow'],['D2041','الكثافة النوعية العظمى النظرية Rice','Maximum Theoretical Specific Gravity'],['D2726','الكثافة النوعية والكثافة الظاهرية','Bulk Specific Gravity'],['D3203','الفراغات الهوائية في الخلطات','Air Voids'],['D6307','محتوى الأسفلت بفرن الإشعال','Asphalt Content by Ignition'],['D5444','التدرج الميكانيكي للركام المستخلص','Extracted Aggregate Gradation'],['D4867','الحساسية للرطوبة / الشد غير المباشر','Moisture Susceptibility'],['D6931','الكثافة في الموقع بالطريقة النووية','In-Place Density'],['D3549','السماكة أو الارتفاع للعينة المدموكة','Thickness of Compacted Specimens'],['D1188','الكثافة النوعية للعينات اللبية','Core Density'],['D6928','معامل المرونة للخلطات الأسفلتية','Resilient Modulus'],['D5','اختراق الرابط الأسفلتي','Bitumen Penetration'],['D36','نقطة تليّن الرابط الأسفلتي','Softening Point'],['D4402','اللزوجة الدورانية للرابط الأسفلتي','Rotational Viscosity'],['D2872','التقادم قصير الأجل RTFO','Rolling Thin-Film Oven'],['D6648','القص الديناميكي للرابط DSR','Dynamic Shear Rheometer']
  ]
});
const TEST_FIELDS = {
  D1883:[['cbr254','CBR عند 2.54 mm','%'],['cbr508','CBR عند 5.08 mm','%'],['swelling','الانتفاخ','%']],
  D2216:[['wet_mass','وزن العينة الرطبة','g'],['dry_mass','وزن العينة الجافة','g']],
  D4318:[['LL','حد السيولة LL','%'],['PL','حد اللدونة PL','%'],['PI','مؤشر اللدونة PI','%']],
  C136:[['sample_mass','كتلة العينة','g'],['FM','معامل النعومة','']],
  C39:[['load','الحمل الأقصى','kN'],['area','مساحة المقطع','mm²'],['strength','مقاومة الضغط','MPa']],
  C143:[['slump','الهبوط','mm']],
  D2041:[['mass_dry','كتلة العينة الجافة','g'],['mass_submerged','الكتلة المغمورة','g'],['Gmm','Gmm','']],
  D6132:[['DFT_avg','متوسط السماكة الجافة','µm']],
  D7091:[['DFT_avg','متوسط السماكة','µm']],
  'ROAD-PROFILER':[['IRI','IRI','m/km'],['roughness','وعورة الطريق',''],['distance','المسافة','km']],
  'GRB-ROUGHNESS':[['roughness','وعورة الأسفلت','']]
};

let catalog = [];
let dashboard = null;
let qualityData = {documents:[],proficiency:[],staff:[]};
let currentUser = null;
let centralAccessToken = sessionStorage.getItem('asas_lims_access_token') || '';
let pendingOtpLogin = null;
let projectView = 'table';
let fieldTests = [];
let fieldLat = null;
let fieldLng = null;
let toastTimer = null;
let refreshInFlight = null;
let realtimeTimer = null;
let userUpdatesChannel = null;
let eventStream = null;
const AUTH_ERRORS = {
  invalid_credentials:'اسم المستخدم أو كلمة المرور غير صحيحة.',
  phone_not_configured:'لا يوجد رقم جوال دولي مفعّل لهذا الحساب. تواصل مع مدير النظام.',
  otp_provider_not_configured:'خدمة رمز التحقق غير مهيأة على الخادم.',
  otp_provider_error:'تعذر إرسال رمز التحقق حالياً. حاول لاحقاً أو تواصل مع مدير النظام.',
  otp_whatsapp_unavailable:'تعذر الإرسال عبر WhatsApp. جرّب SMS أو الاتصال الصوتي، أو فعّل WhatsApp Verify في Twilio.',
  otp_call_unavailable:'تعذر الإرسال عبر الاتصال الصوتي. جرّب SMS أو تحقق من إعدادات Twilio.',
  otp_sms_unavailable:'تعذر إرسال SMS حالياً. جرّب الاتصال الصوتي أو تواصل مع مدير النظام.',
  invalid_otp_channel:'طريقة التحقق غير مدعومة.',
  invalid_otp:'رمز التحقق غير صحيح أو منتهي الصلاحية.',
  otp_resend_too_soon:'تم إرسال رمز مؤخراً. انتظر قليلاً ثم أعد المحاولة.'
};
let otpResendTimer = null;

function esc(value) {
  return String(value === null || value === undefined ? '' : value).replace(/[&<>"'\u0600-\u06ff]/g, function(char) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char] || '&#x'+char.codePointAt(0).toString(16)+';';
  });
}

function statusClass(value) {
  return String(value || '').replace(/\s+/g, '_');
}

function statusChip(value) {
  return '<span class="status ' + statusClass(value) + '">' + escUI(value || '—') + '</span>';
}

function priorityChip(value) {
  return '<span class="priority ' + statusClass(value) + '">' + escUI(value || 'متوسطة') + '</span>';
}

function today() {
  return saudiToday();
}

function localDB() {
  let data;
  try { data = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null'); } catch (error) { data = null; }
  if (!data) {
    data = {users:[],clients:[],projects:[],workOrders:[],samples:[],tests:[],reports:[],equipment:[],visits:[],catalog:[],audit:[],syncQueue:[]};
  }
  ['users','clients','projects','workOrders','samples','tests','reports','equipment','visits','catalog','audit','syncQueue'].forEach(function(key) {
    if (!Array.isArray(data[key])) data[key] = [];
  });
  data.catalog = mergeOfficialCatalog(data.catalog);
  return data;
}

function saveLocal(data) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  return data;
}

function defaultCatalog() {
  return Object.entries(OFFICIAL_TEST_CATALOG).flatMap(function(entry) {
    const category = entry[0], tests = entry[1];
    return tests.map(function(test, index) { return {id:index + 1,code:test[0],name_ar:test[1],name_en:test[2],category:category,standard:'ASTM ' + test[0],version:'معتمد'}; });
  });
}

function mergeOfficialCatalog(existing) {
  const rows = Array.isArray(existing) ? existing.slice() : [];
  defaultCatalog().forEach(function(official) {
    const current = rows.find(function(row) { return row.code === official.code; });
    if (current) Object.assign(current, official, {id:current.id});
    else rows.push(Object.assign({}, official, {id:localId(rows)}));
  });
  return rows;
}

function localId(items) {
  return items.length ? Math.max.apply(null, items.map(function(item) { return Number(item.id) || 0; })) + 1 : 1;
}

function localAudit(data, action, entity, details) {
  data.audit.unshift({id:localId(data.audit),created_at:saudiNow(),full_name:currentUser ? currentUser.full_name : 'محلي',action:action,entity:entity,details:details});
}

function localQueue(data, entity, entityId, operation) {
  data.syncQueue.unshift({id:localId(data.syncQueue),entity:entity,entity_id:entityId,operation:operation,status:'queued',attempts:0,created_at:saudiNow()});
}

function localProjectRows(data) {
  return data.projects.map(function(project) {
    const client = data.clients.find(function(item) { return item.id === Number(project.client_id); });
    const orders = data.workOrders.filter(function(item) { return item.project_id === project.id; });
    const samples = data.samples.filter(function(item) { return item.project_id === project.id; });
    const tests = data.tests.filter(function(item) { return samples.some(function(sample) { return sample.id === Number(item.sample_id); }); });
    const reports = data.reports.filter(function(item) { return tests.some(function(test) { return test.id === Number(item.test_id); }); });
    return Object.assign({}, project, {client_name:client ? client.name : '',work_orders_count:orders.length,samples_count:samples.length,tests_count:tests.length,reports_count:reports.length});
  });
}

function localDashboard(data) {
  const projects = localProjectRows(data);
  const orders = data.workOrders.map(function(order) {
    const project = data.projects.find(function(item) { return item.id === Number(order.project_id); });
    return Object.assign({}, order, {project_name:project ? project.name : '',project_code:project ? project.code : ''});
  });
  const samples = data.samples.map(function(sample) {
    const project = data.projects.find(function(item) { return item.id === Number(sample.project_id); });
    return Object.assign({}, sample, {project_name:project ? project.name : '',project_code:project ? project.code : ''});
  });
  const tests = data.tests.map(function(test) {
    const sample = data.samples.find(function(item) { return item.id === Number(test.sample_id); });
    const testCatalog = data.catalog.find(function(item) { return item.id === Number(test.catalog_id); }) || {};
    return Object.assign({}, test, {sample_no:sample ? sample.sample_no : '',code:testCatalog.code,name_ar:testCatalog.name_ar,standard:testCatalog.standard});
  });
  const reports = data.reports.map(function(report) {
    const test = tests.find(function(item) { return item.id === Number(report.test_id); }) || {};
    return Object.assign({}, report, {test_no:test.test_no,name_ar:test.name_ar,sample_no:test.sample_no});
  });
  return {
    counts:{projects:projects.length,work_orders:orders.length,samples:samples.length,tests:tests.length,reports:reports.length,equipment:data.equipment.length,field_visits:data.visits.length,sync_queue:data.syncQueue.length},
    projects:projects,work_orders:orders,clients:data.clients.slice().reverse(),samples:samples.slice().reverse().map(function(sample) { return Object.assign({}, sample, {planned_tests_count:(sample.test_plan || []).length}); }),tests:tests.slice().reverse(),reports:reports.slice().reverse(),equipment:data.equipment.slice().reverse(),audit:data.audit,activity:data.audit.slice(0,15),sync:data.syncQueue,
    alerts:{
      blocked_projects:projects.filter(function(item) { return item.status === 'موقوف'; }),
      overdue_work_orders:orders.filter(function(item) { return item.due_date && item.due_date < today() && item.status !== 'مكتمل'; }),
      awaiting_review:projects.filter(function(item) { return item.status === 'قيد المراجعة'; })
    }
  };
}

function staticWorkspace(data, projectId) {
  const project = localProjectRows(data).find(function(item) { return item.id === Number(projectId); });
  if (!project) return null;
  const samples = data.samples.filter(function(item) { return item.project_id === project.id; });
  const tests = data.tests.filter(function(item) { return samples.some(function(sample) { return sample.id === Number(item.sample_id); }); });
  return {
    project:project,
    work_orders:data.workOrders.filter(function(item) { return item.project_id === project.id; }),
    samples:samples,
    tests:tests.map(function(test) { const cat = data.catalog.find(function(item) { return item.id === Number(test.catalog_id); }) || {}; const sample = samples.find(function(item) { return item.id === Number(test.sample_id); }) || {}; return Object.assign({}, test, {name_ar:cat.name_ar,standard:cat.standard,sample_no:sample.sample_no}); }),
    results:tests.flatMap(function(test) { return Object.keys(test.results || {}).map(function(key) { return {test_no:test.test_no,name_ar:'نتيجة اختبار',field_name:key,value:test.results[key],unit:''}; }); }),
    reports:data.reports.filter(function(item) { return tests.some(function(test) { return test.id === Number(item.test_id); }); }),
    field_visits:data.visits.filter(function(item) { return item.project_id === project.id; })
  };
}

function staticApi(path, options) {
  const data = localDB();
  const body = options && options.body ? JSON.parse(options.body) : {};
  if (path === '/api/login') {
    const loginId = String(body.username || '').trim();
    const user = data.users.find(function(item) { return (item.username === loginId || item.phone === loginId) && item.password === String(body.password || '') && item.active; });
    if (!user) throw new Error(data.users.length ? 'اسم المستخدم أو كلمة المرور غير صحيحة' : 'أنشئ حساب المدير المحلي أولاً');
    currentUser = {id:user.id,username:user.username,full_name:user.full_name,role:user.role};
    localStorage.setItem(STORAGE_KEY + '_session', JSON.stringify(currentUser));
    return {ok:true,user:currentUser};
  }
  if (path === '/api/logout') {
    localStorage.removeItem(STORAGE_KEY + '_session');
    currentUser = null;
    return {ok:true};
  }
  if (path === '/api/auth/change-password') {
    const user = data.users.find(function(item) { return item.id === currentUser.id; });
    if (!user || user.password !== String(body.current_password || '')) throw new Error('كلمة المرور الحالية غير صحيحة');
    if (String(body.new_password || '').length < 12) throw new Error('كلمة المرور الجديدة يجب ألا تقل عن 12 حرفاً');
    if (body.new_password !== body.confirm_password) throw new Error('تأكيد كلمة المرور غير مطابق');
    user.password = body.new_password; localAudit(data,'تغيير كلمة المرور الذاتية','user',user.id,user.username); saveLocal(data); return {ok:true};
  }
  if (!currentUser) throw new Error('غير مسجل الدخول');
  if (path === '/api/catalog') return data.catalog;
  if (path === '/api/dashboard') return localDashboard(data);
  if (path === '/api/projects') {
    if (!options || !options.method || options.method === 'GET') return localProjectRows(data);
    const id = localId(data.projects);
    const project = Object.assign({id:id,code:'PR-' + String(id).padStart(6,'0'),status:'مخطط',priority:'متوسطة',progress:0,created_at:saudiNow()}, body);
    project.client_id = project.client_id ? Number(project.client_id) : null;
    project.manager_id = project.manager_id ? Number(project.manager_id) : null;
    project.progress = Math.min(100,Math.max(0,Number(project.progress) || 0));
    data.projects.push(project); localQueue(data,'project',id,'create'); localAudit(data,'إضافة مشروع','project',project.code + ' - ' + project.name); saveLocal(data);
    return {ok:true,id:id,code:project.code};
  }
  if (path === '/api/projects/update') {
    const project = data.projects.find(function(item) { return item.id === Number(body.id); });
    if (!project) throw new Error('المشروع غير موجود');
    Object.assign(project, body, {client_id:body.client_id ? Number(body.client_id) : null,manager_id:body.manager_id ? Number(body.manager_id) : null,progress:Math.min(100,Math.max(0,Number(body.progress) || 0))});
    localQueue(data,'project',project.id,'update'); localAudit(data,'تعديل مشروع','project',project.code); saveLocal(data); return {ok:true};
  }
  if (path === '/api/projects/status') {
    const project = data.projects.find(function(item) { return item.id === Number(body.id); });
    if (!project) throw new Error('المشروع غير موجود');
    project.status = body.status; if (body.status === 'معتمد') project.progress = 100;
    localQueue(data,'project',project.id,'status'); localAudit(data,'تغيير حالة مشروع','project',project.code + ' → ' + body.status); saveLocal(data); return {ok:true};
  }
  if (path.indexOf('/api/projects/') === 0 && path.endsWith('/workspace')) {
    return staticWorkspace(data, path.split('/')[3]);
  }
  if (path === '/api/work-orders') {
    if (!options || !options.method || options.method === 'GET') return data.workOrders;
    const id = localId(data.workOrders);
    const order = Object.assign({id:id,order_no:'WO-' + String(id).padStart(6,'0'),status:'مفتوح',priority:'متوسطة',created_at:saudiNow()}, body, {project_id:Number(body.project_id)});
    data.workOrders.push(order); localQueue(data,'work_order',id,'create'); localAudit(data,'إضافة أمر عمل','work_order',order.order_no + ' - ' + order.title); saveLocal(data); return {ok:true,id:id,order_no:order.order_no};
  }
  if (path === '/api/clients') {
    const id = localId(data.clients); data.clients.push(Object.assign({id:id},body)); localAudit(data,'إضافة عميل','client',body.name); saveLocal(data); return {ok:true,id:id};
  }
  if (path === '/api/samples') {
    const id = localId(data.samples); const sample = Object.assign({id:id,status:'قيد الاختبار',project_id:body.project_id ? Number(body.project_id) : null},body);
    sample.test_plan = data.catalog.filter(function(item) { return item.category === sample.material; }).map(function(item) { return {catalog_id:item.id,code:item.code,name_ar:item.name_ar,status:'مخطط'}; });
    data.samples.push(sample); localQueue(data,'sample',id,'create'); localAudit(data,'إضافة عينة وخطة اختبارات تلقائية','sample',body.sample_no + ' (' + sample.test_plan.length + ' اختباراً)'); saveLocal(data); return {ok:true,id:id,planned_count:sample.test_plan.length};
  }
  if (path === '/api/equipment') {
    const id = localId(data.equipment); data.equipment.push(Object.assign({id:id,status:'ساري'},body)); localAudit(data,'إضافة جهاز','equipment',body.name); saveLocal(data); return {ok:true,id:id};
  }
  if (path === '/api/tests/generic' || path === '/api/tests/proctor') {
    const id = localId(data.tests); const code = body.standard_code || (data.catalog.find(function(item) { return item.id === Number(body.catalog_id); }) || {}).code; const cat = data.catalog.find(function(item) { return item.code === code; }) || {};
    const test = {id:id,test_no:body.test_no || 'TST-' + String(id).padStart(6,'0'),sample_id:Number(body.sample_id),catalog_id:cat.id,status:'مكتمل',results:body.results || {mdd:body.mdd,omc:body.omc},mdd:body.mdd,omc:body.omc};
    data.tests.push(test); const reportId = localId(data.reports); const report = {id:reportId,report_no:'AST-R-' + String(reportId).padStart(6,'0'),test_id:id,status:'مسودة',issued_at:saudiNow()}; data.reports.push(report); localQueue(data,'test',id,'create'); localAudit(data,'إضافة اختبار','test',test.test_no); saveLocal(data); return {ok:true,test_id:id,report_no:report.report_no};
  }
  if (path.indexOf('/api/report/') === 0) {
    const test = data.tests.find(function(item) { return item.id === Number(path.split('/').pop()); }) || {}; const report = data.reports.find(function(item) { return item.test_id === test.id; }) || {}; const cat = data.catalog.find(function(item) { return item.id === test.catalog_id; }) || {}; const sample = data.samples.find(function(item) { return item.id === Number(test.sample_id); }) || {};
    return Object.assign({},report,test,{name_ar:cat.name_ar,standard:cat.standard,sample_no:sample.sample_no,data:{inputs:{},results:test.results || {}},lab_name:'مختبر أساس'});
  }
  if (path === '/api/reports/status') {
    const report = data.reports.find(function(item) { return item.id === Number(body.id); }); if (!report) throw new Error('التقرير غير موجود'); report.status = body.status; localAudit(data,'تغيير حالة تقرير','report',report.report_no + ' → ' + body.status); saveLocal(data); return {ok:true};
  }
  if (path === '/api/field/search') {
    const license = decodeURIComponent((path.split('license=')[1] || '')); return data.visits.filter(function(item) { return item.license_no === license; }).slice(-20).reverse();
  }
  if (path === '/api/field/recent') return data.visits.slice().reverse().slice(0,30);
  if (path === '/api/field/visits') {
    const id = localId(data.visits); data.visits.push(Object.assign({id:id,status:'مسودة',created_at:saudiNow(),full_name:currentUser.full_name},body,{project_id:body.project_id ? Number(body.project_id) : null,sample_id:body.sample_id ? Number(body.sample_id) : null})); localQueue(data,'field_visit',id,'create'); localAudit(data,'إضافة زيارة ميدانية','field_visit',body.license_no); saveLocal(data); return {ok:true,id:id};
  }
  if (path === '/api/field/status') {
    const visit = data.visits.find(function(item) { return item.id === Number(body.id); }); if (!visit) throw new Error('الزيارة غير موجودة'); visit.status = body.status; localAudit(data,'تغيير حالة زيارة','field_visit',String(visit.id)); saveLocal(data); return {ok:true};
  }
  if (path === '/api/users') {
    if (!options || !options.method || options.method === 'GET') return data.users.map(function(item) { return {id:item.id,username:item.username,full_name:item.full_name,role:item.role,phone:item.phone || '',active:item.active,created_at:item.created_at}; });
  }
  if (path === '/api/users/create') {
    const username = String(body.username || '').trim();
    const password = String(body.password || '');
    if (!username || !String(body.full_name || '').trim() || password.length < 12) throw new Error('أكمل بيانات المستخدم واجعل كلمة المرور 12 حرفاً على الأقل');
    if (data.users.some(function(item) { return item.username === username; })) throw new Error('اسم المستخدم مستخدم بالفعل');
    const id = localId(data.users); data.users.push({id:id,username:username,password:password,full_name:String(body.full_name).trim(),role:body.role || 'technician',phone:String(body.phone || '').trim(),active:1,created_at:saudiNow()}); localQueue(data,'user',id,'create'); localAudit(data,'إضافة مستخدم','user',username); saveLocal(data); return {ok:true,id:id,sync:'queued'};
  }
  if (path === '/api/users/update') {
    const user = data.users.find(function(item) { return item.id === Number(body.id); }); if (!user) throw new Error('المستخدم غير موجود');
    const password = String(body.password || '');
    if (!String(body.full_name || '').trim()) throw new Error('الاسم الكامل مطلوب');
    if (password && password.length < 12) throw new Error('كلمة المرور يجب ألا تقل عن 12 حرفاً');
    user.full_name = String(body.full_name).trim(); user.role = body.role || user.role; user.phone = String(body.phone || '').trim(); user.active = body.active ? 1 : 0;
    if (password) user.password = password;
    localQueue(data,'user',user.id,'update'); localAudit(data,'تعديل مستخدم','user',user.username); saveLocal(data); return {ok:true,id:user.id,sync:'queued'};
  }
  throw new Error('المسار غير مدعوم في العرض الثابت');
}

async function api(path, options) {
  const opts = options || {};
  if (STATIC_MODE) return staticApi(path, opts);
  const headers = Object.assign({'Content-Type':'application/json'}, opts.headers || {});
  if (centralAccessToken) headers.Authorization = 'Bearer ' + centralAccessToken;
  const response = await fetch(API_BASE_URL + path, Object.assign({}, opts, {credentials:'include', headers:headers}));
  let payload = {};
  try { payload = await response.json(); } catch (error) { throw new Error('استجابة غير صالحة من الخادم'); }
  if (response.status === 401 && currentUser) {
    stopLiveUpdates();
    centralAccessToken = '';
    sessionStorage.removeItem('asas_lims_access_token');
    currentUser = null;
    $('app').classList.add('hidden');
    $('login').classList.remove('hidden');
    $('loginForm').classList.remove('hidden');
    $('loginPassword').value = '';
    setText($('loginMessage'), 'انتهت جلسة الحماية. سجّل الدخول مجددًا ثم أضف أو عدّل المستخدم.');
  }
  if (!response.ok) throw new Error(AUTH_ERRORS[payload.error] || payload.error || 'تعذر تنفيذ العملية');
  return payload;
}

function showToast(message, isError) {
  const toast = $('toast');
  setText(toast, message);
  toast.className = 'toast ' + (isError ? 'error' : 'success');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function() { toast.className = 'toast hidden'; }, 4200);
}

function modal(html) {
  setHtml($('modalBody'), html);
  $('modal').classList.remove('hidden');
}

function closeModal() {
  $('modal').classList.add('hidden');
  setHtml($('modalBody'), '');
}

function fieldValue(form, key) {
  const element = form.elements[key];
  return element ? element.value.trim() : '';
}

function optionList(items, selected, label, value) {
  return items.map(function(item) {
    const itemValue = value(item);
    return '<option value="' + esc(itemValue) + '"' + (String(itemValue) === String(selected || '') ? ' selected' : '') + '>' + ((typeof item === 'string' || item.name_ar) ? escUI(label(item)) : esc(label(item))) + '</option>';
  }).join('');
}

function navigate(page) {
  document.querySelectorAll('.page').forEach(function(element) { element.classList.remove('active'); });
  const target = $(page);
  if (!target) return;
  target.classList.add('active');
  document.querySelectorAll('.nav-link[data-page]').forEach(function(button) { button.classList.toggle('active', button.dataset.page === page); });
  const nav = document.querySelector('.nav-link[data-page="' + page + '"]');
  setText($('pageTitle'), nav ? ((uiTextMemory.get(nav.firstChild) || {}).ar || nav.textContent).trim() : 'أساس LIMS');
  setText($('pageKicker'), page === 'projects' ? 'تنفيذ ومتابعة' : 'إدارة المختبر');
  $('sidebar').classList.remove('open');
  if (page === 'field') loadFieldRecent();
}

async function login(event) {
  event.preventDefault();
  try {
    const form = event.currentTarget || $('loginForm');
    const usernameInput = form && form.querySelector('[name="username"], #loginUsername');
    const passwordInput = form && form.querySelector('[name="password"], #loginPassword');
    if (!usernameInput || !passwordInput) throw new Error('تعذر تحميل حقول الدخول. حدّث الصفحة ثم أعد المحاولة.');
    const username = usernameInput.value.trim();
    const password = passwordInput.value;
    if (!username || !password) throw new Error('أدخل اسم المستخدم وكلمة المرور.');
    if (STATIC_MODE) return await completeLogin(await api('/api/login', {method:'POST',body:JSON.stringify({username:username,password:password})}));
    const result = await api('/api/auth/login', {method:'POST',body:JSON.stringify({username:username,password:password})});
    centralAccessToken = result.token;
    sessionStorage.setItem('asas_lims_access_token', centralAccessToken);
    $('loginPassword').value = '';
    await completeLogin({user:{full_name:result.user.name,role:result.user.role,username:result.user.username,phone:result.user.phone}});
  } catch (error) {
    setText($('loginMessage'), error.message);
  }
}

async function verifyOtpLogin(event) {
  event.preventDefault();
  if (!pendingOtpLogin) return;
  try {
    const otp = $('loginOtp').value.trim();
    if (!/^\d{6}$/.test(otp)) throw new Error('أدخل رمز OTP مكوّناً من 6 أرقام.');
    const result = await api('/api/auth/verify', {method:'POST',body:JSON.stringify({username:pendingOtpLogin.username,otp:otp})});
    centralAccessToken = result.token;
    sessionStorage.setItem('asas_lims_access_token', centralAccessToken);
    pendingOtpLogin = null;
    await completeLogin({user:{full_name:result.user.name,role:result.user.role,username:result.user.username,phone:result.user.phone}});
  } catch (error) { setText($('loginMessage'), error.message); }
}

function setOtpResendCooldown(seconds) {
  const button = $('resendOtp');
  clearInterval(otpResendTimer);
  let remaining = seconds;
  button.disabled = true;
  setText(button, 'إعادة الإرسال (' + remaining + ' ث)');
  otpResendTimer = setInterval(function() {
    remaining -= 1;
    if (remaining <= 0) {
      clearInterval(otpResendTimer);
      button.disabled = false;
      setText(button, 'إعادة إرسال الرمز');
    } else setText(button, 'إعادة الإرسال (' + remaining + ' ث)');
  }, 1000);
}

function chooseOtpChannel(channel, message) {
  if (!pendingOtpLogin) return;
  $('loginUsername').value = pendingOtpLogin.username;
  setText($('loginMessage'), message);
  $('loginForm').classList.remove('hidden');
  $('otpForm').classList.add('hidden');
  $('loginForm').dataset.otpChannel = channel;
  $('loginPassword').focus();
}

async function completeLogin(result) {
  currentUser = result.user;
  $('login').classList.add('hidden');
  $('app').classList.remove('hidden');
  setHtml($('currentUser'), esc(result.user.full_name) + ' — ' + escUI(ROLE_NAMES[result.user.role] || result.user.role));
  // The API authorizes both administrators and managers to manage users.
  // Keep the navigation aligned with that server-side permission so a
  // manager is not blocked by a hidden page despite being authorized.
  $('usersNav').classList.toggle('hidden', ['admin','general_manager','manager'].indexOf(result.user.role) < 0);
  $('qualityNav').classList.toggle('hidden', ['admin','general_manager','manager','quality_manager','quality_officer','calibration_officer','document_controller','quality'].indexOf(result.user.role) < 0);
  $('qualityEquipmentCard').classList.toggle('hidden', ['admin','general_manager','manager','quality_manager','technical_manager','laboratory_manager'].indexOf(result.user.role) < 0);
  await loadCatalog(); await refresh(); startLiveUpdates(); navigate('dashboard');
}

async function logout() {
  stopLiveUpdates();
  try { await api('/api/logout', {method:'POST'}); } catch (error) {}
  centralAccessToken = ''; sessionStorage.removeItem('asas_lims_access_token'); location.reload();
}

async function bootstrapStaticAdmin() {
  $('staticSetup').classList.add('hidden');
  $('staticSetupForm').classList.remove('hidden');
  $('setupUsername').focus();
}

async function submitStaticAdmin(event) {
  event.preventDefault();
  const username = $('setupUsername').value.trim();
  const name = $('setupFullName').value.trim();
  const password = $('setupPassword').value;
  const confirmation = $('setupPasswordConfirm').value;
  if (!username || !name) return setText($('loginMessage'), 'أدخل اسم المستخدم والاسم الكامل.');
  if (password.length < 12) return setText($('loginMessage'), 'كلمة المرور يجب ألا تقل عن 12 حرفاً.');
  if (password !== confirmation) return setText($('loginMessage'), 'تأكيد كلمة المرور غير مطابق.');
  const data = localDB();
  if (data.users.length) return setText($('loginMessage'), 'الحساب المحلي موجود بالفعل. سجّل الدخول.');
  const phone = $('setupPhone').value.trim();
  if (phone && !/^\+\d{8,15}$/.test(phone)) return setText($('loginMessage'), 'رقم الجوال يجب أن يكون بصيغة دولية مثل +9665XXXXXXXX.');
  data.users.push({id:1,username:username.trim(),password:password,full_name:name.trim(),phone:phone,role:'admin',active:1,created_at:saudiNow()});
  saveLocal(data);
  $('staticSetupForm').classList.add('hidden');
  $('loginUsername').value = username;
  $('loginPassword').value = '';
  setText($('loginMessage'), 'تم إنشاء الحساب المحلي. سجّل الدخول الآن.');
}

async function loadCatalog() {
  catalog = await api('/api/catalog');
  renderCatalog();
}

async function refresh() {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async function() {
    dashboard = await api('/api/dashboard');
    renderDashboard();
    renderProjects();
    renderWorkOrders();
    renderClients();
    renderSamples();
    renderTests();
    renderReports();
    renderWhatsappDrafts();
    renderEquipment();
    renderAudit();
    if (currentUser && ['admin','general_manager','manager','quality_manager','quality_officer','calibration_officer','document_controller','quality'].indexOf(currentUser.role) >= 0) await renderQuality();
    if (currentUser && ['admin','general_manager','manager'].indexOf(currentUser.role) >= 0) await renderUsers();
  })();
  try { return await refreshInFlight; } finally { refreshInFlight = null; }
}

function publishLiveUpdate(entity) {
  if (userUpdatesChannel) userUpdatesChannel.postMessage({entity:entity,at:Date.now()});
}

function stopLiveUpdates() {
  if (realtimeTimer) clearInterval(realtimeTimer);
  realtimeTimer = null;
  if (eventStream) eventStream.close();
  eventStream = null;
  if (userUpdatesChannel) userUpdatesChannel.close();
  userUpdatesChannel = null;
}

function startLiveUpdates() {
  stopLiveUpdates();
  if (STATIC_MODE) return;
  if ('BroadcastChannel' in window) {
    userUpdatesChannel = new BroadcastChannel('asas-lims-central-updates');
    userUpdatesChannel.onmessage = function() {
      if (currentUser) refresh().catch(function() {});
    };
  }
  // EventSource is enabled only for the same Render origin. It uses the
  // HttpOnly session cookie, never exposes an access token in a URL, and
  // causes every connected device to refresh immediately after user changes.
  if (!API_BASE_URL || new URL(API_BASE_URL || location.origin, location.origin).origin === location.origin) {
    eventStream = new EventSource((API_BASE_URL || '') + '/api/events');
    eventStream.onmessage = function() {
      if (currentUser) refresh().catch(function() {});
    };
    eventStream.onerror = function() { /* EventSource reconnects automatically. */ };
  }
  // Same-browser updates are immediate. The short visible-page refresh keeps
  // separate devices aligned with the central service without sending secrets.
  realtimeTimer = setInterval(function() {
    if (currentUser && !document.hidden) refresh().catch(function() {});
  }, 12000);
}

function renderDashboard() {
  if (!dashboard) return;
  setText($('metricProjects'), dashboard.projects.filter(function(item) { return ['نشط','قيد المراجعة','موقوف'].indexOf(item.status) >= 0; }).length);
  setText($('metricOrders'), dashboard.counts.work_orders || 0);
  setText($('metricSamples'), dashboard.counts.samples || 0);
  setText($('metricReports'), dashboard.counts.reports || 0);
  setText($('metricReview'), (dashboard.alerts.awaiting_review || []).length);
  setText($('metricSync'), dashboard.counts.sync_queue || 0);
  setText($('metricWhatsapp'), dashboard.counts.whatsapp_drafts || 0);
  const pending = dashboard.counts.sync_queue || 0;
  const drafts = dashboard.counts.whatsapp_drafts || 0;
  setText($('syncIndicator'), 'المزامنة المباشرة: متصلة' +
    (pending ? ' · ' + pending + ' عملية مسجلة' : '') +
    (drafts ? ' · ' + drafts + ' مسودة بانتظار المراجعة' : ''));
  const priorities = [];
  (dashboard.alerts.overdue_work_orders || []).forEach(function(item) { priorities.push('<div class="priority-item overdue"><strong>أمر متأخر: ' + esc(item.order_no) + ' — ' + esc(item.title) + '</strong><small>' + esc(item.project_code) + ' · استحقاق ' + esc(item.due_date) + '</small></div>'); });
  (dashboard.alerts.blocked_projects || []).forEach(function(item) { priorities.push('<div class="priority-item blocked"><strong>مشروع متوقف: ' + esc(item.code) + ' — ' + esc(item.name) + '</strong><small>الأولوية ' + escUI(item.priority) + (item.due_date ? ' · الاستحقاق ' + esc(item.due_date) : '') + '</small></div>'); });
  (dashboard.alerts.awaiting_review || []).forEach(function(item) { priorities.push('<div class="priority-item"><strong>ينتظر المراجعة: ' + esc(item.code || item.name) + '</strong><small>' + esc(item.name || item.entity) + '</small></div>'); });
  setHtml($('priorityList'), priorities.join('') || '<div class="empty">لا توجد أولويات متأخرة أو عوائق حالياً.</div>');
  setHtml($('activityList'), (dashboard.activity || []).map(function(item) { return '<div class="timeline-item"><strong>' + escUI(item.action) + '</strong><small>' + esc(saudiDisplay(item.created_at)) + ' · ' + esc(item.details || '') + '</small></div>'; }).join('') || '<div class="empty">لا توجد عمليات بعد.</div>');
  setHtml($('dashboardProjects'), dashboard.projects.slice(0,6).map(function(project) {
    return '<button class="compact-project text-btn" type="button" data-project-open="' + project.id + '"><h4>' + esc(project.code) + ' — ' + esc(project.name) + '</h4><p>' + statusChip(project.status) + ' · ' + esc(project.samples_count) + ' عينة · ' + esc(project.reports_count) + ' تقرير</p></button>';
  }).join('') || '<div class="empty">ابدأ بإضافة مشروع.</div>');
}

function filteredProjects() {
  const search = $('projectSearch').value.trim().toLowerCase();
  const priority = $('projectPriorityFilter').value;
  return (dashboard ? dashboard.projects : []).filter(function(project) {
    const text = [project.code,project.name,project.client_name,project.location].join(' ').toLowerCase();
    return (!search || text.indexOf(search) >= 0) && (!priority || project.priority === priority);
  });
}

function renderProjects() {
  if (!dashboard) return;
  const projects = filteredProjects();
  setHtml($('projectsTable'), projects.map(function(project) {
    return '<tr><td><strong>' + esc(project.code) + '</strong><small>' + esc(project.name) + '</small></td><td>' + esc(project.client_name || '—') + '<small>' + (project.location ? esc(project.location) : escUI('بدون موقع')) + '</small></td><td>' + priorityChip(project.priority) + '</td><td>' + (project.due_date ? esc(project.due_date) : escUI('غير محدد')) + '</td><td><div class="progress"><span style="width:' + Math.min(100,Math.max(0,Number(project.progress) || 0)) + '%"></span></div><small>' + esc(project.progress || 0) + '%</small></td><td><select class="project-status" data-project-id="' + project.id + '">' + optionList(PROJECT_STATUSES, project.status, function(value) { return value; }, function(value) { return value; }) + '</select></td><td><small>' + esc(project.work_orders_count) + ' أمر · ' + esc(project.samples_count) + ' عينة</small><small>' + esc(project.tests_count) + ' اختبار · ' + esc(project.reports_count) + ' تقرير</small></td><td><div class="row-actions"><button class="text-btn" data-project-open="' + project.id + '" type="button">مساحة العمل</button><button class="text-btn" data-project-edit="' + project.id + '" type="button">تعديل</button></div></td></tr>';
  }).join('') || '<tr><td colspan="8" class="empty">لا توجد مشاريع مطابقة.</td></tr>');
  renderBoard(projects);
  renderRoadmap(projects);
}

function renderBoard(projects) {
  setHtml($('projectBoard'), BOARD_STATUSES.map(function(status) {
    const cards = projects.filter(function(project) { return project.status === status; }).map(function(project) {
      return '<article class="kanban-card"><h4>' + esc(project.code) + ' — ' + esc(project.name) + '</h4><p>' + (project.client_name ? esc(project.client_name) : escUI('بدون عميل')) + '</p><div class="progress"><span style="width:' + Math.min(100,Number(project.progress) || 0) + '%"></span></div><div class="kanban-meta">' + priorityChip(project.priority) + '<span>' + (project.due_date ? esc(project.due_date) : escUI('بلا تاريخ')) + '</span></div><select class="project-status" data-project-id="' + project.id + '">' + optionList(PROJECT_STATUSES,project.status,function(value) { return value; },function(value) { return value; }) + '</select></article>';
    }).join('') || '<div class="empty">لا توجد مشاريع</div>';
    return '<section class="kanban-column"><h3>' + escUI(status) + '</h3><div class="kanban-stack">' + cards + '</div></section>';
  }).join(''));
}

function renderRoadmap(projects) {
  const dated = projects.slice().sort(function(a,b) { return String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')); });
  setHtml($('projectRoadmap'), dated.map(function(project) {
    const progress = Math.min(100,Math.max(0,Number(project.progress) || 0));
    return '<article class="roadmap-row"><div><h4>' + esc(project.code) + ' — ' + esc(project.name) + '</h4><small>' + (project.start_date ? esc(project.start_date) : escUI('بلا بداية')) + ' ← ' + (project.due_date ? esc(project.due_date) : escUI('بلا استحقاق')) + '</small></div><div class="roadmap-track"><span style="width:' + progress + '%"></span></div><div>' + statusChip(project.status) + '<small>' + progress + '% مكتمل</small></div></article>';
  }).join('') || '<div class="empty">أضف تواريخ بداية واستحقاق للمشاريع لإظهار خارطة الطريق.</div>');
}

function setProjectView(view) {
  projectView = view;
  document.querySelectorAll('.view-btn').forEach(function(button) { button.classList.toggle('active', button.dataset.projectView === view); });
  $('projectTableView').classList.toggle('hidden', view !== 'table');
  $('projectBoardView').classList.toggle('hidden', view !== 'board');
  $('projectRoadmapView').classList.toggle('hidden', view !== 'roadmap');
}

function renderWorkOrders() {
  setHtml($('workOrdersTable'), (dashboard ? dashboard.work_orders : []).map(function(order) {
    return '<tr><td><strong>' + esc(order.order_no) + '</strong></td><td>' + esc(order.title) + '<small>' + esc(order.description || '') + '</small></td><td>' + esc(order.project_code) + '<small>' + esc(order.project_name) + '</small></td><td>' + (order.assignee_name ? esc(order.assignee_name) : escUI('غير محدد')) + '</td><td>' + priorityChip(order.priority) + '</td><td>' + esc(order.due_date || '—') + '</td><td>' + statusChip(order.status) + '</td></tr>';
  }).join('') || '<tr><td colspan="7" class="empty">لا توجد أوامر عمل.</td></tr>');
}

function renderClients() {
  setHtml($('clientsTable'), (dashboard ? dashboard.clients : []).map(function(client) { return '<tr><td>' + esc(client.name) + '</td><td>' + esc(client.phone || '') + '</td><td>' + esc(client.email || '') + '</td></tr>'; }).join('') || '<tr><td colspan="3" class="empty">لا يوجد عملاء.</td></tr>');
}

function renderSamples() {
  setHtml($('samplesTable'), (dashboard ? dashboard.samples : []).map(function(sample) { return '<tr><td><strong>' + esc(sample.sample_no) + '</strong></td><td>' + esc(sample.project_code || '—') + '<small>' + esc(sample.project_name || '') + '</small></td><td>' + escUI(sample.material) + '</td><td>' + esc(sample.planned_tests_count || 0) + ' اختباراً تلقائياً</td><td>' + esc(sample.received_date) + '</td><td>' + statusChip(sample.status) + '</td></tr>'; }).join('') || '<tr><td colspan="6" class="empty">لا توجد عينات.</td></tr>');
}

function renderTests() {
  setHtml($('testsTable'), (dashboard ? dashboard.tests : []).map(function(test) {
    const result = test.mdd !== null && test.mdd !== undefined ? 'MDD ' + Number(test.mdd).toFixed(3) + ' / OMC ' + Number(test.omc).toFixed(2) + '%' : '—';
    const canAssign = currentUser && ['admin','manager'].indexOf(currentUser.role) >= 0;
    return '<tr><td><strong>' + esc(test.test_no) + '</strong></td><td>' + esc(test.sample_no) + '</td><td>' + escUI(test.name_ar) + '<small>' + esc(test.code) + '</small></td><td>' + esc(test.standard) + '</td><td>' + escUI(test.technician_name || 'غير مسند') + '</td><td>' + esc(result) + '</td><td>' + statusChip(test.status) + '</td><td>' + (canAssign ? '<button class="text-btn" data-test-assign="' + test.id + '" type="button">إسناد لفني</button>' : '—') + '</td></tr>';
  }).join('') || '<tr><td colspan="8" class="empty">لا توجد اختبارات.</td></tr>');
}

function renderWhatsappDrafts() {
  const drafts = dashboard ? (dashboard.whatsapp_drafts || []) : [];
  const canReview = currentUser && ['admin','manager'].indexOf(currentUser.role) >= 0;
  setHtml($('whatsappDraftsTable'), drafts.map(function(draft) {
    const action = '<button class="text-btn" data-whatsapp-copy="' + draft.id + '" type="button">نسخ المسودة</button>' +
      (canReview && draft.status === 'draft' ? '<button class="text-btn" data-whatsapp-ready="' + draft.id + '" type="button">اعتماد للمشاركة</button>' : '');
    return '<tr><td>' + esc(draft.recipient_name || draft.target_name) + '</td><td>' + esc(draft.related_entity) + ' #' + esc(draft.related_id || '') + '</td><td><small>' + esc(draft.message_text) + '</small></td><td>' + statusChip(draft.status === 'ready' ? 'جاهزة للمشاركة' : 'مسودة') + '</td><td><div class="row-actions">' + action + '</div></td></tr>';
  }).join('') || '<tr><td colspan="5" class="empty">لا توجد مسودات بعد.</td></tr>');
}

function renderCatalog() {
  const query = $('catalogSearch') ? $('catalogSearch').value.toLowerCase() : '';
  setHtml($('catalogTable'), catalog.filter(function(item) { return [item.code,item.name_ar,item.name_en,item.standard,item.category].join(' ').toLowerCase().indexOf(query) >= 0; }).map(function(item) {
    const fileLink = function(id,label){return id ? '<a class="text-btn" target="_blank" rel="noopener" href="'+esc(API_BASE_URL+'/api/attachments/files/'+id)+'">'+label+'</a>' : '';};
    const resources = [fileLink(item.astm_attachment_id,'ASTM'),fileLink(item.worksheet_attachment_id,'Work Sheet'),fileLink(item.results_attachment_id,'Excel النتائج')].filter(Boolean).join(' ');
    const canManage = currentUser && ['admin','general_manager','manager','quality_manager','quality_officer','document_controller','quality'].indexOf(currentUser.role) >= 0;
    return '<tr><td>' + esc(item.code) + '</td><td>' + escUI(item.name_ar) + '<small>' + esc(item.name_en || '') + '</small></td><td>' + escUI(item.category) + '</td><td>' + esc(item.standard) + '</td><td>' + esc(item.version || '—') + '</td><td><div class="row-actions">'+(resources || '—')+(canManage ? '<button class="text-btn" data-catalog-resources="'+item.id+'">إدارة الملفات</button>' : '')+'</div></td></tr>';
  }).join('') || '<tr><td colspan="6" class="empty">لا توجد نتائج.</td></tr>');
}

function openCatalogResources(id) { const item=catalog.find(function(x){return x.id===Number(id);});if(!item)return;modal('<h2>ملفات '+esc(item.code)+'</h2><p>ارفع النسخة المرخّصة من مواصفة ASTM وWork Sheet وExcel النتائج. تظل الملفات متاحة للقراءة والتنزيل حسب الصلاحيات.</p><form id="catalogResourcesForm"><input type="hidden" name="catalog_id" value="'+item.id+'"><div class="modal-grid"><label>مواصفة ASTM (PDF أو Word)<input name="astm" type="file" accept=".pdf,.doc,.docx"></label><label>Work Sheet (PDF أو Word أو Excel)<input name="worksheet" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx"></label><label>Excel الاختبارات والنتائج<input name="results" type="file" accept=".xls,.xlsx,.pdf"></label></div><p class="form-note">الحجم الأقصى لكل ملف 25MB. اترك الحقل فارغًا للإبقاء على الملف الحالي.</p><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ الملفات</button></div></form>'); }
async function submitCatalogResources(form) { const catalogId=form.elements.catalog_id.value; let count=0; for(const type of ['astm','worksheet','results']) { const file=form.elements[type].files[0]; if(!file)continue; if(file.size>25*1024*1024)throw new Error('حجم '+file.name+' يتجاوز 25MB'); const bytes=new Uint8Array(await file.arrayBuffer()); let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode.apply(null,bytes.subarray(i,i+8192));await api('/api/catalog/resources',{method:'POST',body:JSON.stringify({catalog_id:catalogId,resource_type:type,file_name:file.name,file_base64:btoa(binary)})});count++; } if(!count)throw new Error('اختر ملفًا واحدًا على الأقل');closeModal();await refresh();showToast('تم ربط ملفات الاختبار بدليل الجودة'); }

function renderReports() {
  setHtml($('reportsTable'), (dashboard ? dashboard.reports : []).map(function(report) {
    return '<tr><td><strong>' + esc(report.report_no) + '</strong></td><td>' + esc(report.sample_no || '') + '<small>' + escUI(report.name_ar) + ' · ' + esc(report.test_no) + '</small></td><td>' + statusChip(report.status) + '</td><td>' + esc(saudiDisplay(report.issued_at)) + '</td><td><div class="row-actions"><button class="text-btn" data-report-print="' + report.test_id + '" type="button">طباعة</button><button class="text-btn" data-report-review="' + report.id + '" type="button">حالة</button></div></td></tr>';
  }).join('') || '<tr><td colspan="5" class="empty">لا توجد تقارير.</td></tr>');
}

function renderEquipment() {
  setHtml($('equipmentTable'), (dashboard ? dashboard.equipment : []).map(function(item) { return '<tr><td>' + esc(item.name) + '</td><td>' + esc(item.serial_no || '') + '</td><td>' + esc(item.last_calibration || '') + '</td><td>' + esc(item.next_calibration || '') + '</td><td>' + esc(item.certificate_no || '') + '</td><td>' + statusChip(item.status) + '</td></tr>'; }).join('') || '<tr><td colspan="6" class="empty">لا توجد أجهزة.</td></tr>');
}

function renderAudit() {
  setHtml($('auditTable'), (dashboard ? dashboard.audit : []).map(function(item) { return '<tr><td>' + esc(saudiDisplay(item.created_at)) + '</td><td>' + esc(item.full_name || '') + '</td><td>' + escUI(item.action) + '</td><td>' + esc(item.entity || '') + '</td><td>' + esc(item.details || '') + '</td></tr>'; }).join('') || '<tr><td colspan="5" class="empty">لا توجد عمليات.</td></tr>');
}

async function renderUsers() {
  try {
    const users = await api('/api/users');
    setHtml($('usersTable'), users.map(function(user) { return '<tr><td>' + esc(user.username) + '</td><td>' + esc(user.full_name) + '</td><td>' + escUI(ROLE_NAMES[user.role] || user.role) + '</td><td>' + (user.active ? 'نشط' : 'موقوف') + '</td><td>' + esc(saudiDisplay(user.created_at)) + '</td><td><button class="text-btn" data-user-edit="' + user.id + '" type="button">تعديل</button></td></tr>'; }).join(''));
    $('usersTable').dataset.users = JSON.stringify(users);
  } catch (error) {
    setHtml($('usersTable'), '<tr><td colspan="6" class="empty">ليس لديك صلاحية عرض المستخدمين.</td></tr>');
  }
}

function projectForm(project) {
  const value = project || {};
  const clients = dashboard ? dashboard.clients : [];
  const users = [];
  return '<h2>' + (project ? 'تعديل مشروع' : 'مشروع جديد') + '</h2><p>الحقول تربط تخطيط المشروع بالتنفيذ والعينات والتقارير دون تغيير البيانات القائمة.</p><form id="projectForm"><div class="modal-grid">' +
    '<label>اسم المشروع<input name="name" required value="' + esc(value.name || '') + '"></label>' +
    '<label>العميل<select name="client_id"><option value="">— اختر العميل —</option>' + optionList(clients,value.client_id,function(item){return item.name;},function(item){return item.id;}) + '</select></label>' +
    '<label>الموقع<input name="location" value="' + esc(value.location || '') + '"></label>' +
    '<label>الأولوية<select name="priority">' + optionList(PRIORITIES,value.priority || 'متوسطة',function(item){return item;},function(item){return item;}) + '</select></label>' +
    '<label>تاريخ البداية<input name="start_date" type="date" value="' + esc(value.start_date || '') + '"></label>' +
    '<label>تاريخ الاستحقاق<input name="due_date" type="date" value="' + esc(value.due_date || '') + '"></label>' +
    '<label>المقاول<input name="contractor_name" value="' + esc(value.contractor_name || '') + '"></label>' +
    '<label>الاستشاري<input name="consultant_name" value="' + esc(value.consultant_name || '') + '"></label>' +
    '<label>معرف مدير المشروع<input name="manager_id" type="number" min="1" value="' + esc(value.manager_id || '') + '"></label>' +
    '<label>نسبة التقدم<input name="progress" type="number" min="0" max="100" value="' + esc(value.progress || 0) + '"></label>' +
    '<label style="grid-column:1/-1">الوصف<textarea name="description" rows="3">' + esc(value.description || '') + '</textarea></label>' +
    '</div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary" type="submit">حفظ المشروع</button></div></form>';
}

function openProjectForm(id) {
  const project = id ? dashboard.projects.find(function(item) { return item.id === Number(id); }) : null;
  modal(projectForm(project));
}

async function submitProjectForm(form) {
  const payload = {};
  ['name','client_id','location','priority','start_date','due_date','contractor_name','consultant_name','manager_id','progress','description'].forEach(function(key) { payload[key] = fieldValue(form,key); });
  const editingId = form.dataset.projectId;
  await api(editingId ? '/api/projects/update' : '/api/projects', {method:'POST',body:JSON.stringify(editingId ? Object.assign(payload,{id:Number(editingId)}) : payload)});
  closeModal(); await refresh(); showToast(editingId ? 'تم تعديل المشروع' : 'تم إنشاء المشروع وربطه بطابور المزامنة');
}

async function openProjectWorkspace(id) {
  const space = await api('/api/projects/' + id + '/workspace');
  const p = space.project;
  const tabs = [
    ['work_orders','أوامر العمل',space.work_orders],
    ['samples','العينات',space.samples],
    ['tests','الاختبارات',space.tests],
    ['results','النتائج',space.results],
    ['reports','التقارير',space.reports],
    ['field_visits','الزيارات',space.field_visits]
  ];
  function rows(name, items) {
    if (!items.length) return '<div class="empty">لا توجد بيانات مرتبطة بعد.</div>';
    if (name === 'work_orders') return '<table><thead><tr><th>الرقم</th><th>العنوان</th><th>الحالة</th><th>الاستحقاق</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.order_no) + '</td><td>' + esc(item.title) + '</td><td>' + statusChip(item.status) + '</td><td>' + esc(item.due_date || '—') + '</td></tr>'; }).join('') + '</tbody></table>';
    if (name === 'samples') return '<table><thead><tr><th>العينة</th><th>المادة</th><th>الحالة</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.sample_no) + '</td><td>' + escUI(item.material) + '</td><td>' + statusChip(item.status) + '</td></tr>'; }).join('') + '</tbody></table>';
    if (name === 'tests') return '<table><thead><tr><th>الاختبار</th><th>العينة</th><th>الاسم</th><th>الحالة</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.test_no) + '</td><td>' + esc(item.sample_no) + '</td><td>' + escUI(item.name_ar) + '</td><td>' + statusChip(item.status) + '</td></tr>'; }).join('') + '</tbody></table>';
    if (name === 'results') return '<table><thead><tr><th>الاختبار</th><th>البند</th><th>القيمة</th><th>الوحدة</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.test_no) + '</td><td>' + esc(item.field_name) + '</td><td>' + esc(item.value) + '</td><td>' + esc(item.unit || '') + '</td></tr>'; }).join('') + '</tbody></table>';
    if (name === 'reports') return '<table><thead><tr><th>التقرير</th><th>الاختبار</th><th>الحالة</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.report_no) + '</td><td>' + escUI(item.name_ar || item.test_no) + '</td><td>' + statusChip(item.status) + '</td></tr>'; }).join('') + '</tbody></table>';
    return '<table><thead><tr><th>الرخصة</th><th>الموقع</th><th>الحالة</th><th>التاريخ</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.license_no) + '</td><td>' + esc(item.location || '') + '</td><td>' + statusChip(item.status) + '</td><td>' + esc(saudiDisplay(item.created_at)) + '</td></tr>'; }).join('') + '</tbody></table>';
  }
  const summary = '<div class="workspace-summary"><div><strong>' + space.work_orders.length + '</strong>أوامر العمل</div><div><strong>' + space.samples.length + '</strong>العينات</div><div><strong>' + space.tests.length + '</strong>الاختبارات</div><div><strong>' + space.results.length + '</strong>النتائج</div><div><strong>' + space.reports.length + '</strong>التقارير</div></div>';
  const tabButtons = tabs.map(function(tab,index) { return '<button type="button" class="' + (index === 0 ? 'active' : '') + '" data-workspace-tab="' + tab[0] + '">' + tab[1] + ' (' + tab[2].length + ')</button>'; }).join('');
  modal('<h2>' + esc(p.code) + ' — ' + esc(p.name) + '</h2><p>' + (p.client_name ? esc(p.client_name) : escUI('بدون عميل')) + ' · ' + (p.location ? esc(p.location) : escUI('بدون موقع')) + ' · ' + statusChip(p.status) + '</p>' + summary + '<div class="workspace-tabs">' + tabButtons + '<button type="button" data-work-order-for="' + p.id + '">+ أمر عمل</button></div><div id="workspaceContent" class="workspace-content">' + rows(tabs[0][0],tabs[0][2]) + '</div>');
  $('modalBody').dataset.workspace = JSON.stringify({tabs:tabs});
}

function openWorkOrderForm(projectId) {
  const projects = dashboard ? dashboard.projects : [];
  const technicians = dashboard ? (dashboard.technicians || []) : [];
  modal('<h2>أمر عمل جديد</h2><p>ينشئ أمراً مرتبطاً بمشروع، مع مسودة واتساب للمكلّف عند اختياره.</p><form id="workOrderForm"><div class="modal-grid"><label>المشروع<select name="project_id" required><option value="">— اختر المشروع —</option>' + optionList(projects,projectId,function(item){return item.code + ' — ' + item.name;},function(item){return item.id;}) + '</select></label><label>عنوان أمر العمل<input name="title" required></label><label>الأولوية<select name="priority">' + optionList(PRIORITIES,'متوسطة',function(item){return item;},function(item){return item;}) + '</select></label><label>الحالة<select name="status">' + optionList(WORK_ORDER_STATUSES,'مفتوح',function(item){return item;},function(item){return item;}) + '</select></label><label>تاريخ التنفيذ<input name="scheduled_date" type="date"></label><label>تاريخ الاستحقاق<input name="due_date" type="date"></label><label>الفني المكلّف<select name="assigned_to"><option value="">— غير محدد —</option>' + optionList(technicians,'',function(item){return item.full_name + ' — ' + item.username;},function(item){return item.id;}) + '</select></label><label style="grid-column:1/-1">الوصف<textarea name="description"></textarea></label></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary" type="submit">حفظ أمر العمل</button></div></form>');
}

async function renderQuality() {
  try {
    qualityData = await api('/api/quality');
    const categoryNames = {procedure:'إجراء',worksheet:'ورقة عمل',admin_form:'نموذج إداري'};
    setHtml($('qualityDocumentsTable'), qualityData.documents.map(function(item) { const ref = item.document_ref ? (item.document_ref.indexOf('/api/') === 0 ? '<a class="text-btn" href="' + esc(API_BASE_URL + item.document_ref) + '" target="_blank" rel="noopener">فتح الملف</a>' : esc(item.document_ref)) : '—'; return '<tr><td>' + escUI(categoryNames[item.category] || item.category) + '</td><td>' + esc(item.code) + '</td><td>' + esc(item.title) + '</td><td>' + esc(item.revision || '—') + '</td><td>' + statusChip(item.status) + '</td><td>' + ref + '</td></tr>'; }).join('') || '<tr><td colspan="6" class="empty">لا توجد وثائق جودة بعد.</td></tr>');
    setHtml($('proficiencyTable'), qualityData.proficiency.map(function(item) { return '<tr><td>' + esc(item.test_name) + '</td><td>' + esc(item.material || '—') + '</td><td>' + esc(item.provider || '—') + '</td><td>' + esc(item.participation_date || '—') + '</td><td>' + esc(item.result || '—') + '</td><td>' + esc(item.z_score || '—') + '</td></tr>'; }).join('') || '<tr><td colspan="6" class="empty">لا توجد مشاركات كفاءة بعد.</td></tr>');
    setHtml($('qualityStaffTable'), qualityData.staff.map(function(item) { return '<tr><td>' + esc(item.full_name) + '</td><td>' + esc(item.job_title || '—') + '</td><td>' + esc(item.specialty || '—') + '</td><td>' + esc(item.experience_years || '—') + '</td><td>' + esc(item.qualification_ref || '—') + '</td><td>' + (item.active ? 'نشط' : 'موقوف') + '</td></tr>'; }).join('') || '<tr><td colspan="6" class="empty">لا توجد سجلات موظفين للجودة بعد.</td></tr>');
  } catch (error) { ['qualityDocumentsTable','proficiencyTable','qualityStaffTable'].forEach(function(id) { if ($(id)) setHtml($(id), '<tr><td colspan="6" class="empty">تعذر تحميل بيانات الجودة.</td></tr>'); }); }
}

function openQualityForm(kind) {
  const names = {procedure:'إجراء جودة',worksheet:'ورقة عمل',admin_form:'نموذج إداري'};
  if (names[kind]) return modal('<h2>إضافة ' + names[kind] + '</h2><form id="qualityDocumentForm"><input type="hidden" name="category" value="' + kind + '"><input type="hidden" name="owner" value="شركة مختبر أساس"><div class="modal-grid"><label>الكود<input name="code" required placeholder="QMS-P-001"></label><label>العنوان<input name="title" required></label><label>الإصدار<input name="revision" placeholder="Rev. 01"></label><label>الحالة<select name="status"><option>ساري</option><option>قيد المراجعة</option><option>ملغى</option></select></label><label>رفع ملف Word أو PDF<input name="quality_file" type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"></label><label>رابط بديل (اختياري)<input name="document_ref" type="url"></label><label style="grid-column:1/-1">ملاحظات<textarea name="notes"></textarea></label></div><p class="form-note">PDF أو Word حتى 25MB.</p><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ الوثيقة</button></div></form>');
  if (kind === 'proficiency') return modal('<h2>إضافة مشاركة اختبار كفاءة</h2><form id="proficiencyForm"><div class="modal-grid"><label>اسم الاختبار<input name="test_name" required></label><label>المادة<input name="material"></label><label>المعيار<input name="standard"></label><label>مقدم الخدمة<input name="provider"></label><label>تاريخ المشاركة<input name="participation_date" type="date"></label><label>النتيجة<input name="result"></label><label>Z-score<input name="z_score"></label><label>رفع تقرير Word أو PDF<input name="quality_file" type="file" accept=".pdf,.doc,.docx"></label><label style="grid-column:1/-1">ملاحظات<textarea name="notes"></textarea></label></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ المشاركة</button></div></form>');
  if (kind === 'staff') return modal('<h2>إضافة سجل موظف للجودة</h2><form id="qualityStaffForm"><div class="modal-grid"><label>الاسم الكامل<input name="full_name" required></label><label>المسمى الوظيفي<input name="job_title"></label><label>التخصص<input name="specialty"></label><label>سنوات الخبرة<input name="experience_years" type="number" min="0"></label><label>رفع المؤهل Word أو PDF<input name="qualification_file" type="file" accept=".pdf,.doc,.docx"></label><label>رفع السيرة الذاتية Word أو PDF<input name="cv_file" type="file" accept=".pdf,.doc,.docx"></label><label style="grid-column:1/-1">ملاحظات<textarea name="notes"></textarea></label></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ السجل</button></div></form>');
}

const QUALITY_TEMPLATES = {
  equipment:['اسم الجهاز,الرقم التسلسلي,الشركة المصنعة,الموديل,آخر معايرة,المعايرة القادمة,رقم الشهادة,ملاحظات','جهاز ضغط,ABC-001,Manufacturer,Model X,2026-01-01,2027-01-01,CAL-001,'],
  proficiency:['اسم الاختبار,المادة,المعيار,مقدم الخدمة,تاريخ المشاركة,النتيجة,Z-score,مرجع التقرير,ملاحظات','مقاومة الضغط,خرسانة,ASTM C39,اسم الجهة,2026-01-01,مقبول,0.20,PT-001,'],
  staff:['الاسم الكامل,المسمى الوظيفي,التخصص,سنوات الخبرة,مرجع المؤهل,مرجع السيرة الذاتية,ملاحظات','اسم الموظف,فني مختبر,خرسانة,5,QUAL-001,CV-001,']
};
function downloadQualityTemplate(kind) { const blob = new Blob(['\ufeff' + (uiLanguage === 'en' ? QUALITY_TEMPLATES_EN[kind] : QUALITY_TEMPLATES[kind]).join('\n')],{type:'text/csv;charset=utf-8'}); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'ASAS_' + kind + '_template.csv'; link.click(); URL.revokeObjectURL(link.href); }
function parseCsv(text) { const lines = text.replace(/^\ufeff/,'').split(/\r?\n/).filter(Boolean); const cells = function(line) { return line.match(/(?:^|,)("(?:[^"]|"")*"|[^,]*)/g).map(function(cell) { return cell.replace(/^,/, '').replace(/^"|"$/g,'').replace(/""/g,'"').trim(); }); }; const headers = cells(lines.shift() || ''); return lines.map(function(line) { const values = cells(line); return headers.reduce(function(row,header,index) { row[header] = values[index] || ''; return row; },{}); }); }
async function importQualityRows(kind) { const file = $(kind + 'Import').files[0]; if (!file) throw new Error('اختر ملف CSV الذي تم تنزيله من النظام أولاً'); const rows = parseCsv(await file.text()); if (!rows.length) throw new Error('الملف لا يحتوي على صفوف بيانات'); const mappings = {equipment:{'اسم الجهاز':'name','الرقم التسلسلي':'serial_no','الشركة المصنعة':'manufacturer','الموديل':'model','آخر معايرة':'last_calibration','المعايرة القادمة':'next_calibration','رقم الشهادة':'certificate_no','ملاحظات':'notes'},proficiency:{'اسم الاختبار':'test_name','المادة':'material','المعيار':'standard','مقدم الخدمة':'provider','تاريخ المشاركة':'participation_date','النتيجة':'result','Z-score':'z_score','مرجع التقرير':'report_ref','ملاحظات':'notes'},staff:{'الاسم الكامل':'full_name','المسمى الوظيفي':'job_title','التخصص':'specialty','سنوات الخبرة':'experience_years','مرجع المؤهل':'qualification_ref','مرجع السيرة الذاتية':'cv_ref','ملاحظات':'notes'}}; const endpoint = {equipment:'/api/equipment',proficiency:'/api/quality/proficiency',staff:'/api/quality/staff'}[kind]; let completed = 0; for (const row of rows) { const payload = {}; Object.keys(mappings[kind]).forEach(function(header) { payload[mappings[kind][header]] = row[header] || row[translateUI(header)] || row[mappings[kind][header]] || ''; }); await api(endpoint,{method:'POST',body:JSON.stringify(payload)}); completed += 1; } await refresh(); showToast('تم استيراد ' + completed + ' سجل بنجاح'); }

function openTestAssignment(testId) {
  const test = (dashboard ? dashboard.tests : []).find(function(item) { return item.id === Number(testId); });
  const technicians = dashboard ? (dashboard.technicians || []) : [];
  if (!test || !technicians.length) return showToast('أضف فنيًا فعالًا أولًا ثم أعد المحاولة',true);
  modal('<h2>إسناد اختبار لفني</h2><p>سينشئ النظام مهمة للفني ومسودة واتساب قابلة للمراجعة.</p><form id="testAssignmentForm"><input name="test_id" type="hidden" value="' + esc(test.id) + '"><label>الاختبار<strong>' + esc(test.test_no) + ' — ' + escUI(test.name_ar) + '</strong></label><label>الفني<select name="technician_id" required><option value="">— اختر الفني —</option>' + optionList(technicians,test.technician_id || '',function(item){return item.full_name + ' — ' + item.username;},function(item){return item.id;}) + '</select></label><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary" type="submit">إسناد وإنشاء المسودة</button></div></form>');
}

async function submitTestAssignment(form) {
  await api('/api/tests/assign',{method:'POST',body:JSON.stringify({test_id:Number(fieldValue(form,'test_id')),technician_id:Number(fieldValue(form,'technician_id'))})});
  closeModal(); await refresh(); showToast('تم إسناد الاختبار وإنشاء مسودة واتساب للفني');
}

async function submitWorkOrder(form) {
  const payload = {};
  ['project_id','title','priority','status','scheduled_date','due_date','assigned_to','description'].forEach(function(key) { payload[key] = fieldValue(form,key); });
  await api('/api/work-orders',{method:'POST',body:JSON.stringify(payload)});
  closeModal(); await refresh(); showToast('تم إنشاء أمر العمل');
}

function openClientForm() {
  modal('<h2>عميل جديد</h2><form id="clientForm"><div class="modal-grid"><label>اسم العميل<input name="name" required></label><label>الهاتف<input name="phone"></label><label style="grid-column:1/-1">البريد الإلكتروني<input name="email" type="email"></label></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ العميل</button></div></form>');
}

function openSampleForm() {
  const projects = dashboard ? dashboard.projects : [];
  modal('<h2>تسجيل عينة</h2><form id="sampleForm"><div class="modal-grid"><label>رقم العينة<input name="sample_no" required></label><label>المشروع<select name="project_id"><option value="">— غير مرتبط —</option>' + optionList(projects,'',function(item){return item.code + ' — ' + item.name;},function(item){return item.id;}) + '</select></label><label>المادة<select name="material"><option>تربة</option><option>خرسانة</option><option>أسفلت</option></select></label><label>تاريخ الاستلام<input name="received_date" type="date" value="' + today() + '" required></label><label>المصدر<input name="source"></label><label>ملاحظات<textarea name="notes"></textarea></label></div><p class="form-message">سيُنشئ النظام تلقائياً خطة الاختبارات الرسمية الكاملة للمادة المختارة؛ لا تحتاج إلى إضافتها يدوياً.</p><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ العينة والخطة</button></div></form>');
}

function openEquipmentForm() {
  modal('<h2>إضافة جهاز</h2><form id="equipmentForm"><div class="modal-grid"><label>اسم الجهاز<input name="name" required></label><label>الرقم التسلسلي<input name="serial_no"></label><label>الشركة المصنعة<input name="manufacturer"></label><label>الموديل<input name="model"></label><label>آخر معايرة<input name="last_calibration" type="date"></label><label>المعايرة القادمة<input name="next_calibration" type="date"></label><label>رقم الشهادة<input name="certificate_no"></label><label>ملاحظات<textarea name="notes"></textarea></label></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ الجهاز</button></div></form>');
}

function genericFields(testCatalog) {
  const fields = TEST_FIELDS[testCatalog.code] || [['result','النتيجة','']];
  return fields.map(function(item) { return '<label>' + escUI(item[1]) + (item[2] ? ' (' + esc(item[2]) + ')' : '') + '<input name="result_' + esc(item[0]) + '" type="number" step="any"></label>'; }).join('');
}

function testFormContent() {
  return '<h2>إضافة اختبار</h2><form id="testForm"><div class="modal-grid"><label>نوع الاختبار<select id="testCatalogSelect" name="catalog_id" required><option value="">— اختر الاختبار —</option>' + optionList(catalog,'',function(item){return item.code + ' — ' + item.name_ar;},function(item){return item.id;}) + '</select></label><label>معرف العينة<input name="sample_id" type="number" min="1" required></label><label>رقم الاختبار (اختياري)<input name="test_no"></label><label>تاريخ البدء<input name="started_at" type="datetime-local"></label></div><div id="testDynamic" class="modal-grid"></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary" type="submit">حفظ الاختبار</button></div></form>';
}

function openTestForm() {
  modal(testFormContent());
}

function updateTestDynamic() {
  const selected = catalog.find(function(item) { return item.id === Number($('testCatalogSelect').value); });
  if (!selected) return setHtml($('testDynamic'), '');
  if (selected.code === 'D1557' || selected.code === 'D698') {
    let points = '';
    for (let i=1;i<=5;i++) points += '<label>رطوبة النقطة ' + i + ' %<input name="w' + i + '" type="number" step="any"></label><label>القالب + التربة الرطبة ' + i + ' g<input name="wet' + i + '" type="number" step="any"></label>';
    setHtml($('testDynamic'), '<label>وزن القالب g<input name="mold_weight" type="number" step="any"></label><label>حجم القالب cm³<input name="mold_volume" type="number" value="944" step="any"></label>' + points);
  } else {
    setHtml($('testDynamic'), genericFields(selected));
  }
}

async function submitTest(form) {
  const formData = new FormData(form);
  const testCatalog = catalog.find(function(item) { return item.id === Number(formData.get('catalog_id')); });
  if (!testCatalog) throw new Error('اختر نوع الاختبار');
  if (testCatalog.code === 'D1557' || testCatalog.code === 'D698') {
    const points = [];
    const moldWeight = Number(formData.get('mold_weight')); const volume = Number(formData.get('mold_volume'));
    for (let i=1;i<=5;i++) {
      const moisture = Number(formData.get('w' + i)); const wetTotal = Number(formData.get('wet' + i));
      if (!Number.isNaN(moisture) && wetTotal > moldWeight && volume > 0) {
        const wetDensity = (wetTotal - moldWeight) / volume;
        points.push({moisture:moisture,mold_soil_wet:wetTotal,wet_density:wetDensity,dry_density:wetDensity/(1+moisture/100)});
      }
    }
    if (points.length < 2) throw new Error('أدخل نقطتين صحيحتين على الأقل للبروكتور');
    const best = points.reduce(function(a,b) { return b.dry_density > a.dry_density ? b : a; });
    await api('/api/tests/proctor',{method:'POST',body:JSON.stringify({test_no:formData.get('test_no'),sample_id:formData.get('sample_id'),started_at:formData.get('started_at'),mdd:best.dry_density,omc:best.moisture,points:points,standard_code:testCatalog.code})});
  } else {
    const results = {};
    (TEST_FIELDS[testCatalog.code] || [['result','النتيجة','']]).forEach(function(item) { const value = formData.get('result_' + item[0]); if (value !== '') results[item[0]] = value; });
    await api('/api/tests/generic',{method:'POST',body:JSON.stringify({catalog_id:testCatalog.id,test_no:formData.get('test_no'),sample_id:formData.get('sample_id'),started_at:formData.get('started_at'),inputs:{},results:results})});
  }
  closeModal(); await refresh(); showToast('تم حفظ الاختبار وإنشاء مسودة التقرير');
}

function openUserForm(user) {
  const value = user || {};
  modal('<h2>' + (user ? 'تعديل مستخدم' : 'مستخدم جديد') + '</h2><p>يُحفظ التغيير في الخادم المركزي فورًا ويظهر للمستخدمين المتصلين.</p><form id="userForm" novalidate><input type="hidden" name="id" value="' + esc(value.id || '') + '"><div class="modal-grid"><label>اسم المستخدم<input name="username" required autocomplete="username" ' + (user ? 'readonly' : '') + ' value="' + esc(value.username || '') + '"></label><label>الاسم الكامل<input name="full_name" required value="' + esc(value.full_name || '') + '"></label><label>رقم الجوال الدولي<input class="phone-input" name="phone" dir="ltr" inputmode="tel" autocomplete="tel" placeholder="+9665XXXXXXXX" value="' + esc(value.phone || '') + '"></label><label>الدور<select name="role">' + optionList(Object.keys(ROLE_NAMES),value.role || 'technician',function(item){return ROLE_NAMES[item];},function(item){return item;}) + '</select></label><label>كلمة المرور ' + (user ? '(اتركها فارغة للإبقاء)' : '') + '<input name="password" type="password" autocomplete="new-password" ' + (user ? '' : 'required') + ' minlength="12"></label>' + (user ? '<label><input name="active" type="checkbox" ' + (value.active ? 'checked' : '') + '> الحساب نشط</label>' : '') + '</div><p id="userFormMessage" class="form-message" aria-live="polite">جاهز للحفظ والمزامنة الفورية. رقم الجوال اختياري، وإذا أُدخل يجب أن يكون دوليًا.</p><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button id="saveUserButton" class="btn primary" type="button">حفظ ومزامنة المستخدم</button></div></form>');
  const form = $('userForm');
  $('saveUserButton').addEventListener('click', function() { saveUserForm(form); });
}

async function saveUserForm(form) {
  try {
    await submitSimple(form, form.elements.id.value ? '/api/users/update' : '/api/users/create');
  } catch (error) {
    const message = error && error.message ? error.message : 'تعذر حفظ المستخدم';
    const formMessage = form.querySelector('#userFormMessage');
    if (formMessage) setText(formMessage, message);
    showToast(message, true);
  }
}

async function submitSimple(form, path) {
  const data = {};
  new FormData(form).forEach(function(value,key) { data[key] = value; });
  if (path === '/api/users/update') { const active = form.querySelector('[name="active"]'); data.active = active ? active.checked : true; }
  if (path.indexOf('/api/users/') === 0) {
    if (!String(data.full_name || '').trim()) throw new Error('الاسم الكامل مطلوب');
    if (!data.id && String(data.password || '').length < 12) throw new Error('كلمة المرور يجب ألا تقل عن 12 حرفاً');
    if (data.id && data.password && String(data.password).length < 12) throw new Error('كلمة المرور يجب ألا تقل عن 12 حرفاً');
  }
  const isUserSave = path.indexOf('/api/users/') === 0;
  const saveButton = isUserSave ? form.querySelector('#saveUserButton') : null;
  const formMessage = isUserSave ? form.querySelector('#userFormMessage') : null;
  if (saveButton) { saveButton.disabled = true; setText(saveButton, 'جارٍ الحفظ والمزامنة…'); }
  if (formMessage) setText(formMessage, 'جارٍ حفظ التغيير في الخادم المركزي…');
  let result;
  try {
    result = await api(path,{method:'POST',body:JSON.stringify(data)});
  } finally {
    if (saveButton) { saveButton.disabled = false; setText(saveButton, 'حفظ ومزامنة المستخدم'); }
  }
  closeModal(); await refresh();
  if (isUserSave) {
    publishLiveUpdate('users');
    showToast(data.id ? 'تم تعديل المستخدم ومزامنته فورًا' : 'تمت إضافة المستخدم وتفعيله ومزامنته فورًا');
    return;
  }
  publishLiveUpdate('operations');
  showToast(path === '/api/samples' ? 'تم حفظ العينة وإنشاء ' + (result.planned_count || 0) + ' اختباراً رسمياً تلقائياً' : 'تم الحفظ والمزامنة');
}
function openChangePassword() { modal('<h2>تغيير كلمة المرور</h2><p>هذا التغيير يخص حسابك المسجّل فقط.</p><form id="changePasswordForm"><div class="modal-grid"><label>كلمة المرور الحالية<input name="current_password" type="password" autocomplete="current-password" required></label><label>كلمة المرور الجديدة<input name="new_password" type="password" autocomplete="new-password" minlength="12" required></label><label>تأكيد كلمة المرور الجديدة<input name="confirm_password" type="password" autocomplete="new-password" minlength="12" required></label></div><p class="form-note">الحد الأدنى 12 حرفًا.</p><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">تغيير كلمة المرور</button></div></form>'); }
async function submitChangePassword(form) { const data={};new FormData(form).forEach(function(value,key){data[key]=value;});await api('/api/auth/change-password',{method:'POST',body:JSON.stringify(data)});closeModal();showToast('تم تغيير كلمة المرور لحسابك'); }
async function submitQualityDocument(form) { const data = {}; new FormData(form).forEach(function(value,key) { if (key !== 'quality_file') data[key] = value; }); const file = form.elements.quality_file.files[0]; if (file) { if (file.size > 25 * 1024 * 1024) throw new Error('حجم الملف يتجاوز 25MB'); const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ''; for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode.apply(null, bytes.subarray(offset, offset + 8192)); data.file_name = file.name; data.file_base64 = btoa(binary); } await api('/api/quality/documents',{method:'POST',body:JSON.stringify(data)}); closeModal(); await refresh(); showToast('تم حفظ وثيقة الجودة'); }
async function uploadQualityFile(file) { if (!file) return ''; if (file.size > 25 * 1024 * 1024) throw new Error('حجم الملف يتجاوز 25MB'); const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ''; for (let offset=0; offset<bytes.length; offset+=8192) binary += String.fromCharCode.apply(null,bytes.subarray(offset,offset+8192)); const result = await api('/api/quality/files',{method:'POST',body:JSON.stringify({file_name:file.name,file_base64:btoa(binary)})}); return result.ref; }
async function submitQualityRecord(form,path,files) { const data={}; new FormData(form).forEach(function(value,key){if(files.indexOf(key)<0)data[key]=value;}); for(const item of files){const ref=await uploadQualityFile(form.elements[item].files[0]); if(ref)data[item === 'quality_file' ? 'report_ref' : item === 'qualification_file' ? 'qualification_ref' : 'cv_ref']=ref;} await api(path,{method:'POST',body:JSON.stringify(data)}); closeModal(); await refresh(); showToast('تم الحفظ'); }

const BULK_FIELDS = {clients:['الاسم','الهاتف','البريد'],projects:['اسم المشروع','العميل','الموقع','الأولوية','البداية','الاستحقاق','التقدم','الوصف'],work_orders:['أمر العمل','معرف المشروع','الأولوية','الموعد','الاستحقاق','الوصف'],samples:['المادة','معرف المشروع','المصدر','تاريخ الاستلام','ملاحظات']};
const ENTITY_LABELS = {client:'عميل',project:'مشروع',work_order:'أمر عمل',sample:'عينة',test:'اختبار',report:'تقرير',equipment:'جهاز',user:'مستخدم'};
function csvRows(text) { const rows=[], row=[]; let cell='', quoted=false; for(let i=0;i<text.length;i++){const c=text[i]; if(c==='"'){if(quoted && text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;} else if(c===','&&!quoted){row.push(cell.trim());cell='';} else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell.trim());if(row.some(Boolean))rows.push(row.splice(0));cell='';} else cell+=c;} row.push(cell.trim());if(row.some(Boolean))rows.push(row); return rows; }
function downloadBulkTemplate(type) { const line=BULK_FIELDS[type].map(x=>uiLanguage==='en'?translateUI(x):x).join(',')+'\n'; const blob=new Blob(['\ufeff'+line],{type:'text/csv;charset=utf-8'}); const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='asas-'+type+'-template.csv';a.click();URL.revokeObjectURL(a.href); }
function entityRows(entity) { const mapping={client:'clients',project:'projects',work_order:'work_orders',sample:'samples',test:'tests',report:'reports',equipment:'equipment',user:'users'}; return (dashboard[mapping[entity]]||[]).map(function(item){ return {id:item.id,label:item.name||item.code||item.order_no||item.sample_no||item.test_no||item.report_no||item.full_name||item.username||('سجل '+item.id)}; }); }
function openAttachmentPanel(entity) { const rows=entityRows(entity); modal('<h2>مرفقات '+escUI(ENTITY_LABELS[entity])+'</h2><p>ارفع Word أو Excel أو PDF حتى 25MB، واربطه بالسجل المطلوب.</p><form id="recordAttachmentForm"><div class="modal-grid"><label>السجل<select name="entity_id" required>'+optionList(rows,'',function(x){return x.label;},function(x){return x.id;})+'</select></label><label>الملف<input name="file" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx" required></label></div><div id="recordAttachmentList" class="form-note"></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">رفع وحفظ</button></div></form>'); const form=$('recordAttachmentForm'); form.dataset.entityType=entity; const load=async function(){const id=form.elements.entity_id.value;if(!id)return;setText($('recordAttachmentList'), 'جارٍ تحميل المرفقات…');try{const items=await api('/api/attachments?entity_type='+encodeURIComponent(entity)+'&entity_id='+encodeURIComponent(id));setHtml($('recordAttachmentList'), items.length?items.map(function(x){return '<a target="_blank" rel="noopener" href="'+esc(API_BASE_URL+'/api/attachments/files/'+x.id)+'">'+esc(x.original_name)+'</a>';}).join('<br>'):'لا توجد مرفقات لهذا السجل.');}catch(e){setText($('recordAttachmentList'), 'تعذر تحميل المرفقات');}}; form.elements.entity_id.addEventListener('change',load); load(); }
function openBulkPanel(type) { const entity={clients:'client',projects:'project',work_orders:'work_order',samples:'sample'}[type]; modal('<h2>استيراد '+escUI(ENTITY_LABELS[entity])+' من Excel</h2><p>نزّل القالب، افتحه في Excel، ثم احفظه بصيغة CSV UTF-8 وارفعه. بعد الاستيراد تستطيع رفع المرفقات من نفس القسم.</p><div class="modal-actions"><button class="btn secondary" type="button" data-download-bulk="'+esc(type)+'">تنزيل قالب Excel</button><button class="btn secondary" type="button" data-open-attachments="'+esc(entity)+'">رفع مرفق</button></div><form id="bulkImportForm"><label>ملف CSV من Excel<input name="file" type="file" accept=".csv,text/csv" required></label><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">استيراد الصفوف</button></div></form>'); $('bulkImportForm').dataset.entityType=type; }
async function submitBulkImport(form) { const file=form.elements.file.files[0]; if(!file)throw new Error('اختر ملف CSV صادر من Excel'); const rows=csvRows(await file.text()); if(rows.length<2)throw new Error('الملف لا يحتوي صفوفاً للاستيراد'); const heads=rows.shift(); const values=rows.map(function(row){const out={};heads.forEach(function(h,i){const canonical=(BULK_FIELDS[form.dataset.entityType]||[]).find(x=>x===h||translateUI(x)===h)||h; let value=row[i]||''; if(['الأولوية','المادة'].includes(canonical)){value=['منخفضة','متوسطة','عالية','حرجة','تربة','خرسانة','أسفلت'].find(x=>translateUI(x).toLowerCase()===value.toLowerCase())||value;} out[canonical]=value;});return out;}); const result=await api('/api/bulk/import',{method:'POST',body:JSON.stringify({entity_type:form.dataset.entityType,rows:values})}); closeModal();await refresh();showToast('تم استيراد '+result.imported+' صف'+(result.skipped.length?'، وتجاوز '+result.skipped.length+' صف غير صالح':'')); }
async function submitRecordAttachment(form) { const file=form.elements.file.files[0];if(!file)throw new Error('اختر ملفاً');if(file.size>25*1024*1024)throw new Error('حجم الملف يتجاوز 25MB');const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode.apply(null,bytes.subarray(i,i+8192));await api('/api/attachments',{method:'POST',body:JSON.stringify({entity_type:form.dataset.entityType,entity_id:form.elements.entity_id.value,file_name:file.name,file_base64:btoa(binary)})});closeModal();showToast('تم رفع المرفق وحفظه');}

async function changeProjectStatus(id, status) {
  try {
    await api('/api/projects/status',{method:'POST',body:JSON.stringify({id:Number(id),status:status})});
    await refresh(); showToast('تم تحديث حالة المشروع');
  } catch (error) {
    showToast(error.message,true); renderProjects();
  }
}

async function changeReportStatus(id) {
  let status = window.prompt(uiLanguage === 'en' ? 'Select status: Draft, Under review, Approved, Rejected' : 'اختر الحالة: مسودة، قيد المراجعة، معتمد، مرفوض');
  if (!status) return; status = ({'Draft':'مسودة','Under review':'قيد المراجعة','Approved':'معتمد','Rejected':'مرفوض'})[status.trim()] || status;
  try { await api('/api/reports/status',{method:'POST',body:JSON.stringify({id:Number(id),status:status.trim()})}); await refresh(); showToast('تم تحديث التقرير'); } catch (error) { showToast(error.message,true); }
}

async function printReport(testId) {
  const report = await api('/api/report/' + testId);
  const inputRows = Object.keys(report.data.inputs || {}).map(function(key) { return '<tr><th>' + esc(key) + '</th><td>' + esc(report.data.inputs[key]) + '</td></tr>'; }).join('');
  const resultRows = Object.keys(report.data.results || {}).map(function(key) { return '<tr><th>' + esc(key) + '</th><td>' + esc(report.data.results[key]) + '</td></tr>'; }).join('');
  modal('<section class="report-preview">' + '<h1>' + escUI(report.lab_name) + '</h1><h2>تقرير اختبار</h2><table><tr><th>رقم التقرير</th><td>' + esc(report.report_no) + '</td></tr><tr><th>رقم الاختبار</th><td>' + esc(report.test_no) + '</td></tr><tr><th>العينة</th><td>' + esc(report.sample_no) + '</td></tr><tr><th>الاختبار</th><td>' + escUI(report.name_ar) + '</td></tr><tr><th>المعيار</th><td>' + esc(report.standard) + '</td></tr><tr><th>الحالة</th><td>' + escUI(report.status) + '</td></tr></table><h3>المدخلات</h3><table>' + (inputRows || '<tr><td>—</td></tr>') + '</table><h3>النتائج</h3><table>' + (resultRows || '<tr><td>—</td></tr>') + '</table>' + '</section><button class="btn primary no-print" type="button" data-print-preview>طباعة</button>');
}

function renderFieldTests() {
  setHtml($('fieldTests'), fieldTests.map(function(test,index) {
    return '<div class="field-test-row"><select data-field-test="' + index + '" data-field-key="catalog_id" aria-label="الاختبار الرسمي"><option value="">— اختر اختباراً رسمياً —</option>' + optionList(catalog, test.catalog_id, function(item) { return item.category + ' — ' + item.code + ' — ' + item.name_ar; }, function(item) { return item.id; }) + '</select><input data-field-test="' + index + '" data-field-key="result" value="' + esc(test.result) + '" placeholder="النتيجة / القراءات الميدانية"><button class="btn danger" data-field-remove="' + index + '" type="button">حذف</button></div>';
  }).join('') || '<div class="empty">اختر الاختبارات الرسمية المنفذة في هذه الزيارة.</div>');
}

function syncFieldTestCatalog(test) {
  const item = catalog.find(function(row) { return row.id === Number(test.catalog_id); });
  if (item) { test.name = item.name_ar; test.standard = item.standard; }
  return test;
}

function openBaladyWindow() {
  modal('<h2>نظام بلدي — بيانات الزيارة</h2><p class="form-message">تُحفظ بيانات التصريح مع الزيارة. فتح البوابة لا يرسل بيانات تلقائياً ولا يتجاوز صلاحيات حساب بلدي.</p><form id="baladyForm"><div class="modal-grid"><label>رقم تصريح بلدي<input name="balady_permit_no" value="' + esc($('fieldLicense').value) + '"></label><label>الأمانة / البلدية<input name="balady_municipality"></label><label>نوع التصريح<input name="balady_permit_type" placeholder="مثال: حفرية أو إشغال"></label><label>حالة التصريح<select name="balady_permit_status"><option value="">— غير محددة —</option><option>ساري</option><option>قيد المراجعة</option><option>منتهي</option><option>موقوف</option></select></label><label style="grid-column:1/-1">رابط معاملة بلدي (اختياري)<input name="balady_reference_url" type="url" placeholder="https://..."></label></div><div class="modal-actions"><button class="btn secondary" type="button" data-open-balady-portal>فتح بوابة بلدي</button><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary" type="submit">حفظ في الزيارة</button></div></form>');
}

function saveBaladyData(form) {
  new FormData(form).forEach(function(value, key) { $('field').dataset[key] = String(value).trim(); });
  if ($('field').dataset.balady_permit_no) $('fieldLicense').value = $('field').dataset.balady_permit_no;
  closeModal(); showToast('تم حفظ بيانات بلدي مع الزيارة الميدانية');
}

function fillPermitFields(permit) {
  $('fieldContractor').value = permit.contractor_name || '';
  $('fieldProjectName').value = permit.project_name || '';
  $('fieldSector').value = permit.sector_name || '';
  $('fieldLocation').value = permit.location || '';
  const field=$('field');
  field.dataset.balady_permit_no=permit.license_no || $('fieldLicense').value;
  field.dataset.balady_municipality=permit.municipality || '';
  field.dataset.balady_permit_type=permit.permit_type || '';
  field.dataset.balady_permit_status=permit.status || '';
  field.dataset.balady_reference_url=permit.reference_url || '';
}
function showBaladyPermit(permit) {
  const details=permit.details || {};
  const rows=Object.keys(details).filter(function(key){return details[key] !== null && details[key] !== '' && typeof details[key] !== 'object';}).map(function(key){return '<div><strong>'+escUI(key)+'</strong><span>'+esc(details[key])+'</span></div>';}).join('');
  modal('<h2>تفاصيل رخصة بلدي</h2><div class="stack-list"><div><strong>رقم الرخصة</strong><span>'+esc(permit.license_no || '')+'</span></div><div><strong>الأمانة / البلدية</strong><span>'+esc(permit.municipality || '')+'</span></div><div><strong>المقاول</strong><span>'+esc(permit.contractor_name || '')+'</span></div><div><strong>المشروع</strong><span>'+esc(permit.project_name || '')+'</span></div><div><strong>نوع التصريح</strong><span>'+esc(permit.permit_type || '')+'</span></div><div><strong>الحالة</strong><span>'+escUI(permit.status || '')+'</span></div>'+rows+'</div><div class="modal-actions"><button class="btn primary" type="button" data-modal-close>إغلاق</button></div>');
}
async function searchLicense() {
  const license = $('fieldLicense').value.trim();
  if (!license) return showToast('أدخل رقم الرخصة أولاً',true);
  const button=$('searchLicenseBtn'); button.disabled=true; setText(button,'جارٍ البحث في بلدي…');
  try {
    if (!STATIC_MODE) {
      const permit=await api('/api/balady/permit?license='+encodeURIComponent(license));
      fillPermitFields(permit); showBaladyPermit(permit); showToast('تم جلب بيانات الرخصة من منصة بلدي'); return;
    }
    const rows = await api('/api/field/search?license=' + encodeURIComponent(license));
    if (!rows.length) return showToast('الربط المركزي مع بلدي غير متاح في وضع العرض الثابت',true);
    fillPermitFields(rows[0]); showToast('تمت تعبئة آخر بيانات محفوظة محليًا لهذه الرخصة');
  } catch (error) { showToast(error.message,true); }
  finally { button.disabled=false; setText(button,'بحث برقم الرخصة'); }
}

function getLocation() {
  if (!navigator.geolocation) return showToast('تحديد الموقع غير متاح في هذا المتصفح',true);
  navigator.geolocation.getCurrentPosition(function(position) {
    fieldLat = position.coords.latitude; fieldLng = position.coords.longitude;
    setText($('gpsStatus'), 'تم تحديد الموقع: ' + fieldLat.toFixed(6) + ', ' + fieldLng.toFixed(6));
  }, function(error) { showToast('تعذر تحديد الموقع: ' + error.message,true); }, {enableHighAccuracy:true,timeout:10000});
}

async function saveFieldVisit() {
  const license = $('fieldLicense').value.trim();
  if (!license) return showToast('رقم الرخصة مطلوب',true);
  try {
    const result = await api('/api/field/visits',{method:'POST',body:JSON.stringify({
      license_no:license,contractor_name:$('fieldContractor').value,project_name:$('fieldProjectName').value,sector_name:$('fieldSector').value,layer_no:$('fieldLayer').value,location:$('fieldLocation').value,latitude:fieldLat,longitude:fieldLng,project_id:$('fieldProjectId').value || null,sample_id:$('fieldSampleId').value || null,tests:fieldTests.map(syncFieldTestCatalog).filter(function(test) { return test.catalog_id; }),notes:$('fieldNotes').value,status:'مسودة',balady_permit_no:$('field').dataset.balady_permit_no || '',balady_municipality:$('field').dataset.balady_municipality || '',balady_permit_type:$('field').dataset.balady_permit_type || '',balady_permit_status:$('field').dataset.balady_permit_status || '',balady_reference_url:$('field').dataset.balady_reference_url || ''
    })});
    setText($('fieldMessage'), 'تم حفظ الزيارة رقم ' + result.id);
    fieldTests = []; renderFieldTests(); await loadFieldRecent(); await refresh();
  } catch (error) { setText($('fieldMessage'), error.message); }
}

async function loadFieldRecent() {
  try {
    const rows = await api('/api/field/recent');
    setHtml($('fieldRecent'), rows.map(function(item) {
      return '<article class="field-item"><strong>' + esc(item.license_no) + ' — ' + esc(item.project_name || '') + '</strong><small>' + esc(item.contractor_name || '') + ' · ' + esc(saudiDisplay(item.created_at)) + '</small><div>' + statusChip(item.status) + '</div><div class="field-item-actions"><button class="btn secondary" data-field-status="' + item.id + '|مرسلة" type="button">إرسال</button><button class="btn secondary" data-field-status="' + item.id + '|قيد المراجعة" type="button">مراجعة</button><button class="btn primary" data-field-status="' + item.id + '|معتمدة" type="button">اعتماد</button><button class="btn danger" data-field-status="' + item.id + '|مرفوضة" type="button">رفض</button></div></article>';
    }).join('') || '<div class="empty">لا توجد زيارات ميدانية بعد.</div>');
  } catch (error) { setHtml($('fieldRecent'), '<div class="empty">تعذر تحميل الزيارات.</div>'); }
}

async function setFieldStatus(token) {
  const parts = token.split('|');
  try { await api('/api/field/status',{method:'POST',body:JSON.stringify({id:Number(parts[0]),status:parts[1]})}); await loadFieldRecent(); await refresh(); showToast('تم تحديث حالة الزيارة'); } catch (error) { showToast(error.message,true); }
}

function bindEvents() {
  $('loginForm').addEventListener('submit',login);
  $('logoutBtn').addEventListener('click',logout);
  $('changePassword').addEventListener('click',openChangePassword);
  $('staticSetup').addEventListener('click',bootstrapStaticAdmin);
  $('staticSetupForm').addEventListener('submit',submitStaticAdmin);
  $('menuBtn').addEventListener('click',function() { $('sidebar').classList.toggle('open'); });
  $('closeModal').addEventListener('click',closeModal);
  $('modal').addEventListener('click',function(event) { if (event.target === $('modal')) closeModal(); });
  document.querySelectorAll('.nav-link[data-page]').forEach(function(button) { button.addEventListener('click',function() { navigate(button.dataset.page); }); });
  document.querySelectorAll('[data-open-project]').forEach(function(button) { button.addEventListener('click',function() { openProjectForm(); }); });
  document.querySelectorAll('[data-page-go]').forEach(function(button) { button.addEventListener('click',function() { navigate(button.dataset.pageGo); }); });
  document.querySelectorAll('.view-btn').forEach(function(button) { button.addEventListener('click',function() { setProjectView(button.dataset.projectView); }); });
  $('projectSearch').addEventListener('input',renderProjects);
  $('projectPriorityFilter').addEventListener('change',renderProjects);
  $('catalogSearch').addEventListener('input',renderCatalog);
  $('openWorkOrder').addEventListener('click',function() { openWorkOrderForm(); });
  $('openClient').addEventListener('click',openClientForm);
  $('openSample').addEventListener('click',openSampleForm);
  $('openEquipment').addEventListener('click',openEquipmentForm);
  $('openTest').addEventListener('click',openTestForm);
  $('openUser').addEventListener('click',function() { openUserForm(); });
  $('openBalady').addEventListener('click',openBaladyWindow);
  $('searchLicenseBtn').addEventListener('click',searchLicense);
  $('getLocationBtn').addEventListener('click',getLocation);
  $('addFieldTest').addEventListener('click',function() { if (!catalog.length) return showToast('يجري تحميل كتالوج الاختبارات، حاول بعد لحظة',true); if (fieldTests.length >= 20) return showToast('الحد الأقصى عشرون اختباراً للزيارة',true); fieldTests.push({catalog_id:'',name:'',standard:'',result:''}); renderFieldTests(); });
  $('saveFieldVisit').addEventListener('click',saveFieldVisit);
  document.addEventListener('change',function(event) {
    if (event.target.matches('.project-status')) changeProjectStatus(event.target.dataset.projectId,event.target.value);
    if (event.target.id === 'testCatalogSelect') updateTestDynamic();
    if (event.target.matches('[data-field-test]')) { const test = fieldTests[Number(event.target.dataset.fieldTest)]; test[event.target.dataset.fieldKey] = event.target.value; if (event.target.dataset.fieldKey === 'catalog_id') syncFieldTestCatalog(test); }
  });
  document.addEventListener('click',async function(event) {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.hasAttribute('data-modal-close')) return closeModal();
    if (button.hasAttribute('data-open-balady-portal')) return window.open('https://balady.gov.sa/', '_blank', 'noopener');
    if (button.dataset.projectOpen) return openProjectWorkspace(button.dataset.projectOpen);
    if (button.dataset.projectEdit) {
      openProjectForm(button.dataset.projectEdit);
      $('projectForm').dataset.projectId = button.dataset.projectEdit;
      return;
    }
    if (button.dataset.workOrderFor) return openWorkOrderForm(button.dataset.workOrderFor);
    if (button.dataset.workspaceTab) {
      const stored = JSON.parse($('modalBody').dataset.workspace || '{"tabs":[]}');
      const tab = stored.tabs.find(function(item) { return item[0] === button.dataset.workspaceTab; });
      if (!tab) return;
      document.querySelectorAll('[data-workspace-tab]').forEach(function(item) { item.classList.toggle('active', item === button); });
      const lines = tab[2].length ? '<pre style="margin:0;padding:14px;white-space:pre-wrap;font:inherit">' + esc(JSON.stringify(tab[2],null,2)) + '</pre>' : '<div class="empty">لا توجد بيانات مرتبطة بعد.</div>';
      setHtml($('workspaceContent'), lines);
      return;
    }
    if (button.dataset.fieldRemove !== undefined) { fieldTests.splice(Number(button.dataset.fieldRemove),1); renderFieldTests(); return; }
    if (button.dataset.fieldStatus) return setFieldStatus(button.dataset.fieldStatus);
    if (button.hasAttribute('data-print-preview')) return window.print();
    if (button.dataset.reportPrint) return printReport(button.dataset.reportPrint);
    if (button.dataset.reportReview) return changeReportStatus(button.dataset.reportReview);
    if (button.dataset.testAssign) return openTestAssignment(button.dataset.testAssign);
    if (button.dataset.whatsappCopy) {
      const draft = (dashboard.whatsapp_drafts || []).find(function(item) { return item.id === Number(button.dataset.whatsappCopy); });
      if (!draft) return;
      try { await navigator.clipboard.writeText(draft.message_text); showToast('تم نسخ المسودة؛ الصقها في مجتمع مختبر أساس بعد المراجعة'); }
      catch (error) { showToast('تعذر النسخ التلقائي؛ افتح المسودة وانسخ النص يدويًا',true); }
      return;
    }
    if (button.dataset.whatsappReady) {
      try { await api('/api/whatsapp/drafts/' + Number(button.dataset.whatsappReady) + '/ready',{method:'POST',body:'{}'}); await refresh(); showToast('المسودة جاهزة للمشاركة اليدوية في مجتمع واتساب'); }
      catch (error) { showToast(error.message,true); }
      return;
    }
    if (button.dataset.qualityAdd) return openQualityForm(button.dataset.qualityAdd);
    if (button.dataset.qualityTemplate) return downloadQualityTemplate(button.dataset.qualityTemplate);
    if (button.dataset.qualityImport) { try { await importQualityRows(button.dataset.qualityImport); } catch (error) { showToast(error.message,true); } return; }
    if (button.dataset.catalogResources) return openCatalogResources(button.dataset.catalogResources);
    if (button.dataset.bulkPanel) return openBulkPanel(button.dataset.bulkPanel);
    if (button.dataset.attachmentPanel) return openAttachmentPanel(button.dataset.attachmentPanel);
    if (button.dataset.downloadBulk) return downloadBulkTemplate(button.dataset.downloadBulk);
    if (button.dataset.openAttachments) return openAttachmentPanel(button.dataset.openAttachments);
    if (button.dataset.userEdit) {
      const users = JSON.parse($('usersTable').dataset.users || '[]'); const user = users.find(function(item) { return item.id === Number(button.dataset.userEdit); }); if (user) openUserForm(user);
    }
  });
  document.addEventListener('submit',async function(event) {
    const form = event.target;
    if (!form.id) return;
    event.preventDefault();
    try {
      if (form.id === 'projectForm') await submitProjectForm(form);
      if (form.id === 'workOrderForm') await submitWorkOrder(form);
      if (form.id === 'clientForm') await submitSimple(form,'/api/clients');
      if (form.id === 'sampleForm') await submitSimple(form,'/api/samples');
      if (form.id === 'equipmentForm') await submitSimple(form,'/api/equipment');
      if (form.id === 'testForm') await submitTest(form);
      if (form.id === 'testAssignmentForm') await submitTestAssignment(form);
      if (form.id === 'userForm') await saveUserForm(form);
      if (form.id === 'qualityDocumentForm') await submitQualityDocument(form);
      if (form.id === 'proficiencyForm') await submitQualityRecord(form,'/api/quality/proficiency',['quality_file']);
      if (form.id === 'qualityStaffForm') await submitQualityRecord(form,'/api/quality/staff',['qualification_file','cv_file']);
      if (form.id === 'bulkImportForm') await submitBulkImport(form);
      if (form.id === 'recordAttachmentForm') await submitRecordAttachment(form);
      if (form.id === 'catalogResourcesForm') await submitCatalogResources(form);
      if (form.id === 'changePasswordForm') await submitChangePassword(form);
      if (form.id === 'baladyForm') saveBaladyData(form);
    } catch (error) {
      const message = error && error.message ? error.message : 'تعذر حفظ البيانات';
      const formMessage = form.querySelector('#userFormMessage');
      if (formMessage) setText(formMessage, message);
      showToast(message,true);
    }
  });
}

function init() {
  bindEvents();
  const languageToggle = $('languageToggle');
  if (languageToggle) { languageToggle.value = localStorage.getItem('asas_lims_language') || 'ar'; languageToggle.addEventListener('change', function(){ setLanguage(languageToggle.value); }); setLanguage(languageToggle.value); }
  updateSaudiClock(); setInterval(updateSaudiClock,1000);
  const footerYear = $('footerYear');
  if (footerYear) setText(footerYear, String(new Date().getFullYear()));
  document.addEventListener('visibilitychange', function() {
    if (!document.hidden && currentUser) refresh().catch(function() {});
  });
  window.addEventListener('online', function() {
    if (currentUser) refresh().catch(function() {});
  });
  if (STATIC_MODE && !localDB().users.length) $('staticSetup').classList.remove('hidden');
}

document.addEventListener('DOMContentLoaded',init);

const QUALITY_TEMPLATES_EN = {
 equipment:['Equipment name,Serial number,Manufacturer,Model,Last calibration,Next calibration,Certificate number,Notes','Compression machine,ABC-001,Manufacturer,Model X,2026-01-01,2027-01-01,CAL-001,'],
 proficiency:['Test name,Material,Standard,Service provider,Participation date,Result,Z-score,Report reference,Notes','Compressive strength,Concrete,ASTM C39,Provider,2026-01-01,Accepted,0.20,PT-001,'],
 staff:['Full name,Job title,Specialty,Years of experience,Qualification reference,CV reference,Notes','Employee name,Laboratory technician,Concrete,5,QUAL-001,CV-001,']
};
