'use strict';
(function(){
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const types=['swot','risk','kpi','action'];
  let data={swot:[],risks:[],kpis:[],actions:[]};
  const stageNames=['مراجعة واعتماد التقارير','تحليل الانحرافات','اجتماع الإدارة العليا','اتخاذ القرارات','إعداد خطة العمل','تنفيذ الإجراءات','المتابعة والرقابة','قياس النتائج','التحسين المستمر'];
  const stageHints=['تحقق من صحة البيانات واعتماد المخرجات','حدد الفجوات والأسباب الجذرية والمخاطر','سجل العرض والمناقشات والأولويات','اعتمد القرار والمسؤول والميزانية','حدد المهام والمواعيد ومؤشرات الأداء','سجل التنفيذ والأدلة والمعوقات','حدّث نسب الإنجاز والتنبيهات','قارن خط الأساس بالنتيجة والمستهدف','وثّق الدروس وحدّث الإجراءات'];
  let cycleData={cycles:[],steps:[]};

  function input(type,name,label,inputType='text',extra=''){
    return '<label><span>'+label+'</span><input data-qm-field="'+type+'" name="'+name+'" type="'+inputType+'" '+extra+'></label>';
  }
  function managementFields(type){
    const common=input(type,'title','العنوان / الاسم')+input(type,'owner_id','معرّف المسؤول','number','min="1"');
    if(type==='swot') return common+'<label><span>التصنيف</span><select data-qm-field="'+type+'" name="quadrant"><option value="strength">نقطة قوة</option><option value="weakness">نقطة ضعف</option><option value="opportunity">فرصة</option><option value="threat">تهديد</option></select></label>'+input(type,'description','التفاصيل');
    if(type==='risk') return common+input(type,'category','الفئة')+input(type,'probability','الاحتمالية 1-5','number','min="1" max="5" value="1"')+input(type,'impact','الأثر 1-5','number','min="1" max="5" value="1"')+input(type,'due_date','تاريخ الاستحقاق','date')+input(type,'mitigation','خطة المعالجة');
    if(type==='kpi') return common+input(type,'unit','الوحدة')+input(type,'target','المستهدف','number','step="any"')+input(type,'actual','الفعلي','number','step="any"')+input(type,'period','الفترة');
    return common+input(type,'source_type','المصدر')+input(type,'due_date','تاريخ الاستحقاق','date')+input(type,'description','وصف الإجراء');
  }
  function rowsFor(type){return type==='swot'?data.swot:type==='risk'?data.risks:type==='kpi'?data.kpis:data.actions;}
  function renderManagement(type){
    const fields=document.getElementById('qm-'+type+'-fields');
    if(fields&&!fields.dataset.ready){fields.innerHTML=managementFields(type);fields.dataset.ready='1';}
    const host=document.getElementById('qm-'+type+'-rows'); if(!host)return;
    const rows=rowsFor(type);
    host.innerHTML=rows.length?rows.map(r=>{
      const score=type==='risk'?Number(r.score||0):0;
      const cls=score>=15?'risk-high':score>=6?'risk-medium':score?'risk-low':'';
      const meta=type==='swot'?({strength:'قوة',weakness:'ضعف',opportunity:'فرصة',threat:'تهديد'}[r.quadrant]||r.quadrant):type==='risk'?'درجة الخطر '+score+'/25':type==='kpi'?'الإنجاز '+(r.achievement||0)+'%':(r.status||'open');
      const value=type==='risk'?'احتمال '+r.probability+' × أثر '+r.impact:type==='kpi'?r.actual+' / '+r.target+' '+esc(r.unit||''):esc(r.owner_name||'غير مسند');
      return '<div class="qm-row '+cls+'"><div><strong>'+esc(r.title||r.name)+'</strong><small>'+esc(meta)+'</small></div><span>'+value+'</span><span>'+esc(r.owner_name||'—')+'</span><span>'+esc(r.due_date||r.period||r.status||'—')+'</span><button class="text-btn danger-link" data-qm-delete="'+type+'" data-id="'+r.id+'" type="button">حذف</button></div>';
    }).join(''):'<div class="empty-state">لا توجد سجلات بعد.</div>';
  }
  async function loadManagement(){
    data=await api('/api/quality/management');
    types.forEach(renderManagement);
  }
  function managementPayload(type){
    const values={type};
    document.querySelectorAll('[data-qm-field="'+type+'"]').forEach(el=>{values[el.name]=el.value||null;});
    return values;
  }
  function clearManagement(type){document.querySelectorAll('[data-qm-field="'+type+'"]').forEach(el=>{if(el.name==='probability'||el.name==='impact')el.value='1';else if(el.tagName!=='SELECT')el.value='';});}

  function renderStageRail(){
    const host=document.getElementById('managementStages');if(!host)return;
    host.innerHTML=stageNames.map((n,i)=>'<div class="management-stage"><b>'+(i+1)+'</b><span>'+esc(n)+'</span></div>').join('');
  }
  function cycleProgress(c){return c.status==='completed'?100:Math.max(0,Math.min(100,Math.round((Number(c.current_stage)-1)*100/9)));}
  function stageFields(stage){
    const map={
      1:'<label>مرجع التقارير المعتمدة<input name="report_refs"></label><label>حالة الاعتماد<select name="approval"><option>معتمد</option><option>مع ملاحظات</option><option>مرفوض</option></select></label>',
      2:'<label>الانحراف / الفجوة<textarea name="deviation"></textarea></label><label>السبب الجذري<textarea name="root_cause"></textarea></label>',
      3:'<label>الحضور والأطراف<input name="attendees"></label><label>الأولويات المتفق عليها<textarea name="priorities"></textarea></label>',
      4:'<label>المسؤول عن القرار<input name="responsible"></label><label>الموعد المستهدف<input name="deadline" type="date"></label>',
      5:'<label>مؤشر الأداء KPI<input name="kpi"></label><label>الموعد النهائي<input name="deadline" type="date"></label>',
      6:'<label>دليل التنفيذ / مرجع المرفق<input name="evidence"></label><label>نسبة الإنجاز %<input name="progress" type="number" min="0" max="100"></label>',
      7:'<label>نسبة الإنجاز %<input name="progress" type="number" min="0" max="100"></label><label>التنبيه / العائق<textarea name="alert"></textarea></label>',
      8:'<label>النتيجة قبل<input name="before" type="number" step="any"></label><label>النتيجة بعد<input name="after" type="number" step="any"></label>',
      9:'<label>الدروس المستفادة<textarea name="lessons"></textarea></label><label>الإجراء القياسي المحدث<textarea name="standard_update"></textarea></label>'
    }; return map[stage]||'';
  }
  function renderCycleCreate(){
    const host=document.getElementById('qualityCycleCreateFields');if(!host)return;
    host.innerHTML='<label>عنوان الدورة<input name="title" required></label><label>الهدف التشغيلي<textarea name="objective"></textarea></label><label>معرّف المسؤول<input name="owner_id" type="number" min="1"></label><label>تاريخ البداية<input name="start_date" type="date"></label><label>تاريخ الاستحقاق<input name="due_date" type="date"></label><label>خط الأساس<input name="baseline" type="number" step="any" value="0"></label><label>المستهدف<input name="target" type="number" step="any" value="100"></label>';
  }
  function renderCycles(){
    const host=document.getElementById('qualityCycles');if(!host)return;
    host.innerHTML=cycleData.cycles.length?cycleData.cycles.map(c=>{
      const steps=cycleData.steps.filter(s=>Number(s.cycle_id)===Number(c.id));
      const active=steps.find(s=>s.status==='active');
      const progress=cycleProgress(c);
      const activeForm=(c.status==='active'&&active)?'<form class="cycle-inline-stage" data-cycle-stage-form="'+c.id+'" data-stage="'+active.stage+'"><div class="stage-guidance"><strong>'+active.stage+'. '+esc(stageNames[active.stage-1])+'</strong><p>'+esc(stageHints[active.stage-1])+'</p></div><div class="qc-form-grid"><label>ملخص التنفيذ والدليل<textarea name="notes" required></textarea></label>'+stageFields(Number(active.stage))+'<label>القرار / النتيجة<textarea name="decision"></textarea></label></div><button class="btn primary" type="submit">'+(Number(active.stage)===9?'إكمال الدورة واعتماد التحسين':'إكمال المرحلة والانتقال للتالية')+'</button></form>':'';
      return '<article class="cycle-card '+(c.status==='completed'?'is-complete':'')+'"><div class="cycle-card-head"><div><span class="cycle-state">'+(c.status==='completed'?'مكتملة':'المرحلة '+c.current_stage+' من 9')+'</span><h4>'+esc(c.title)+'</h4><p>'+esc(c.objective||'بدون هدف وصفي')+'</p></div><div class="cycle-score"><strong>'+progress+'%</strong><small>تقدم الدورة</small></div></div><div class="cycle-progress"><span style="width:'+progress+'%"></span></div><div class="cycle-meta"><span>المسؤول: '+esc(c.owner_name||'—')+'</span><span>الاستحقاق: '+esc(c.due_date||'—')+'</span><span>القياس: '+esc(c.baseline)+' ← '+esc(c.result)+' / '+esc(c.target)+'</span></div>'+activeForm+(c.status==='active'?'<div class="cycle-result"><label>النتيجة الحالية <input type="number" step="any" value="'+esc(c.result)+'" data-cycle-result="'+c.id+'"></label><button class="btn secondary" data-save-cycle-result="'+c.id+'" type="button">تحديث القياس</button></div>':'')+'</article>';
    }).join(''):'<div class="empty-state">لا توجد دورة إدارة بعد. أنشئ أول دورة من نفس البطاقة.</div>';
  }
  async function loadCycles(){cycleData=await api('/api/quality/cycles');renderCycles();}
  function formObject(form){const out={};new FormData(form).forEach((v,k)=>{out[k]=v;});return out;}

  document.addEventListener('click',async e=>{
    const save=e.target.closest('[data-qm-inline-save]');
    if(save){
      const type=save.dataset.qmInlineSave,body=managementPayload(type);
      if(!body.title)return showToast('أدخل العنوان أولًا',true);
      save.disabled=true;try{await api('/api/quality/management',{method:'POST',body:JSON.stringify(body)});clearManagement(type);await loadManagement();showToast('تم حفظ السجل');}catch(err){showToast(err.message||'تعذر الحفظ',true);}finally{save.disabled=false;}return;
    }
    const del=e.target.closest('[data-qm-delete]');
    if(del){
      if(!confirm('حذف هذا السجل؟'))return;
      try{await api('/api/quality/management/delete',{method:'POST',body:JSON.stringify({type:del.dataset.qmDelete,id:Number(del.dataset.id)})});await loadManagement();showToast('تم الحذف');}catch(err){showToast(err.message||'تعذر الحذف',true);}return;
    }
    const result=e.target.closest('[data-save-cycle-result]');
    if(result){
      const id=Number(result.dataset.saveCycleResult),input=document.querySelector('[data-cycle-result="'+id+'"]');
      try{await api('/api/quality/cycles',{method:'POST',body:JSON.stringify({action:'update_result',cycle_id:id,result:input.value})});await loadCycles();showToast('تم تحديث القياس الفعلي');}catch(err){showToast(err.message||'تعذر تحديث القياس',true);}
    }
  });

  document.addEventListener('submit',async e=>{
    const create=e.target.closest('#qualityCycleInlineForm');
    if(create){
      e.preventDefault();const values=formObject(create);if(!values.title)return showToast('أدخل عنوان الدورة',true);
      const btn=create.querySelector('button[type="submit"]');btn.disabled=true;
      try{await api('/api/quality/cycles',{method:'POST',body:JSON.stringify(Object.assign({action:'create'},values))});create.reset();renderCycleCreate();await loadCycles();showToast('تم إنشاء دورة الإدارة وبدء مرحلة المراجعة');}catch(err){showToast(err.message||'تعذر إنشاء الدورة',true);}finally{btn.disabled=false;}return;
    }
    const stage=e.target.closest('[data-cycle-stage-form]');
    if(stage){
      e.preventDefault();const values=formObject(stage),cycleId=Number(stage.dataset.cycleStageForm),stageNo=Number(stage.dataset.stage);
      const details=Object.assign({},values);delete details.notes;delete details.decision;
      const btn=stage.querySelector('button[type="submit"]');btn.disabled=true;
      try{await api('/api/quality/cycles',{method:'POST',body:JSON.stringify({action:'complete_stage',cycle_id:cycleId,stage:stageNo,notes:values.notes,decision:values.decision,details})});await loadCycles();showToast(stageNo===9?'تم إكمال الدورة واعتماد التحسين':'تم اعتماد المرحلة والانتقال للتالية');}catch(err){showToast(err.message||'تعذر حفظ المرحلة',true);}finally{btn.disabled=false;}
    }
  });

  types.forEach(renderManagement);
  renderStageRail();
  renderCycleCreate();
  loadManagement().catch(()=>{});
  loadCycles().catch(()=>{});
})();