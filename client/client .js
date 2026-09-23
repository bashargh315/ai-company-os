const API_BASE='';
const toolData=[
 ['🔎','باحث السوق','منافسون، أسعار، اتجاهات، فرص'],['📊','محلل الأعمال','أرقام وقرارات وتوقعات'],['💡','مولّد الأفكار','منتجات وحملات وفرص جديدة'],['✍️','صانع المحتوى','نصوص، صفحات، عروض، ترجمة'],['🎨','استوديو الصور','صور منتجات وإعلانات وهوية'],['🎬','استوديو الفيديو','إعلانات وفيديوهات احترافية'],['📣','التسويق','استراتيجية وتجارب وSEO'],['🤝','المبيعات','عملاء محتملون ومتابعات وفق القواعد'],['🎧','خدمة العملاء','ردود ذكية وتصعيد للحالات الحساسة'],['💰','المالية','إيرادات ومصروفات وتوقعات'],['🛡️','QA والأمان','تدقيق ومخاطر وصلاحيات'],['🧠','CEO Agent','يفهم الهدف ويوزع العمل ويراقب النتيجة']
];
const grid=document.querySelector('#tools');
if(grid) grid.innerHTML=toolData.map(x=>`<article class="tool"><b>${x[0]} ${x[1]}</b><small>${x[2]}</small></article>`).join('');
const form=document.querySelector('#chatForm'),input=document.querySelector('#message'),chat=document.querySelector('#chat');
let currentCompanyId=localStorage.getItem('aios_company_id')||null;
let config=null;
let booted=false;
function escapeHtml(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function addBubble(role,text){
 if(!chat)return;
 chat.insertAdjacentHTML('beforeend',`<div class="bubble ${role}">${role==='ai'?'<b>AI Company OS</b><br>':''}${escapeHtml(text).replace(/\n/g,'<br>')}</div>`);
 chat.scrollTop=chat.scrollHeight;
}
function clearBubbles(){chat?.querySelectorAll('.bubble').forEach(n=>n.remove());}
function useSuggestion(t){if(input){input.value=t;input.focus();}}
async function api(path,options={}){
 const headers={'Content-Type':'application/json',...(options.headers||{})};
 const du=localStorage.getItem('aios_demo_user');
 if(du) headers['X-Demo-User']=du;
 const r=await fetch(API_BASE+path,{...options,headers});
 if(!r.ok){let msg='طلب غير ناجح';try{msg=(await r.json()).detail||msg;}catch{}throw new Error(msg);}
 return r.json();
}
async function loadMessages(){
 if(!currentCompanyId||!chat)return;
 const data=await api('/api/companies/'+encodeURIComponent(currentCompanyId)+'/messages');
 clearBubbles();
 if(data.length) data.forEach(m=>addBubble(m.role==='user'?'user':'ai',m.content));
 else addBubble('ai','أهلاً بك 👋 احكيلي عن شركتك أو المشكلة التي تريد حلها، وسنبدأ بأقل عدد ممكن من الأسئلة.');
}
async function loadCompanies(){
 const companies=await api('/api/companies');
 if(companies[0]){currentCompanyId=companies[0].id;localStorage.setItem('aios_company_id',currentCompanyId);await loadMessages();}
}
async function loadSummary(){
 if(!currentCompanyId)return;
 try{
  const s=await api('/api/companies/'+encodeURIComponent(currentCompanyId)+'/summary');
  const panel=document.querySelector('#summaryPanel'); if(!panel)return;
  panel.innerHTML=`<article><span>${s.confidence}%</span><div><b>فهم النظام للشركة</b><p>مكتملة: ${s.stats.completed_tasks} — نشطة: ${s.stats.active_tasks} — موافقات: ${s.stats.pending_approvals}</p></div></article>`+
   (s.next_questions||[]).map((q,i)=>`<article><span>${i+1}</span><div><b>معلومة ناقصة</b><p>${escapeHtml(q)}</p></div></article>`).join('');
 }catch{}
}
async function showLatestResult(){
 if(!currentCompanyId)return;
 try{
  const r=await api('/api/companies/'+encodeURIComponent(currentCompanyId)+'/latest-result');
  const box=document.querySelector('#resultPanel'); if(!box)return;
  if(!r.result){box.innerHTML='<div class="empty">لم تُنشأ نتيجة بعد. فعّل الاشتراك المدفوع ثم شغّل أول مهمة.</div>';return;}
  const x=r.result;
  const steps=x.plan?.steps||[]; const posts=x.content?.posts||[];
  box.innerHTML=`<div class="result-card"><div class="result-top"><span class="eyebrow">آخر نتيجة</span><b>${escapeHtml(x.request||x.objective||'تجربة أولى')}</b></div><p>${escapeHtml(x.execution?.context||'تم إنشاء حزمة أولية للعمل.')}</p><div class="result-grid"><div><small>خطوات</small><strong>${steps.length}</strong></div><div><small>منشورات</small><strong>${posts.length}</strong></div><div><small>الوضع</small><strong>مدفوع</strong></div></div><div class="result-actions"><button class="primary" id="downloadLatest">تحميل النتيجة</button></div></div>`;
  document.querySelector('#downloadLatest')?.addEventListener('click',()=>window.open('/api/tasks/'+encodeURIComponent(r.task_id)+'/text','_blank'));
 }catch{}
}
async function boot(){
 if(booted)return; booted=true;
 try{
  config=await api('/api/config');
  const cs=document.querySelector('#connectionStatus');if(cs)cs.textContent='متصل';
  const st=document.querySelector('#appStatus');if(st)st.textContent=config.auth_mode==='supabase'?'المصادقة المتصلة جاهزة':'جاهز للبدء بعد تفعيل الاشتراك';
  await loadCompanies(); await loadSummary(); await showLatestResult();
 }catch(e){
  const cs=document.querySelector('#connectionStatus');if(cs)cs.textContent='تشغيل محلي';
 }
}
form?.addEventListener('submit',async e=>{
 e.preventDefault(); const t=input.value.trim(); if(!t)return;
 addBubble('user',t); input.value='';
 try{
  const r=await api('/api/chat',{method:'POST',body:JSON.stringify({message:t,company_id:currentCompanyId})});
  currentCompanyId=r.company_id;localStorage.setItem('aios_company_id',currentCompanyId);addBubble('ai',r.reply);await loadSummary();
 }catch(e){addBubble('ai','تعذر تنفيذ الطلب الآن. تأكد أن الخدمة تعمل ثم حاول مرة أخرى.');}
});
const accountBtn=document.querySelector('#accountBtn'),loginModal=document.querySelector('#loginModal');
accountBtn?.addEventListener('click',()=>{if(loginModal)loginModal.hidden=false;});
document.querySelector('#closeModal')?.addEventListener('click',()=>loginModal.hidden=true);
async function providerLogin(provider){
 if(!config||config.auth_mode!=='supabase'){
  document.querySelector('#loginHint').textContent='المصادقة الاجتماعية ليست مضبوطة بعد؛ استخدم الدخول التجريبي للاختبار الداخلي.';return;
 }
 try{const sb=supabase.createClient(config.supabase_url,config.supabase_publishable_key);await sb.auth.signInWithOAuth({provider:provider==='twitter'?'twitter':provider,options:{redirectTo:location.href}});}catch(e){document.querySelector('#loginHint').textContent='تعذر بدء تسجيل الدخول.';}
}
document.querySelectorAll('[data-provider]').forEach(b=>b.addEventListener('click',()=>providerLogin(b.dataset.provider)));
document.querySelector('#demoLogin')?.addEventListener('click',async()=>{localStorage.setItem('aios_demo_user','demo-user');loginModal.hidden=true;booted=false;await boot();});
document.querySelector('#discoverBtn')?.addEventListener('click',async()=>{
 if(!currentCompanyId){addBubble('ai','ابدأ أولاً بإنشاء مساحة الشركة ثم فعّل الاشتراك.');return;}
 try{const r=await api('/api/discover?company_id='+encodeURIComponent(currentCompanyId),{method:'POST'});r.ideas.forEach((x,i)=>addBubble('ai',`${i+1}. ${x.title}\n${x.description}`));await loadSummary();}catch{addBubble('ai','تعذر اكتشاف الفرص الآن.');}
});
async function makeReport(liveOnly=false){
 if(!currentCompanyId){addBubble('ai','ابدأ أولاً بإنشاء مساحة الشركة ثم فعّل الاشتراك.');return;}
 const q=input?.value.trim()||'حلل وضعي الحالي واقترح أول تجربة لزيادة النتائج';
 try{
  if(liveOnly){
   const r=await api('/api/research/live',{method:'POST',body:JSON.stringify({query:q,company_id:currentCompanyId,limit:5})});
   if(!r.connected){addBubble('ai','البحث الحي غير موصول بعد. لا توجد مصادر وهمية.');return;}
   addBubble('ai',`${r.answer||'تم العثور على مصادر:'}\n\n${(r.results||[]).map((x,i)=>`${i+1}. ${x.title}\n${x.url}`).join('\n')}`);return;
  }
  const r=await api('/api/research/report',{method:'POST',body:JSON.stringify({message:q,company_id:currentCompanyId})}); const x=r.report;
  let text=`${x.title}\n\n${x.executive_summary}\n\nفهم النظام: ${x.confidence}%\n\nالخطة:\n• ${x.execution_plan.join('\n• ')}\n\nالتوصيات:\n• ${x.recommendations.join('\n• ')}\n\nالمعلومات الناقصة: ${x.questions.length?x.questions.join('، '):'لا يوجد شيء أساسي حالياً.'}`;
  if(x.source_count)text+=`\n\nالمصادر الحية (${x.source_count}):\n${x.sources.map((s,i)=>`${i+1}. ${s.title}\n${s.url}`).join('\n')}`;
  addBubble('ai',text);await showLatestResult();
 }catch{addBubble('ai','تعذر إنشاء التقرير حالياً.');}
}
document.querySelector('#researchBtn')?.addEventListener('click',()=>makeReport(false));
document.querySelector('#liveResearchBtn')?.addEventListener('click',()=>makeReport(true));
async function launchFirst(){
 if(!currentCompanyId){addBubble('ai','ابدأ أولاً بإنشاء مساحة الشركة ثم فعّل الاشتراك.');return;}
 const q=input?.value.trim()||'أريد أول نتيجة قابلة للقياس بأقل تكلفة ممكنة';
 try{
  const r=await api('/api/execution/launch',{method:'POST',body:JSON.stringify({company_id:currentCompanyId,request:q,audience:'العملاء المحتملون'})}); const x=r.result;
  addBubble('ai',`تم تشغيل أول مهمة مدفوعة.\n\nالخطوات:\n${(x.plan?.steps||[]).slice(0,6).map((z,i)=>`${i+1}. ${z}`).join('\n')}\n\nتم إنشاء ${x.content?.posts?.length||0} منشورات أولية.\n\nلا يوجد إرسال خارجي تلقائي؛ أي تواصل يحتاج موافقة المدير.`);
  await loadSummary();await showLatestResult();
 }catch{addBubble('ai','تعذر تشغيل المهمة الآن. تأكد من تفعيل الاشتراك.');}
}
document.querySelector('#launchBtn')?.addEventListener('click',launchFirst);
document.querySelector('#summaryBtn')?.addEventListener('click',async()=>{await loadSummary();await showLatestResult();});
const pilotModal=document.querySelector('#pilotModal');
document.querySelector('#pilotBtn')?.addEventListener('click',()=>pilotModal.hidden=false);
document.querySelector('#closePilot')?.addEventListener('click',()=>pilotModal.hidden=true);
document.querySelector('#startPilot')?.addEventListener('click',async()=>{
 const name=document.querySelector('#pilotName').value.trim(),desc=document.querySelector('#pilotDesc').value.trim(),hint=document.querySelector('#pilotHint');
 if(!name){hint.textContent='اكتب اسم الشركة أو المشروع.';return;}
 try{
  const r=await api('/api/pilot/start',{method:'POST',body:JSON.stringify({company_name:name,description:desc,goal:'الحصول على أول نتيجة قابلة للقياس'})});
  currentCompanyId=r.company_id;localStorage.setItem('aios_company_id',currentCompanyId);pilotModal.hidden=true;clearBubbles();addBubble('ai','تم إنشاء مساحة الشركة. قبل تشغيل المهام، اختر الخطة المناسبة وأكمل الدفع.');await loadSummary();await showLatestResult();
 }catch{hint.textContent='تعذر إنشاء التجربة الآن.';}
});
boot();
window.useSuggestion=useSuggestion;

// v1.2 billing: provider-agnostic payment requests; no fake payment success.
async function loadBilling(){
  if(!currentCompanyId)return;
  try{
    const b=await api('/api/billing/status?company_id='+encodeURIComponent(currentCompanyId));
    const st=document.querySelector('#appStatus');
    if(st) st.textContent=b.active ? (b.plan==='owner' ? 'وصول المدير الداخلي' : `اشتراك ${b.subscription?.plan||''} فعّال`) : 'الاشتراك غير مفعّل';
    ['launchBtn','discoverBtn','researchBtn','liveResearchBtn'].forEach(id=>{const el=document.getElementById(id);if(el)el.disabled=!b.active;});
  }catch{}
}
async function showPlans(){
  const modal=document.querySelector('#billingModal'); if(!modal)return; modal.hidden=false;
  const box=document.querySelector('#plans'); if(!box)return;
  try{
    const data=await api('/api/billing/plans');
    box.innerHTML=data.plans.map(([id,p])=>`<article class="idea"><span>$${p.amount_usd}</span><div><b>${p.name}</b><p>${p.label}</p><button class="primary choosePlan" data-plan="${id}">طلب الدفع — ${p.name}</button></div></article>`).join('');
    box.querySelectorAll('.choosePlan').forEach(btn=>btn.addEventListener('click',async()=>{
      const hint=document.querySelector('#billingHint');
      if(!currentCompanyId){if(hint)hint.textContent='أنشئ مساحة شركتك أولاً.';return;}
      try{
        const r=await api('/api/billing/checkout',{method:'POST',body:JSON.stringify({company_id:currentCompanyId,plan:btn.dataset.plan})});
        if(r.checkout_url){ window.open(r.checkout_url,'_blank','noopener'); if(hint)hint.textContent='تم إنشاء طلب الدفع وفتح رابط الدفع.'; }
        else if(hint) hint.textContent=`تم إنشاء طلب الدفع ${r.payment_id}. لا توجد بوابة مربوطة حالياً؛ المدير يؤكد الدفع بعد استلامه.`;
      }catch{if(hint)hint.textContent='تعذر إنشاء طلب الدفع.';}
    }));
  }catch{box.innerHTML='<div class="empty">تعذر تحميل الخطط.</div>';}
}
document.querySelector('#closeBilling')?.addEventListener('click',()=>document.querySelector('#billingModal').hidden=true);
document.querySelector('#billingBtn')?.addEventListener('click',showPlans);
if(!document.querySelector('#billingBtn')){const b=document.createElement('button');b.className='ghost';b.id='billingBtn';b.textContent='الأسعار والاشتراك';b.onclick=showPlans;document.querySelector('.topbar div:last-child')?.prepend(b);}
const _oldBoot=boot; boot=async function(){await _oldBoot();await loadBilling();};