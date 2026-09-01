'use strict';

const $ = function(id) { return document.getElementById(id); };
const STATIC_MODE = location.hostname.endsWith('github.io');
const STORAGE_KEY = 'asas_lims_v720';
const PROJECT_STATUSES = ['مخطط', 'نشط', 'موقوف', 'قيد المراجعة', 'معتمد', 'مكتمل'];
const BOARD_STATUSES = ['مخطط', 'نشط', 'قيد المراجعة', 'موقوف', 'مكتمل'];
const PRIORITIES = ['منخفضة', 'متوسطة', 'عالية', 'حرجة'];
const WORK_ORDER_STATUSES = ['مفتوح', 'قيد التنفيذ', 'بانتظار المراجعة', 'موقوف', 'مكتمل'];
const ROLE_NAMES = {admin:'مدير نظام',manager:'مدير',technician:'فني مختبر',field:'مفتش ميداني'};
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
let currentUser = null;
let projectView = 'table';
let fieldTests = [];
let fieldLat = null;
let fieldLng = null;
let toastTimer = null;

function esc(value) {
  return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function(char) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char];
  });
}

function statusClass(value) {
  return String(value || '').replace(/\s+/g, '_');
}

function statusChip(value) {
  return '<span class="status ' + statusClass(value) + '">' + esc(value || '—') + '</span>';
}

function priorityChip(value) {
  return '<span class="priority ' + statusClass(value) + '">' + esc(value || 'متوسطة') + '</span>';
}

function today() {
  return new Date().toISOString().slice(0, 10);
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
  if (!data.catalog.length) data.catalog = defaultCatalog();
  return data;
}

function saveLocal(data) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  return data;
}

function defaultCatalog() {
  return [
    {id:1,code:'D1883',name_ar:'نسبة تحمل كاليفورنيا CBR',name_en:'California Bearing Ratio',category:'تربة',standard:'ASTM D1883',version:'2024'},
    {id:2,code:'D2216',name_ar:'محتوى الرطوبة',name_en:'Water Content',category:'تربة',standard:'ASTM D2216',version:'2019'},
    {id:3,code:'D4318',name_ar:'حدود أتربرج',name_en:'Atterberg Limits',category:'تربة',standard:'ASTM D4318',version:'2018'},
    {id:4,code:'C136',name_ar:'التحليل المنخلي',name_en:'Sieve Analysis',category:'ركام',standard:'ASTM C136',version:'2019'},
    {id:5,code:'D1557',name_ar:'بروكتور المعدل',name_en:'Modified Proctor',category:'تربة',standard:'ASTM D1557',version:'2021'},
    {id:6,code:'D698',name_ar:'بروكتور القياسي',name_en:'Standard Proctor',category:'تربة',standard:'ASTM D698',version:'2021'},
    {id:7,code:'C39',name_ar:'مقاومة الضغط للخرسانة',name_en:'Compressive Strength',category:'خرسانة',standard:'ASTM C39',version:'2024'},
    {id:8,code:'C143',name_ar:'اختبار الهطول',name_en:'Slump',category:'خرسانة',standard:'ASTM C143',version:'2020'},
    {id:9,code:'D2041',name_ar:'الوزن النوعي الأقصى للخلطة الإسفلتية Gmm',category:'أسفلت',standard:'ASTM D2041',version:'2022'}
  ];
}

function localId(items) {
  return items.length ? Math.max.apply(null, items.map(function(item) { return Number(item.id) || 0; })) + 1 : 1;
}

function localAudit(data, action, entity, details) {
  data.audit.unshift({id:localId(data.audit),created_at:new Date().toLocaleString('ar-SA'),full_name:currentUser ? currentUser.full_name : 'محلي',action:action,entity:entity,details:details});
}

