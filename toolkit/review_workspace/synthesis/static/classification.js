'use strict';
function classificationStatusLabel(status){return ({confirmed:'Classified',draft:'Draft',later:'Later',unreviewed:'Unclassified'})[status]||status||'Unclassified';}
let classReview=null,classDirty=false,classBusy=false,classTab=true;
function classChanged(){classDirty=true;$('#class-save-state').textContent='Unsaved classification';$('#class-domains-checked').checked=false;}
function classDecision(){
 const r=classReview.record,labels={};$$('[data-class-category]').forEach(e=>labels[e.dataset.classCategory]=e.value);
 const core=[],secondary=[];$$('[data-class-domain]').forEach(e=>{if(e.value==='core')core.push(e.dataset.classDomain);if(e.value==='secondary')secondary.push(e.dataset.classDomain);});
 return {review_scope:'categories_domains',labels,reason:$('#class-reason').value,question:'',reviewer:$('#reviewer').value.trim(),evidence_checked:true,
  domains:{primary:$('#class-primary').value,core,secondary,reviewed:$('#class-domains-checked').checked,note:$('#class-domain-note').value}};
}
function classPrimary(){const prior=$('#class-primary').value;$('#class-primary').innerHTML='<option value="">Select primary domain</option>'+$$('[data-class-domain]').filter(e=>e.value==='core').map(e=>`<option>${esc(e.dataset.classDomain)}</option>`).join('');$('#class-primary').value=prior;}
function classPassages(evidence){return evidence.map(e=>`<div class="class-quote"><blockquote>${esc(e.quote.replace(/\s+/g,' '))}</blockquote><a href="${pdfLink(e.page)}" target="_blank" rel="noopener">PDF p. ${e.page}</a><p class="small">${esc((e.cautions||[]).join('; ')||e.reason||'Rule match; check in context.')}</p></div>`).join('');}
function renderClassification(){
 $('#classification-panel').hidden=!classTab;$('#extraction-workspace').hidden=classTab;
 $('#save').hidden=classTab;$('#later').hidden=classTab;$('#confirm').hidden=classTab;
 if(!classReview)return;
 if(window.reviewSnapshot){
  const {record:r,categories,domains}=classReview;const d=r.review.payload;
  $('#class-category-fields').innerHTML=categories.map(name=>`<article class="class-card"><label>${esc(name)}<select disabled><option>${d.labels[name]==='yes'?'Yes':'Not labelled in export'}</option></select></label></article>`).join('');
  $('#class-domain-fields').innerHTML=domains.filter(name=>d.domains.core.includes(name)).map(name=>`<div class="class-domain-row"><label>${esc(name)}<select disabled><option>Core</option></select></label></div>`).join('');
  $('#class-save-state').textContent=r.author_verified==='true'?'Author verified · '+r.verification_reviewer:'Labels in the CSV export';return;
 }
 const {record:r,categories,domains}=classReview;const d=r.review?.payload;const labels=d?.labels||Object.fromEntries(categories.map(k=>[k,'uncertain']));
 const domain=d?.domains||r.domain_assignment;
 $('#class-category-fields').innerHTML=categories.map(name=>{
  const p=r.proposal?.assessments?.[name];const evidence=(r.proposal?.evidence||[]).filter(e=>e.candidate_categories?.includes(name));
  return `<article class="class-card"><label>${esc(name)}<select data-class-category="${esc(name)}">${[['uncertain','?'],['yes','Yes'],['no','No']].map(([v,t])=>`<option value="${v}" ${labels[name]===v?'selected':''}>${t}</option>`).join('')}</select></label><p class="small">Python rules: ${p?.suggestion==='yes'?'Yes':'unresolved'} · ${esc(p?.reason||'Assess manually.')}</p><details><summary>Supporting passages (${evidence.length})</summary>${classPassages(evidence)}</details></article>`;
 }).join('');
 $('#class-domain-fields').innerHTML=domains.map(name=>{const p=r.domain_proposals?.[name];const role=domain.core.includes(name)?'core':domain.secondary.includes(name)?'secondary':'';return `<div class="class-domain-row"><label>${esc(name)}<select data-class-domain="${esc(name)}">${[['','Not assigned'],['core','Core'],['secondary','Secondary / side topic']].map(([v,t])=>`<option value="${v}" ${v===role?'selected':''}>${t}</option>`).join('')}</select></label><details><summary>${p?.suggestion==='yes'?'Python rule suggestion — see evidence':'No sufficient match / manual review'}</summary><p class="small">${esc(p?.reason||'No suggestion prepared.')}</p>${classPassages(p?.evidence||[])}</details></div>`;}).join('');
 classPrimary();$('#class-primary').value=domain.primary;$('#class-domains-checked').checked=domain.reviewed;$('#class-domain-note').value=domain.note||'';$('#class-reason').value=d?.reason||'';
 $('#class-save-state').textContent=r.review?`${classificationStatusLabel(r.review_status)} · revision ${r.review.revision}`:'No classification saved';
 $$('[data-class-category]').forEach(e=>e.onchange=classChanged);
 $$('[data-class-domain]').forEach(e=>e.onchange=()=>{classChanged();classPrimary();});
 $('#class-primary').onchange=classChanged;$('#class-domain-note').oninput=classChanged;$('#class-reason').oninput=classChanged;
 $('#class-domains-checked').onchange=()=>{classDirty=true;$('#class-save-state').textContent='Unsaved classification';};
}
async function saveClassification(action='draft'){
 if(!current||!classReview||classBusy)return;
 classBusy=true;
 try{
  const r=classReview.record,decision=classDecision();
  const saved=await api('/api/classify',{record_id:r.record_id,proposal_hash:r.proposal_hash,revision:r.review?.revision||0,action,decision});
  r.review=saved;r.review_status=saved.status;r.domain_assignment=saved.payload.domains;classDirty=false;
  const updated=await api('/api/meta');meta.records=updated.records;current.record={...current.record,...meta.records.find(x=>x.record_id===r.record_id)};
  renderClassification();renderReading();browse();$('#paper-status').textContent=`Extraction: ${synthesisStatusLabel(current.review.status)} · Classification: ${classificationStatusLabel(saved.status)}`;error('');
 }catch(e){error(e.message);throw e;}finally{classBusy=false;}
}
async function flushClassification(){if(classBusy)throw Error('Classification is still saving. Please wait.');if(classDirty)await saveClassification('draft');}
document.addEventListener('DOMContentLoaded',()=>{
 $('#class-save').onclick=()=>saveClassification('draft').catch(()=>{});
 $('#class-confirm').onclick=()=>saveClassification('confirm').catch(()=>{});
});