function localQueue(data, entity, entityId, operation) {
  data.syncQueue.unshift({id:localId(data.syncQueue),entity:entity,entity_id:entityId,operation:operation,status:'queued',attempts:0,created_at:new Date().toLocaleString('ar-SA')});
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
    projects:projects,work_orders:orders,clients:data.clients.slice().reverse(),samples:samples.slice().reverse(),tests:tests.slice().reverse(),reports:reports.slice().reverse(),equipment:data.equipment.slice().reverse(),audit:data.audit,activity:data.audit.slice(0,15),sync:data.syncQueue,
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
    const user = data.users.find(function(item) { return item.username === String(body.username || '').trim() && item.password === String(body.password || '') && item.active; });
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
  if (!currentUser) throw new Error('غير مسجل الدخول');
  if (path === '/api/catalog') return data.catalog;
  if (path === '/api/dashboard') return localDashboard(data);
  if (path === '/api/projects') {
    if (!options || !options.method || options.method === 'GET') return localProjectRows(data);
    const id = localId(data.projects);
    const project = Object.assign({id:id,code:'PR-' + String(id).padStart(6,'0'),status:'مخطط',priority:'متوسطة',progress:0,created_at:new Date().toLocaleString('ar-SA')}, body);
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
    const order = Object.assign({id:id,order_no:'WO-' + String(id).padStart(6,'0'),status:'مفتوح',priority:'متوسطة',created_at:new Date().toLocaleString('ar-SA')}, body, {project_id:Number(body.project_id)});
    data.workOrders.push(order); localQueue(data,'work_order',id,'create'); localAudit(data,'إضافة أمر عمل','work_order',order.order_no + ' - ' + order.title); saveLocal(data); return {ok:true,id:id,order_no:order.order_no};
  }
  if (path === '/api/clients') {
    const id = localId(data.clients); data.clients.push(Object.assign({id:id},body)); localAudit(data,'إضافة عميل','client',body.name); saveLocal(data); return {ok:true,id:id};
  }
  if (path === '/api/samples') {
    const id = localId(data.samples); data.samples.push(Object.assign({id:id,status:'قيد الاختبار',project_id:body.project_id ? Number(body.project_id) : null},body)); localQueue(data,'sample',id,'create'); localAudit(data,'إضافة عينة','sample',body.sample_no); saveLocal(data); return {ok:true,id:id};
  }
  if (path === '/api/equipment') {
    const id = localId(data.equipment); data.equipment.push(Object.assign({id:id,status:'ساري'},body)); localAudit(data,'إضافة جهاز','equipment',body.name); saveLocal(data); return {ok:true,id:id};
  }
  if (path === '/api/tests/generic' || path === '/api/tests/proctor') {
    const id = localId(data.tests); const code = body.standard_code || (data.catalog.find(function(item) { return item.id === Number(body.catalog_id); }) || {}).code; const cat = data.catalog.find(function(item) { return item.code === code; }) || {};
    const test = {id:id,test_no:body.test_no || 'TST-' + String(id).padStart(6,'0'),sample_id:Number(body.sample_id),catalog_id:cat.id,status:'مكتمل',results:body.results || {mdd:body.mdd,omc:body.omc},mdd:body.mdd,omc:body.omc};
    data.tests.push(test); const reportId = localId(data.reports); const report = {id:reportId,report_no:'AST-R-' + String(reportId).padStart(6,'0'),test_id:id,status:'مسودة',issued_at:new Date().toLocaleString('ar-SA')}; data.reports.push(report); localQueue(data,'test',id,'create'); localAudit(data,'إضافة اختبار','test',test.test_no); saveLocal(data); return {ok:true,test_id:id,report_no:report.report_no};
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
    const id = localId(data.visits); data.visits.push(Object.assign({id:id,status:'مسودة',created_at:new Date().toLocaleString('ar-SA'),full_name:currentUser.full_name},body,{project_id:body.project_id ? Number(body.project_id) : null,sample_id:body.sample_id ? Number(body.sample_id) : null})); localQueue(data,'field_visit',id,'create'); localAudit(data,'إضافة زيارة ميدانية','field_visit',body.license_no); saveLocal(data); return {ok:true,id:id};
  }
  if (path === '/api/field/status') {
    const visit = data.visits.find(function(item) { return item.id === Number(body.id); }); if (!visit) throw new Error('الزيارة غير موجودة'); visit.status = body.status; localAudit(data,'تغيير حالة زيارة','field_visit',String(visit.id)); saveLocal(data); return {ok:true};
  }
  if (path === '/api/users') {
    if (!options || !options.method || options.method === 'GET') return data.users.map(function(item) { return {id:item.id,username:item.username,full_name:item.full_name,role:item.role,active:item.active,created_at:item.created_at}; });
  }
  if (path === '/api/users/create') {
    const id = localId(data.users); data.users.push({id:id,username:body.username,password:body.password,full_name:body.full_name,role:body.role,active:1,created_at:new Date().toLocaleString('ar-SA')}); localAudit(data,'إضافة مستخدم','user',body.username); saveLocal(data); return {ok:true,id:id};
  }
  if (path === '/api/users/update') {
    const user = data.users.find(function(item) { return item.id === Number(body.id); }); if (!user) throw new Error('المستخدم غير موجود'); Object.assign(user,body,{active:body.active ? 1 : 0}); if (!body.password) delete user.password; localAudit(data,'تعديل مستخدم','user',user.username); saveLocal(data); return {ok:true};
  }
  throw new Error('المسار غير مدعوم في العرض الثابت');
}

async function api(path, options) {
  const opts = options || {};
  if (STATIC_MODE) return staticApi(path, opts);
  const response = await fetch(path, Object.assign({headers:{'Content-Type':'application/json'}}, opts));
  let payload = {};
  try { payload = await response.json(); } catch (error) { throw new Error('استجابة غير صالحة من الخادم'); }
  if (!response.ok) throw new Error(payload.error || 'تعذر تنفيذ العملية');
  return payload;
}

function showToast(message, isError) {
  const toast = $('toast');
  toast.textContent = message;
  toast.className = 'toast ' + (isError ? 'error' : 'success');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function() { toast.className = 'toast hidden'; }, 4200);
}

function modal(html) {
  $('modalBody').innerHTML = html;
  $('modal').classList.remove('hidden');
}

function closeModal() {
  $('modal').classList.add('hidden');
  $('modalBody').innerHTML = '';
}

function fieldValue(form, key) {
  const element = form.elements[key];
  return element ? element.value.trim() : '';
}

function optionList(items, selected, label, value) {
  return items.map(function(item) {
    const itemValue = value(item);
    return '<option value="' + esc(itemValue) + '"' + (String(itemValue) === String(selected || '') ? ' selected' : '') + '>' + esc(label(item)) + '</option>';
  }).join('');
}

function navigate(page) {
  document.querySelectorAll('.page').forEach(function(element) { element.classList.remove('active'); });
  const target = $(page);
  if (!target) return;
  target.classList.add('active');
  document.querySelectorAll('.nav-link[data-page]').forEach(function(button) { button.classList.toggle('active', button.dataset.page === page); });
  const nav = document.querySelector('.nav-link[data-page="' + page + '"]');
  $('pageTitle').textContent = nav ? nav.textContent.trim() : 'أساس LIMS';
  $('pageKicker').textContent = page === 'projects' ? 'تنفيذ ومتابعة' : 'إدارة المختبر';
  $('sidebar').classList.remove('open');
  if (page === 'field') loadFieldRecent();
}

async function login(event) {
  event.preventDefault();
  try {
    const result = await api('/api/login', {method:'POST',body:JSON.stringify({username:$('loginUsername').value,password:$('loginPassword').value})});
    currentUser = result.user;
    $('login').classList.add('hidden');
    $('app').classList.remove('hidden');
    $('currentUser').textContent = result.user.full_name + ' — ' + (ROLE_NAMES[result.user.role] || result.user.role);
    $('usersNav').classList.toggle('hidden', result.user.role !== 'admin');
    await loadCatalog();
    await refresh();
    navigate('dashboard');
  } catch (error) {
    $('loginMessage').textContent = error.message;
  }
}

async function logout() {
  try { await api('/api/logout', {method:'POST'}); } catch (error) {}
  location.reload();
}

async function bootstrapStaticAdmin() {
  const username = window.prompt('اسم مستخدم المدير المحلي', 'admin');
  if (!username) return;
  const name = window.prompt('الاسم الكامل للمدير', 'مدير المختبر');
  if (!name) return;
  const password = window.prompt('اختر كلمة مرور محلية قوية (12 حرفاً على الأقل)');
  if (!password || password.length < 12) return showToast('كلمة المرور يجب ألا تقل عن 12 حرفاً', true);
  const data = localDB();
  if (data.users.length) return;
  data.users.push({id:1,username:username.trim(),password:password,full_name:name.trim(),role:'admin',active:1,created_at:new Date().toLocaleString('ar-SA')});
  saveLocal(data);
  $('staticSetup').classList.add('hidden');
  $('loginMessage').textContent = 'تم إنشاء الحساب المحلي. سجّل الدخول الآن.';
}

async function loadCatalog() {
  catalog = await api('/api/catalog');
  renderCatalog();
}

async function refresh() {
  dashboard = await api('/api/dashboard');
  renderDashboard();
  renderProjects();
  renderWorkOrders();
  renderClients();
  renderSamples();
  renderTests();
  renderReports();
  renderEquipment();
  renderAudit();
  if (currentUser && currentUser.role === 'admin') await renderUsers();
}

function renderDashboard() {
  if (!dashboard) return;
  $('metricProjects').textContent = dashboard.projects.filter(function(item) { return ['نشط','قيد المراجعة','موقوف'].indexOf(item.status) >= 0; }).length;
  $('metricOrders').textContent = dashboard.counts.work_orders || 0;
  $('metricSamples').textContent = dashboard.counts.samples || 0;
  $('metricReports').textContent = dashboard.counts.reports || 0;
  $('metricReview').textContent = (dashboard.alerts.awaiting_review || []).length;
  $('metricSync').textContent = (dashboard.counts.sync_queue || 0);
  $('syncIndicator').textContent = 'المزامنة: ' + (dashboard.counts.sync_queue || 0) + ' عملية بانتظار الربط المركزي';
  const priorities = [];
  (dashboard.alerts.overdue_work_orders || []).forEach(function(item) { priorities.push('<div class="priority-item overdue"><strong>أمر متأخر: ' + esc(item.order_no) + ' — ' + esc(item.title) + '</strong><small>' + esc(item.project_code) + ' · استحقاق ' + esc(item.due_date) + '</small></div>'); });
  (dashboard.alerts.blocked_projects || []).forEach(function(item) { priorities.push('<div class="priority-item blocked"><strong>مشروع متوقف: ' + esc(item.code) + ' — ' + esc(item.name) + '</strong><small>الأولوية ' + esc(item.priority) + (item.due_date ? ' · الاستحقاق ' + esc(item.due_date) : '') + '</small></div>'); });
  (dashboard.alerts.awaiting_review || []).forEach(function(item) { priorities.push('<div class="priority-item"><strong>ينتظر المراجعة: ' + esc(item.code || item.name) + '</strong><small>' + esc(item.name || item.entity) + '</small></div>'); });
  $('priorityList').innerHTML = priorities.join('') || '<div class="empty">لا توجد أولويات متأخرة أو عوائق حالياً.</div>';
  $('activityList').innerHTML = (dashboard.activity || []).map(function(item) { return '<div class="timeline-item"><strong>' + esc(item.action) + '</strong><small>' + esc(item.created_at) + ' · ' + esc(item.details || '') + '</small></div>'; }).join('') || '<div class="empty">لا توجد عمليات بعد.</div>';
  $('dashboardProjects').innerHTML = dashboard.projects.slice(0,6).map(function(project) {
    return '<button class="compact-project text-btn" type="button" data-project-open="' + project.id + '"><h4>' + esc(project.code) + ' — ' + esc(project.name) + '</h4><p>' + statusChip(project.status) + ' · ' + esc(project.samples_count) + ' عينة · ' + esc(project.reports_count) + ' تقرير</p></button>';
  }).join('') || '<div class="empty">ابدأ بإضافة مشروع.</div>';
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
  $('projectsTable').innerHTML = projects.map(function(project) {
    return '<tr><td><strong>' + esc(project.code) + '</strong><small>' + esc(project.name) + '</small></td><td>' + esc(project.client_name || '—') + '<small>' + esc(project.location || 'بدون موقع') + '</small></td><td>' + priorityChip(project.priority) + '</td><td>' + esc(project.due_date || 'غير محدد') + '</td><td><div class="progress"><span style="width:' + Math.min(100,Math.max(0,Number(project.progress) || 0)) + '%"></span></div><small>' + esc(project.progress || 0) + '%</small></td><td><select class="project-status" data-project-id="' + project.id + '">' + optionList(PROJECT_STATUSES, project.status, function(value) { return value; }, function(value) { return value; }) + '</select></td><td><small>' + esc(project.work_orders_count) + ' أمر · ' + esc(project.samples_count) + ' عينة</small><small>' + esc(project.tests_count) + ' اختبار · ' + esc(project.reports_count) + ' تقرير</small></td><td><div class="row-actions"><button class="text-btn" data-project-open="' + project.id + '" type="button">مساحة العمل</button><button class="text-btn" data-project-edit="' + project.id + '" type="button">تعديل</button></div></td></tr>';
  }).join('') || '<tr><td colspan="8" class="empty">لا توجد مشاريع مطابقة.</td></tr>';
  renderBoard(projects);
  renderRoadmap(projects);
}

function renderBoard(projects) {
  $('projectBoard').innerHTML = BOARD_STATUSES.map(function(status) {
    const cards = projects.filter(function(project) { return project.status === status; }).map(function(project) {
      return '<article class="kanban-card"><h4>' + esc(project.code) + ' — ' + esc(project.name) + '</h4><p>' + esc(project.client_name || 'بدون عميل') + '</p><div class="progress"><span style="width:' + Math.min(100,Number(project.progress) || 0) + '%"></span></div><div class="kanban-meta">' + priorityChip(project.priority) + '<span>' + esc(project.due_date || 'بلا تاريخ') + '</span></div><select class="project-status" data-project-id="' + project.id + '">' + optionList(PROJECT_STATUSES,project.status,function(value) { return value; },function(value) { return value; }) + '</select></article>';
    }).join('') || '<div class="empty">لا توجد مشاريع</div>';
    return '<section class="kanban-column"><h3>' + esc(status) + '</h3><div class="kanban-stack">' + cards + '</div></section>';
  }).join('');
}

function renderRoadmap(projects) {
  const dated = projects.slice().sort(function(a,b) { return String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')); });
  $('projectRoadmap').innerHTML = dated.map(function(project) {
    const progress = Math.min(100,Math.max(0,Number(project.progress) || 0));
    return '<article class="roadmap-row"><div><h4>' + esc(project.code) + ' — ' + esc(project.name) + '</h4><small>' + esc(project.start_date || 'بلا بداية') + ' ← ' + esc(project.due_date || 'بلا استحقاق') + '</small></div><div class="roadmap-track"><span style="width:' + progress + '%"></span></div><div>' + statusChip(project.status) + '<small>' + progress + '% مكتمل</small></div></article>';
  }).join('') || '<div class="empty">أضف تواريخ بداية واستحقاق للمشاريع لإظهار خارطة الطريق.</div>';
}

function setProjectView(view) {
  projectView = view;
  document.querySelectorAll('.view-btn').forEach(function(button) { button.classList.toggle('active', button.dataset.projectView === view); });
  $('projectTableView').classList.toggle('hidden', view !== 'table');
  $('projectBoardView').classList.toggle('hidden', view !== 'board');
  $('projectRoadmapView').classList.toggle('hidden', view !== 'roadmap');
}

function renderWorkOrders() {
  $('workOrdersTable').innerHTML = (dashboard ? dashboard.work_orders : []).map(function(order) {
    return '<tr><td><strong>' + esc(order.order_no) + '</strong></td><td>' + esc(order.title) + '<small>' + esc(order.description || '') + '</small></td><td>' + esc(order.project_code) + '<small>' + esc(order.project_name) + '</small></td><td>' + esc(order.assignee_name || 'غير محدد') + '</td><td>' + priorityChip(order.priority) + '</td><td>' + esc(order.due_date || '—') + '</td><td>' + statusChip(order.status) + '</td></tr>';
  }).join('') || '<tr><td colspan="7" class="empty">لا توجد أوامر عمل.</td></tr>';
}

function renderClients() {
  $('clientsTable').innerHTML = (dashboard ? dashboard.clients : []).map(function(client) { return '<tr><td>' + esc(client.name) + '</td><td>' + esc(client.phone || '') + '</td><td>' + esc(client.email || '') + '</td></tr>'; }).join('') || '<tr><td colspan="3" class="empty">لا يوجد عملاء.</td></tr>';
}

function renderSamples() {
  $('samplesTable').innerHTML = (dashboard ? dashboard.samples : []).map(function(sample) { return '<tr><td><strong>' + esc(sample.sample_no) + '</strong></td><td>' + esc(sample.project_code || '—') + '<small>' + esc(sample.project_name || '') + '</small></td><td>' + esc(sample.material) + '</td><td>' + esc(sample.received_date) + '</td><td>' + statusChip(sample.status) + '</td></tr>'; }).join('') || '<tr><td colspan="5" class="empty">لا توجد عينات.</td></tr>';
}

function renderTests() {
  $('testsTable').innerHTML = (dashboard ? dashboard.tests : []).map(function(test) {
    const result = test.mdd !== null && test.mdd !== undefined ? 'MDD ' + Number(test.mdd).toFixed(3) + ' / OMC ' + Number(test.omc).toFixed(2) + '%' : '—';
    return '<tr><td><strong>' + esc(test.test_no) + '</strong></td><td>' + esc(test.sample_no) + '</td><td>' + esc(test.name_ar) + '<small>' + esc(test.code) + '</small></td><td>' + esc(test.standard) + '</td><td>' + esc(result) + '</td><td>' + statusChip(test.status) + '</td></tr>';
  }).join('') || '<tr><td colspan="6" class="empty">لا توجد اختبارات.</td></tr>';
}

function renderCatalog() {
  const query = $('catalogSearch') ? $('catalogSearch').value.toLowerCase() : '';
  $('catalogTable').innerHTML = catalog.filter(function(item) { return [item.code,item.name_ar,item.name_en,item.standard,item.category].join(' ').toLowerCase().indexOf(query) >= 0; }).map(function(item) {
    return '<tr><td>' + esc(item.code) + '</td><td>' + esc(item.name_ar) + '<small>' + esc(item.name_en || '') + '</small></td><td>' + esc(item.category) + '</td><td>' + esc(item.standard) + '</td><td>' + esc(item.version || '—') + '</td></tr>';
  }).join('') || '<tr><td colspan="5" class="empty">لا توجد نتائج.</td></tr>';
}

function renderReports() {
  $('reportsTable').innerHTML = (dashboard ? dashboard.reports : []).map(function(report) {
    return '<tr><td><strong>' + esc(report.report_no) + '</strong></td><td>' + esc(report.sample_no || '') + '<small>' + esc(report.name_ar) + ' · ' + esc(report.test_no) + '</small></td><td>' + statusChip(report.status) + '</td><td>' + esc(report.issued_at || '—') + '</td><td><div class="row-actions"><button class="text-btn" data-report-print="' + report.test_id + '" type="button">طباعة</button><button class="text-btn" data-report-review="' + report.id + '" type="button">حالة</button></div></td></tr>';
  }).join('') || '<tr><td colspan="5" class="empty">لا توجد تقارير.</td></tr>';
}

function renderEquipment() {
  $('equipmentTable').innerHTML = (dashboard ? dashboard.equipment : []).map(function(item) { return '<tr><td>' + esc(item.name) + '</td><td>' + esc(item.serial_no || '') + '</td><td>' + esc(item.last_calibration || '') + '</td><td>' + esc(item.next_calibration || '') + '</td><td>' + esc(item.certificate_no || '') + '</td><td>' + statusChip(item.status) + '</td></tr>'; }).join('') || '<tr><td colspan="6" class="empty">لا توجد أجهزة.</td></tr>';
}

function renderAudit() {
  $('auditTable').innerHTML = (dashboard ? dashboard.audit : []).map(function(item) { return '<tr><td>' + esc(item.created_at) + '</td><td>' + esc(item.full_name || '') + '</td><td>' + esc(item.action) + '</td><td>' + esc(item.entity || '') + '</td><td>' + esc(item.details || '') + '</td></tr>'; }).join('') || '<tr><td colspan="5" class="empty">لا توجد عمليات.</td></tr>';
}

async function renderUsers() {
  try {
    const users = await api('/api/users');
    $('usersTable').innerHTML = users.map(function(user) { return '<tr><td>' + esc(user.username) + '</td><td>' + esc(user.full_name) + '</td><td>' + esc(ROLE_NAMES[user.role] || user.role) + '</td><td>' + (user.active ? 'نشط' : 'موقوف') + '</td><td>' + esc(user.created_at) + '</td><td><button class="text-btn" data-user-edit="' + user.id + '" type="button">تعديل</button></td></tr>'; }).join('');
    $('usersTable').dataset.users = JSON.stringify(users);
  } catch (error) {
    $('usersTable').innerHTML = '<tr><td colspan="6" class="empty">ليس لديك صلاحية عرض المستخدمين.</td></tr>';
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
    if (name === 'samples') return '<table><thead><tr><th>العينة</th><th>المادة</th><th>الحالة</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.sample_no) + '</td><td>' + esc(item.material) + '</td><td>' + statusChip(item.status) + '</td></tr>'; }).join('') + '</tbody></table>';
    if (name === 'tests') return '<table><thead><tr><th>الاختبار</th><th>العينة</th><th>الاسم</th><th>الحالة</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.test_no) + '</td><td>' + esc(item.sample_no) + '</td><td>' + esc(item.name_ar) + '</td><td>' + statusChip(item.status) + '</td></tr>'; }).join('') + '</tbody></table>';
    if (name === 'results') return '<table><thead><tr><th>الاختبار</th><th>البند</th><th>القيمة</th><th>الوحدة</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.test_no) + '</td><td>' + esc(item.field_name) + '</td><td>' + esc(item.value) + '</td><td>' + esc(item.unit || '') + '</td></tr>'; }).join('') + '</tbody></table>';
    if (name === 'reports') return '<table><thead><tr><th>التقرير</th><th>الاختبار</th><th>الحالة</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.report_no) + '</td><td>' + esc(item.name_ar || item.test_no) + '</td><td>' + statusChip(item.status) + '</td></tr>'; }).join('') + '</tbody></table>';
    return '<table><thead><tr><th>الرخصة</th><th>الموقع</th><th>الحالة</th><th>التاريخ</th></tr></thead><tbody>' + items.map(function(item) { return '<tr><td>' + esc(item.license_no) + '</td><td>' + esc(item.location || '') + '</td><td>' + statusChip(item.status) + '</td><td>' + esc(item.created_at) + '</td></tr>'; }).join('') + '</tbody></table>';
  }
  const summary = '<div class="workspace-summary"><div><strong>' + space.work_orders.length + '</strong>أوامر العمل</div><div><strong>' + space.samples.length + '</strong>العينات</div><div><strong>' + space.tests.length + '</strong>الاختبارات</div><div><strong>' + space.results.length + '</strong>النتائج</div><div><strong>' + space.reports.length + '</strong>التقارير</div></div>';
  const tabButtons = tabs.map(function(tab,index) { return '<button type="button" class="' + (index === 0 ? 'active' : '') + '" data-workspace-tab="' + tab[0] + '">' + tab[1] + ' (' + tab[2].length + ')</button>'; }).join('');
  modal('<h2>' + esc(p.code) + ' — ' + esc(p.name) + '</h2><p>' + esc(p.client_name || 'بدون عميل') + ' · ' + esc(p.location || 'بدون موقع') + ' · ' + statusChip(p.status) + '</p>' + summary + '<div class="workspace-tabs">' + tabButtons + '<button type="button" data-work-order-for="' + p.id + '">+ أمر عمل</button></div><div id="workspaceContent" class="workspace-content">' + rows(tabs[0][0],tabs[0][2]) + '</div>');
  $('modalBody').dataset.workspace = JSON.stringify({tabs:tabs});
}

function openWorkOrderForm(projectId) {
  const projects = dashboard ? dashboard.projects : [];
  modal('<h2>أمر عمل جديد</h2><p>ينشئ أمراً مرتبطاً بمشروع ويضيفه إلى طابور المزامنة المركزي.</p><form id="workOrderForm"><div class="modal-grid"><label>المشروع<select name="project_id" required><option value="">— اختر المشروع —</option>' + optionList(projects,projectId,function(item){return item.code + ' — ' + item.name;},function(item){return item.id;}) + '</select></label><label>عنوان أمر العمل<input name="title" required></label><label>الأولوية<select name="priority">' + optionList(PRIORITIES,'متوسطة',function(item){return item;},function(item){return item;}) + '</select></label><label>الحالة<select name="status">' + optionList(WORK_ORDER_STATUSES,'مفتوح',function(item){return item;},function(item){return item;}) + '</select></label><label>تاريخ التنفيذ<input name="scheduled_date" type="date"></label><label>تاريخ الاستحقاق<input name="due_date" type="date"></label><label>معرف المكلّف<input name="assigned_to" type="number" min="1"></label><label style="grid-column:1/-1">الوصف<textarea name="description"></textarea></label></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary" type="submit">حفظ أمر العمل</button></div></form>');
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
  modal('<h2>تسجيل عينة</h2><form id="sampleForm"><div class="modal-grid"><label>رقم العينة<input name="sample_no" required></label><label>المشروع<select name="project_id"><option value="">— غير مرتبط —</option>' + optionList(projects,'',function(item){return item.code + ' — ' + item.name;},function(item){return item.id;}) + '</select></label><label>المادة<select name="material"><option>تربة</option><option>ركام</option><option>خرسانة</option><option>أسفلت</option><option>طلاءات</option><option>مواد بناء</option></select></label><label>تاريخ الاستلام<input name="received_date" type="date" value="' + today() + '" required></label><label>المصدر<input name="source"></label><label>ملاحظات<textarea name="notes"></textarea></label></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ العينة</button></div></form>');
}

function openEquipmentForm() {
  modal('<h2>إضافة جهاز</h2><form id="equipmentForm"><div class="modal-grid"><label>اسم الجهاز<input name="name" required></label><label>الرقم التسلسلي<input name="serial_no"></label><label>الشركة المصنعة<input name="manufacturer"></label><label>الموديل<input name="model"></label><label>آخر معايرة<input name="last_calibration" type="date"></label><label>المعايرة القادمة<input name="next_calibration" type="date"></label><label>رقم الشهادة<input name="certificate_no"></label><label>ملاحظات<textarea name="notes"></textarea></label></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ الجهاز</button></div></form>');
}

function genericFields(testCatalog) {
  const fields = TEST_FIELDS[testCatalog.code] || [['result','النتيجة','']];
  return fields.map(function(item) { return '<label>' + esc(item[1]) + (item[2] ? ' (' + esc(item[2]) + ')' : '') + '<input name="result_' + esc(item[0]) + '" type="number" step="any"></label>'; }).join('');
}

function testFormContent() {
  return '<h2>إضافة اختبار</h2><form id="testForm"><div class="modal-grid"><label>نوع الاختبار<select id="testCatalogSelect" name="catalog_id" required><option value="">— اختر الاختبار —</option>' + optionList(catalog,'',function(item){return item.code + ' — ' + item.name_ar;},function(item){return item.id;}) + '</select></label><label>معرف العينة<input name="sample_id" type="number" min="1" required></label><label>رقم الاختبار (اختياري)<input name="test_no"></label><label>تاريخ البدء<input name="started_at" type="datetime-local"></label></div><div id="testDynamic" class="modal-grid"></div><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary" type="submit">حفظ الاختبار</button></div></form>';
}

function openTestForm() {
  modal(testFormContent());
}

function updateTestDynamic() {
  const selected = catalog.find(function(item) { return item.id === Number($('testCatalogSelect').value); });
  if (!selected) return $('testDynamic').innerHTML = '';
  if (selected.code === 'D1557' || selected.code === 'D698') {
    let points = '';
    for (let i=1;i<=5;i++) points += '<label>رطوبة النقطة ' + i + ' %<input name="w' + i + '" type="number" step="any"></label><label>القالب + التربة الرطبة ' + i + ' g<input name="wet' + i + '" type="number" step="any"></label>';
    $('testDynamic').innerHTML = '<label>وزن القالب g<input name="mold_weight" type="number" step="any"></label><label>حجم القالب cm³<input name="mold_volume" type="number" value="944" step="any"></label>' + points;
  } else {
    $('testDynamic').innerHTML = genericFields(selected);
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
  modal('<h2>' + (user ? 'تعديل مستخدم' : 'مستخدم جديد') + '</h2><form id="userForm"><input type="hidden" name="id" value="' + esc(value.id || '') + '"><div class="modal-grid"><label>اسم المستخدم<input name="username" required ' + (user ? 'readonly' : '') + ' value="' + esc(value.username || '') + '"></label><label>الاسم الكامل<input name="full_name" required value="' + esc(value.full_name || '') + '"></label><label>الدور<select name="role">' + optionList(Object.keys(ROLE_NAMES),value.role || 'technician',function(item){return ROLE_NAMES[item];},function(item){return item;}) + '</select></label><label>كلمة المرور ' + (user ? '(اتركها فارغة للإبقاء)' : '') + '<input name="password" type="password" ' + (user ? '' : 'required') + ' minlength="12"></label>' + (user ? '<label><input name="active" type="checkbox" ' + (value.active ? 'checked' : '') + '> الحساب نشط</label>' : '') + '</div><p class="muted">كلمة المرور لا تقل عن 12 حرفاً ولا تُحفظ في Git.</p><div class="modal-actions"><button class="btn secondary" type="button" data-modal-close>إلغاء</button><button class="btn primary">حفظ المستخدم</button></div></form>');
}

async function submitSimple(form, path) {
  const data = {};
  new FormData(form).forEach(function(value,key) { data[key] = value; });
  if (path === '/api/users/update') data.active = form.elements.active.checked;
  await api(path,{method:'POST',body:JSON.stringify(data)});
  closeModal(); await refresh(); showToast('تم الحفظ');
}

async function changeProjectStatus(id, status) {
  try {
    await api('/api/projects/status',{method:'POST',body:JSON.stringify({id:Number(id),status:status})});
    await refresh(); showToast('تم تحديث حالة المشروع');
  } catch (error) {
    showToast(error.message,true); renderProjects();
  }
}

async function changeReportStatus(id) {
  const status = window.prompt('اختر الحالة: مسودة، قيد المراجعة، معتمد، مرفوض');
  if (!status) return;
  try { await api('/api/reports/status',{method:'POST',body:JSON.stringify({id:Number(id),status:status.trim()})}); await refresh(); showToast('تم تحديث التقرير'); } catch (error) { showToast(error.message,true); }
}

async function printReport(testId) {
  const report = await api('/api/report/' + testId);
  const inputRows = Object.keys(report.data.inputs || {}).map(function(key) { return '<tr><th>' + esc(key) + '</th><td>' + esc(report.data.inputs[key]) + '</td></tr>'; }).join('');
  const resultRows = Object.keys(report.data.results || {}).map(function(key) { return '<tr><th>' + esc(key) + '</th><td>' + esc(report.data.results[key]) + '</td></tr>'; }).join('');
  const popup = window.open('', '_blank', 'noopener');
  if (!popup) return showToast('السماح بالنوافذ المنبثقة مطلوب للطباعة',true);
  popup.document.write('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>' + esc(report.report_no) + '</title><style>body{font-family:Tahoma;padding:30px;color:#14213d}h1,h2{text-align:center}table{width:100%;border-collapse:collapse;margin:16px 0}td,th{padding:8px;border:1px solid #94a3b8;text-align:right}</style></head><body><h1>' + esc(report.lab_name) + '</h1><h2>تقرير اختبار</h2><table><tr><th>رقم التقرير</th><td>' + esc(report.report_no) + '</td></tr><tr><th>رقم الاختبار</th><td>' + esc(report.test_no) + '</td></tr><tr><th>العينة</th><td>' + esc(report.sample_no) + '</td></tr><tr><th>الاختبار</th><td>' + esc(report.name_ar) + '</td></tr><tr><th>المعيار</th><td>' + esc(report.standard) + '</td></tr><tr><th>الحالة</th><td>' + esc(report.status) + '</td></tr></table><h3>المدخلات</h3><table>' + (inputRows || '<tr><td>—</td></tr>') + '</table><h3>النتائج</h3><table>' + (resultRows || '<tr><td>—</td></tr>') + '</table></body></html>');
  popup.document.close();
  popup.focus();
  popup.print();
}

function renderFieldTests() {
  $('fieldTests').innerHTML = fieldTests.map(function(test,index) {
    return '<div class="field-test-row"><input data-field-test="' + index + '" data-field-key="name" value="' + esc(test.name) + '" placeholder="اسم الاختبار"><input data-field-test="' + index + '" data-field-key="standard" value="' + esc(test.standard) + '" placeholder="المعيار / ASTM"><input data-field-test="' + index + '" data-field-key="result" value="' + esc(test.result) + '" placeholder="النتيجة / القراءات"><button class="btn danger" data-field-remove="' + index + '" type="button">حذف</button></div>';
  }).join('') || '<div class="empty">أضف الاختبارات المنفذة في هذه الزيارة.</div>';
}

async function searchLicense() {
  const license = $('fieldLicense').value.trim();
  if (!license) return showToast('أدخل رقم الرخصة أولاً',true);
  try {
    const rows = await api('/api/field/search?license=' + encodeURIComponent(license));
    if (!rows.length) return showToast('لا توجد بيانات سابقة لهذه الرخصة');
    const visit = rows[0];
    $('fieldContractor').value = visit.contractor_name || '';
    $('fieldProjectName').value = visit.project_name || '';
    $('fieldSector').value = visit.sector_name || '';
    $('fieldLayer').value = visit.layer_no || '';
    $('fieldLocation').value = visit.location || '';
    $('fieldProjectId').value = visit.project_id || '';
    $('fieldSampleId').value = visit.sample_id || '';
    showToast('تمت تعبئة بيانات الزيارة السابقة');
  } catch (error) { showToast(error.message,true); }
}

function getLocation() {
  if (!navigator.geolocation) return showToast('تحديد الموقع غير متاح في هذا المتصفح',true);
  navigator.geolocation.getCurrentPosition(function(position) {
    fieldLat = position.coords.latitude; fieldLng = position.coords.longitude;
    $('gpsStatus').textContent = 'تم تحديد الموقع: ' + fieldLat.toFixed(6) + ', ' + fieldLng.toFixed(6);
  }, function(error) { showToast('تعذر تحديد الموقع: ' + error.message,true); }, {enableHighAccuracy:true,timeout:10000});
}

async function saveFieldVisit() {
  const license = $('fieldLicense').value.trim();
  if (!license) return showToast('رقم الرخصة مطلوب',true);
  try {
    const result = await api('/api/field/visits',{method:'POST',body:JSON.stringify({
      license_no:license,contractor_name:$('fieldContractor').value,project_name:$('fieldProjectName').value,sector_name:$('fieldSector').value,layer_no:$('fieldLayer').value,location:$('fieldLocation').value,latitude:fieldLat,longitude:fieldLng,project_id:$('fieldProjectId').value || null,sample_id:$('fieldSampleId').value || null,tests:fieldTests,notes:$('fieldNotes').value,status:'مسودة'
    })});
    $('fieldMessage').textContent = 'تم حفظ الزيارة رقم ' + result.id;
    fieldTests = []; renderFieldTests(); await loadFieldRecent(); await refresh();
  } catch (error) { $('fieldMessage').textContent = error.message; }
}

async function loadFieldRecent() {
  try {
    const rows = await api('/api/field/recent');
    $('fieldRecent').innerHTML = rows.map(function(item) {
      return '<article class="field-item"><strong>' + esc(item.license_no) + ' — ' + esc(item.project_name || '') + '</strong><small>' + esc(item.contractor_name || '') + ' · ' + esc(item.created_at) + '</small><div>' + statusChip(item.status) + '</div><div class="field-item-actions"><button class="btn secondary" data-field-status="' + item.id + '|مرسلة" type="button">إرسال</button><button class="btn secondary" data-field-status="' + item.id + '|قيد المراجعة" type="button">مراجعة</button><button class="btn primary" data-field-status="' + item.id + '|معتمدة" type="button">اعتماد</button><button class="btn danger" data-field-status="' + item.id + '|مرفوضة" type="button">رفض</button></div></article>';
    }).join('') || '<div class="empty">لا توجد زيارات ميدانية بعد.</div>';
  } catch (error) { $('fieldRecent').innerHTML = '<div class="empty">تعذر تحميل الزيارات.</div>'; }
}

async function setFieldStatus(token) {
  const parts = token.split('|');
  try { await api('/api/field/status',{method:'POST',body:JSON.stringify({id:Number(parts[0]),status:parts[1]})}); await loadFieldRecent(); await refresh(); showToast('تم تحديث حالة الزيارة'); } catch (error) { showToast(error.message,true); }
}

function bindEvents() {
  $('loginForm').addEventListener('submit',login);
  $('logoutBtn').addEventListener('click',logout);
  $('staticSetup').addEventListener('click',bootstrapStaticAdmin);
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
  $('searchLicenseBtn').addEventListener('click',searchLicense);
  $('getLocationBtn').addEventListener('click',getLocation);
  $('addFieldTest').addEventListener('click',function() { if (fieldTests.length >= 4) return showToast('الحد الأقصى أربعة اختبارات للزيارة',true); fieldTests.push({name:'',standard:'',result:''}); renderFieldTests(); });
  $('saveFieldVisit').addEventListener('click',saveFieldVisit);
  document.addEventListener('change',function(event) {
    if (event.target.matches('.project-status')) changeProjectStatus(event.target.dataset.projectId,event.target.value);
    if (event.target.id === 'testCatalogSelect') updateTestDynamic();
    if (event.target.matches('[data-field-test]')) fieldTests[Number(event.target.dataset.fieldTest)][event.target.dataset.fieldKey] = event.target.value;
  });
  document.addEventListener('click',async function(event) {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.hasAttribute('data-modal-close')) return closeModal();
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
      $('workspaceContent').innerHTML = lines;
      return;
    }
    if (button.dataset.fieldRemove !== undefined) { fieldTests.splice(Number(button.dataset.fieldRemove),1); renderFieldTests(); return; }
    if (button.dataset.fieldStatus) return setFieldStatus(button.dataset.fieldStatus);
    if (button.dataset.reportPrint) return printReport(button.dataset.reportPrint);
    if (button.dataset.reportReview) return changeReportStatus(button.dataset.reportReview);
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
      if (form.id === 'userForm') await submitSimple(form,form.elements.id.value ? '/api/users/update' : '/api/users/create');
    } catch (error) { showToast(error.message,true); }
  });
}

function init() {
  bindEvents();
  if (STATIC_MODE && !localDB().users.length) $('staticSetup').classList.remove('hidden');
}

document.addEventListener('DOMContentLoaded',init);

