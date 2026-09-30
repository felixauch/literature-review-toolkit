'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone=o=>JSON.parse(JSON.stringify(o));
const snapshotMode=Boolean(window.reviewSnapshot);let shortcutsBound=false;
const labels={unchecked:'Unchecked',recorded:'Recorded',not_reported:'Not reported',not_applicable:'Not applicable',unclear:'Unclear'};
let meta,current=null,group='',activeField='',dirty=false,generation=0,timer=null,savePromise=null,navBusy=false,pendingNavigation=undefined;
let searchResults=null,evidenceLimit=3,overview=null,domainNote=null,domainDirty=false,domainTimer=null,domainPromise=null,domainGeneration=0;
function error(message){$('#error').textContent=message;$('#error').hidden=!message;}
async function api(path,body){
 if(snapshotMode)return window.reviewSnapshot.api(path,body);
 const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':meta.token},body:JSON.stringify(body)}:{});
 const data=await r.json();if(!r.ok)throw Error(data.error||'The local server did not save the request.');return data;
}
function domains(r){return r.report_core_domains.split(';').map(x=>x.trim()).filter(Boolean);}
function categories(r){return r.report_categories.split(';').map(x=>x.trim()).filter(Boolean);}
function queue(){const q=$('#queue').value,query=$('#find').value.toLowerCase(),d=$('#domain-filter').value;return meta.records.filter(r=>
 (q==='reading_pending'&&readingPending(r)||q==='reading_selected'&&r.reading_status==='detailed_needed'&&r.status!=='confirmed'||q==='brief_done'&&r.reading_status==='brief_done'||q==='all'||(q==='classification_pending'&&(r.classification_status!=='confirmed'||!r.domains_reviewed))||(q==='pending'&&!['confirmed','assessed'].includes(r.status))||(q==='assessed'&&['confirmed','assessed'].includes(r.status))||r.status===q)&&(!$('#reading-filter').value||r.reading_group===$('#reading-filter').value)&&(!d||domains(r).includes(d))&&(!query||[r.record_id,r.title,r.authors].join(' ').toLowerCase().includes(query))).sort((a,b)=>(a.reading_priority??999)-(b.reading_priority??999)||a.record_id.localeCompare(b.record_id));}
function progress(){if(snapshotMode){$('#progress').textContent=meta.records.length+' papers · Read-only CSV';return;}const n=meta.records.filter(r=>['confirmed','assessed'].includes(r.status)).length;$('#progress').textContent=`Classification: ${meta.records.filter(r=>r.classification_status==='confirmed'&&r.domains_reviewed).length}/${meta.records.length} · Extraction: ${n}/${meta.records.length}${meta.reading_plan?.groups?.length?' · Brief: '+meta.records.filter(r=>r.reading_status==='brief_done').length:''}`;}
function browse(){const rows=queue();$('#queue-count').textContent=`${rows.length} papers · browse`;$('#paper-list').innerHTML=rows.map(r=>`<button data-id="${esc(r.record_id)}">${esc(r.record_id)} · ${esc(r.title)}<small>${esc(synthesisStatusLabel(r.status))}</small></button>`).join('');$$('#paper-list button').forEach(b=>b.onclick=()=>go(b.dataset.id));progress();}
function setSave(text){$('#save-state').textContent=text;}
function changed(){if(snapshotMode)return;dirty=true;generation++;current.review.payload.verified=false;setSave('Unsaved changes');clearTimeout(timer);timer=setTimeout(()=>persist('draft').catch(e=>error(e.message)),1100);renderSteps();}
function renderSteps(){if(!current)return;$('#steps').innerHTML=`<button id="extraction-tab" class="${classTab?'':'active'}">Evidence & synthesis</button><button id="classification-tab" class="${classTab?'active':''}">Categories & domains</button><button id="toggle-source" class="source-toggle">Source search</button>`;
 $('#classification-tab').onclick=async()=>{await flushReading();await flush();classTab=true;renderClassification();renderSteps();};
 $('#extraction-tab').onclick=async()=>{await flushClassification();classTab=false;renderClassification();renderSteps();renderFields();renderEvidence();};
 $('#toggle-source').onclick=()=>{const pane=$('.evidence-pane');pane.hidden=!pane.hidden;if(!pane.hidden){renderEvidence();$('#source-search').focus();}};
}

function pdfLink(page=1){return `/pdf/${encodeURIComponent(current.record.record_id)}#page=${page}`;}
function renderFields(){
 $('#fields').style.setProperty('--measure-groups',Math.min(4,Math.max(1,meta.groups.length)));
 const sourcePages=[...new Set(meta.fields.flatMap(f=>(current.review.payload.fields[f.id]?.pages||'').split(',').map(v=>v.trim()).filter(v=>/^\d+$/.test(v))))].sort((a,b)=>Number(a)-Number(b));
 const sourceLinks=sourcePages.length?`<div class="source-links">Source pages: ${sourcePages.map(n=>`<a href="${pdfLink(Number(n))}" target="_blank" rel="noopener">${esc(n)}</a>`).join(' · ')}</div>`:'';
 $('#fields').innerHTML=sourceLinks+meta.groups.map(g=>`<section class="measure-group"><h2>${esc(g)}</h2>`+meta.fields.filter(f=>f.group===g).map(f=>{
  const v=current.review.payload.fields[f.id];
  return `<article class="field ${f.author?'author':''} ${f.id===activeField?'focus':''}" data-field="${f.id}"><div class="field-top"><label for="value-${f.id}">${esc(f.title)}${f.required?' <span class="required">*</span>':''}</label><select aria-label="${esc(f.title)} status" data-state="${f.id}">${Object.entries(labels).map(([k,n])=>`<option value="${k}" ${v.state===k?'selected':''}>${n}</option>`).join('')}</select></div><p class="hint">${esc(f.hint)}</p>${f.type&&f.type!=='text'?choiceControl(f,v.choices||[],`field-${f.id}`):`<textarea id="value-${f.id}" data-value="${f.id}" rows="3" placeholder="${f.author?'Your interpretation or proposal…':'Your concise summary, exact result or explanation…'}">${esc(v.value)}</textarea>`}<div class="field-bottom"><label>Source pages <input data-pages="${f.id}" aria-label="${esc(f.title)} source pages" value="${esc(v.pages)}" placeholder="e.g. 4, Table 2"></label><div class="evidence-chips">${v.evidence.map(e=>`<span class="evidence-chip"><a href="${pdfLink(e.page)}" target="_blank" rel="noopener">PDF p. ${e.page}</a><button data-remove="${f.id}" data-evidence="${esc(e.id)}" aria-label="Remove attached passage">×</button></span>`).join('')}</div></div></article>`;
 }).join('')+'</section>').join('');
 $$('#fields [data-field]').forEach(a=>a.addEventListener('focusin',()=>focusField(a.dataset.field)));
 $$('#fields [data-value]').forEach(a=>a.oninput=()=>{const v=current.review.payload.fields[a.dataset.value];v.value=a.value;if(v.state==='unchecked'&&a.value.trim()){v.state='recorded';$(`[data-state="${a.dataset.value}"]`).value='recorded';}changed();});
 bindChoices('#fields',(key,values)=>{const v=current.review.payload.fields[key];v.choices=values;v.value=values.join('; ');v.state=values.length?'recorded':'unchecked';$(`[data-state="${key}"]`).value=v.state;focusField(key);changed();});
 $$('#fields [data-state]').forEach(a=>a.onchange=()=>{const v=current.review.payload.fields[a.dataset.state];v.state=a.value;if(v.state!=='recorded'&&v.choices){v.choices=[];v.value='';renderFields();}focusField(a.dataset.state);changed();});
 $$('#fields [data-pages]').forEach(a=>a.oninput=()=>{current.review.payload.fields[a.dataset.pages].pages=a.value;changed();});
 $$('#fields [data-remove]').forEach(b=>b.onclick=()=>{const v=current.review.payload.fields[b.dataset.remove];v.evidence=v.evidence.filter(e=>e.id!==b.dataset.evidence);changed();renderFields();renderEvidence();});
}
function focusField(key){if(activeField===key)return;activeField=key;searchResults=null;evidenceLimit=3;$$('[data-field]').forEach(x=>x.classList.toggle('focus',x.dataset.field===key));renderEvidence();}
function renderEvidence(){
 const field=meta.fields.find(f=>f.id===activeField);$('#evidence-title').textContent=field.title;
 const list=searchResults?searchResults.map(e=>({e,terms:[],cautions:[]})):[];
 $('#clear-search').hidden=!searchResults;$('#evidence-count').textContent=field.author&&!searchResults?'Your interpretation belongs in the form. Search the source to attach a passage if useful.':`${list.length} ${searchResults?'search matches':'candidate passages'} · showing ${Math.min(list.length,evidenceLimit)}`;
 $('#passages').innerHTML=list.slice(0,evidenceLimit).map(({e,terms,cautions})=>{
  const attached=current.review.payload.fields[activeField].evidence.some(x=>x.id===e.id);
  return `<article class="passage"><div class="passage-head"><a href="${pdfLink(e.page)}" target="_blank" rel="noopener">PDF p. ${e.page} ↗</a><span>${esc(e.section)}</span><span>${attached?'Attached':''}</span></div><blockquote>${esc(e.quote.replace(/\s+/g,' ').trim())}</blockquote>${cautions.length?`<p class="caution">${esc(cautions.join(' · '))}</p>`:''}<div class="passage-actions"><button data-attach="${esc(e.id)}" ${attached?'disabled':''}>${attached?'Attached':'Attach to this field'}</button>${field.type&&field.type!=='text'?'':`<button data-use="${esc(e.id)}">Insert quotation</button>`}</div><details><summary>Matched terms / original extraction</summary><p class="terms">${esc(terms.join(', ')||'Literal search match')}</p><div class="raw">${esc(e.quote)}</div></details></article>`;
 }).join('') || `<p class="hint">${field.author?'Choose your interpretation in the form.':'Search the extracted text or read the PDF. Automatic keyword ranking has been removed.'}</p>`;
 function attach(id,insert){const e=list.find(x=>x.e.id===id).e;const f=current.review.payload.fields[activeField];if(!f.evidence.some(x=>x.id===id))f.evidence.push(clone(e));if(insert){f.value+=(f.value?'\n\n':'')+'“'+e.quote.replace(/\s+/g,' ').trim()+'” (PDF p. '+e.page+')';f.state='recorded';}changed();renderFields();renderEvidence();}
 $$('#passages [data-attach]').forEach(b=>b.onclick=()=>attach(b.dataset.attach,false));$$('#passages [data-use]').forEach(b=>b.onclick=()=>attach(b.dataset.use,true));
 $('#more').hidden=list.length<=evidenceLimit;
}
function renderPaper(){
 renderReading();
 renderPaperSections();renderLegacy();
 const r=current.record;$('#paper-id').textContent=`${r.record_id} · ${r.year}`;$('#paper-status').textContent=`Extraction: ${synthesisStatusLabel(current.review.status)} · Classification: ${classificationStatusLabel(r.classification_status)}${r.author_verified==='true'?' · Author verified':''}`;$('#paper-title').textContent=r.title;$('#paper-author').textContent=r.authors;let revisionNote=$('#revision-note');if(!revisionNote){revisionNote=document.createElement('p');revisionNote.id='revision-note';revisionNote.className='small';$('#paper-author').after(revisionNote);}revisionNote.textContent=r.reading_note||'';revisionNote.hidden=!r.reading_note;
 $('#paper-tags').innerHTML=categories(r).map(c=>`<span class="tag">${esc(c)}</span>`).join('')+domains(r).map(d=>`<span class="tag domain">${esc(d)}</span>`).join('')+(r.decision_link?`<span class="tag">${esc(r.output_label || r.decision_link)} output</span>`:'');
 let rememberedReviewer='';if(!snapshotMode){try{rememberedReviewer=localStorage.getItem('synthesis-reviewer')||'';}catch(e){}}
 $('#reviewer').value=current.review.payload.reviewer||rememberedReviewer;if(!snapshotMode)current.review.payload.reviewer=$('#reviewer').value;
 setSave(current.review.updated_at?`Saved · ${synthesisStatusLabel(current.review.status)}`:'Not yet reviewed');renderSteps();renderFields();renderEvidence();renderClassification();
}
async function persist(status='draft',force=false){
 if(snapshotMode)return;
 clearTimeout(timer);if(savePromise)await savePromise;if(!current||(!dirty&&!force))return;
 const selected=current,id=selected.record.record_id,gen=generation;
 const payload=clone(selected.review.payload);payload.reviewer=$('#reviewer').value.trim();payload.verified=status==='confirmed'; // Confirm & next is the explicit review acknowledgement.
 setSave('Saving…');
 savePromise=api('/api/save',{id,revision:selected.review.revision,status,payload});
 try{const saved=await savePromise;selected.review.revision=saved.revision;selected.review.status=saved.status;selected.review.updated_at=saved.updated_at;
  const index=meta.records.find(r=>r.record_id===id);index.status=saved.status;index.revision=saved.revision;index.updated_at=saved.updated_at;
  if(current===selected&&generation===gen){selected.review.payload=saved.payload;dirty=false;setSave(`Saved · ${synthesisStatusLabel(saved.status)}`);$('#paper-status').textContent=`Extraction: ${synthesisStatusLabel(saved.status)} · Classification: ${classificationStatusLabel(current.record.classification_status)}`;}
  else if(current===selected){setSave('New changes awaiting save');clearTimeout(timer);timer=setTimeout(()=>persist().catch(e=>error(e.message)),700);}
  browse();error('');return saved;
 }catch(e){setSave('Save failed — changes kept on screen');error(e.message);throw e;}finally{savePromise=null;}
}
async function flush(){if(savePromise)await savePromise;if(dirty){await persist();if(dirty)await flush();}}
async function go(id){if(navBusy){pendingNavigation=id;return;}navBusy=true;$('#paper').inert=true;try{
 await flushReading();await flushClassification();await flush();if(!id){$('#empty').hidden=false;$('#paper').hidden=true;$('#review-footer').hidden=true;current=null;return;}
 const [data,classification]=await Promise.all([api('/api/record/'+encodeURIComponent(id)),api('/api/classification/'+encodeURIComponent(id))]);classReview=classification;classDirty=false;current=data;current.record={...data.record,...meta.records.find(r=>r.record_id===id)};readingDirty=false;dirty=false;generation=0;searchResults=null;evidenceLimit=3;$('#source-search').value='';$('#browse').open=false;
 if(!meta.fields.some(f=>f.id===activeField&&f.group===group))activeField=meta.fields.find(f=>f.group===group).id;
 $('#empty').hidden=true;$('#paper').hidden=false;$('#review-footer').hidden=false;renderPaper();browse();error('');window.scrollTo({top:0,behavior:'instant'});
 }catch(e){error(e.message);}finally{navBusy=false;$('#paper').inert=false;if(pendingNavigation!==undefined){const nextId=pendingNavigation;pendingNavigation=undefined;await go(nextId);}}}
async function step(delta){const rows=queue(),i=rows.findIndex(r=>r.record_id===current?.record.record_id);if(rows.length)await go(rows[(i+delta+rows.length)%rows.length].record_id);}
async function finish(status){if(!current)return;const id=current.record.record_id,rows=queue(),i=rows.findIndex(r=>r.record_id===id),next=rows.slice(i+1).concat(rows.slice(0,i)).find(r=>r.record_id!==id)?.record_id;
 $('#paper').inert=true;$('#confirm').disabled=true;$('#later').disabled=true;
 try{await persist(status,true);if(dirty)await flush();await go(next||queue().find(r=>r.record_id!==id)?.record_id||null);}catch(e){error(e.message);}finally{$('#paper').inert=false;$('#confirm').disabled=false;$('#later').disabled=false;}}
async function setMode(mode){try{await flushReading();await flushClassification();await flush();if(domainDirty)await saveDomain();$('#review-view').hidden=mode!=='review';$('#synthesis-view').hidden=mode!=='synthesis';$('#review-mode').classList.toggle('active',mode==='review');$('#synthesis-mode').classList.toggle('active',mode==='synthesis');if(mode==='synthesis'){overview=await api('/api/overview');renderOverview();await loadDomain();}}catch(e){error(e.message);}}
function cell(field){if(!field)return '';return `<div>${esc(field.value)}</div>${field.state!=='recorded'?`<span class="cell-state">${esc(labels[field.state])}</span>`:''}${field.evidence.length||field.pages?`<small>Pages: ${esc(field.pages||[...new Set(field.evidence.map(e=>e.page))].join(', '))}</small>`:''}`;}
function synthesisStatusLabel(status){return ({confirmed:'Assessed',assessed:'Assessed',draft:'Draft',later:'Later',unreviewed:'Unreviewed',brief_done:'Overview only'})[status]||status;}
function renderOverview(){
 const status=$('#overview-state').value,d=$('#overview-domain').value,c=$('#overview-category').value;
 const all=uniqueSynthesisRows(overview.records.filter(r=>r.eligibility!=='exclude'&&(!d||domains(r).includes(d))&&(!c||categories(r).includes(c))));
 const rows=all.filter(r=>r.reading_depth!=='brief'&&(status==='confirmed'?r.status==='confirmed':status==='assessed'?['assessed','confirmed'].includes(r.status):r.status!=='unreviewed'));
 const completed=rows.filter(r=>['confirmed','assessed'].includes(r.status)).length;
 renderSynthesisMap(rows,all);
 const detailRows=filterSynthesisRows(rows,synthesisFocus,meta.fields);
 const columns=meta.fields.filter(f=>!$('#overview-group').value||f.group===$('#overview-group').value);
 $('#overview-summary').innerHTML=`<div><span>Papers in this view</span><b>${rows.length}</b><small>of ${all.length} papers matching the filters</small></div><div><span>Assessed</span><b>${completed}</b><small>Completed assessments in this view</small></div><div><span>Drafts / later</span><b>${rows.length-completed}</b><small>Saved entries awaiting completion</small></div>`;
 $('#paper-detail-count').textContent=`${detailRows.length} ${detailRows.length===1?'paper':'papers'}`;
 $('#paper-detail-filter').textContent=synthesisFocusTitle(synthesisFocus,meta.fields);
 $('#clear-map-focus').hidden=!synthesisFocus;$('#clear-map-focus').onclick=resetSynthesisFocus;
 $('#overview-head').innerHTML='<tr><th>Paper</th>'+columns.map(f=>`<th>${esc(f.title)}</th>`).join('')+'</tr>';
 $('#overview-body').innerHTML=detailRows.map(r=>`<tr><td><button class="paper-link" data-paper="${esc(r.record_id)}">${esc(r.record_id)} · ${esc(r.title)}</button><small>${esc(r.report_categories)} · <span class="review-badge ${['confirmed','assessed'].includes(r.status)?'review-confirmed':'review-draft'}">${esc(synthesisStatusLabel(r.status))}</span></small></td>${columns.map(({id:k})=>`<td>${cell(r.review.payload.fields[k])}</td>`).join('')}</tr>`).join('')||'<tr><td colspan="99">No papers in this selection. Clear the selection or change the filters.</td></tr>';
 $$('#overview-body [data-paper]').forEach(b=>b.onclick=async()=>{await setMode('review');await go(b.dataset.paper);});
}
async function loadDomain(){if(snapshotMode){$('#domain-notes').hidden=true;return;}if(domainDirty)await saveDomain();const d=$('#overview-domain').value;$('#domain-notes').hidden=!d;domainNote=null;if(!d)return;domainNote=await api('/api/domain?id='+encodeURIComponent(d));$('#domain-title').textContent=d;for(const f of meta.domain_fields){const el=$('#domain-'+f.id),v=domainNote.payload[f.id];if(f.type&&f.type!=='text'){for(const o of el.options)o.selected=Array.isArray(v)&&v.includes(o.value);}else el.value=v;}$('#domain-save-state').textContent=domainNote.updated_at?'Saved':'Not yet saved';domainDirty=false;}
async function saveDomain(){clearTimeout(domainTimer);if(domainPromise)await domainPromise;if(!domainNote||!domainDirty)return;const payload={},selected=domainNote,gen=domainGeneration;for(const f of meta.domain_fields){const el=$('#domain-'+f.id);payload[f.id]=f.type&&f.type!=='text'?[...el.selectedOptions].map(o=>o.value).filter(Boolean):el.value;}domainPromise=api('/api/domain',{id:selected.id,revision:selected.revision,payload});try{const saved=await domainPromise;selected.revision=saved.revision;if(domainNote===selected&&domainGeneration===gen){domainNote=saved;domainDirty=false;$('#domain-save-state').textContent='Saved';error('');}else if(domainNote===selected){$('#domain-save-state').textContent='New changes awaiting save';}}finally{domainPromise=null;}if(domainDirty)await saveDomain();}
async function init(){
 meta=await api('/api/meta');if(meta.version!=='unified-review-2026-09-30-v18-csv')throw Error('This server is running older code. Save any open edits and use the updated interface.');initReading();group=meta.groups[0];activeField=meta.fields[0].id;
 $('#overview-category').innerHTML='<option value="">All categories</option>';$('#overview-category').insertAdjacentHTML('beforeend',[...new Set(meta.records.flatMap(categories))].map(c=>`<option>${esc(c)}</option>`).join(''));
 $('#domain-note-fields').innerHTML=meta.domain_fields.map(f=>`<label>${esc(f.title)}${f.type&&f.type!=='text'?`<select id="domain-${esc(f.id)}" ${f.type==='multi'?'multiple size="5"':''}>${f.type==='single'?'<option value="">Choose…</option>':''}${f.options.map(o=>`<option>${esc(o)}</option>`).join('')}</select>`:`<textarea id="domain-${esc(f.id)}" rows="4"></textarea>`}</label>`).join('');
 $('#overview-group').innerHTML='<option value="">All measures</option>'+meta.groups.map(g=>`<option>${esc(g)}</option>`).join('');$('#overview-group').onchange=renderOverview;
 document.title=(snapshotMode?'Corpus explorer':'Literature review toolkit')+' — '+meta.project.name;for(const sel of ['#domain-filter','#overview-domain'])$(sel).innerHTML='<option value="">All domains</option>'+meta.domains.map(d=>`<option>${esc(d)}</option>`).join('');
 $$('a[download]').forEach(a=>a.onclick=async e=>{e.preventDefault();try{await flushReading();await flushClassification();await flush();if(domainDirty)await saveDomain();window.location.assign(a.href);}catch(e){error(e.message);}});
 $('#review-mode').onclick=()=>setMode('review');$('#synthesis-mode').onclick=()=>setMode('synthesis');
 $('#find').oninput=browse;$('#domain-filter').onchange=async()=>{browse();await go(queue()[0]?.record_id);};$('#queue').onchange=async()=>{browse();await go(queue()[0]?.record_id);};
 $('#prev').onclick=()=>step(-1);$('#next').onclick=()=>step(1);$('#save').onclick=()=>persist('draft',true).catch(e=>error(e.message));$('#later').onclick=()=>finish('later');$('#confirm').onclick=()=>finish('confirmed');
 $('#reviewer').oninput=()=>{if(current){current.review.payload.reviewer=$('#reviewer').value;try{localStorage.setItem('synthesis-reviewer',$('#reviewer').value);}catch(e){}changed();}};
 $('#open-pdf').onclick=()=>{if(current)window.open(pdfLink(),'source-'+current.record.record_id,'popup,width=1080,height=900,noopener');};
 $('#close-source').onclick=()=>{$('.evidence-pane').hidden=true;};
 $('#more').onclick=()=>{evidenceLimit+=5;renderEvidence();};
 $('#search-form').onsubmit=async e=>{e.preventDefault();if(!current)return;try{const id=current.record.record_id;const found=await api('/api/search/'+id+'?q='+encodeURIComponent($('#source-search').value));if(current.record.record_id!==id)return;searchResults=found.results;evidenceLimit=5;renderEvidence();}catch(e){error(e.message);}};
 $('#clear-search').onclick=()=>{searchResults=null;$('#source-search').value='';evidenceLimit=3;renderEvidence();};
 $('#overview-state').onchange=renderOverview;$('#overview-category').onchange=renderOverview;$('#overview-domain').onchange=async()=>{try{await loadDomain();renderOverview();}catch(e){error(e.message);}};
 for(const k of meta.domain_fields.map(f=>f.id))$('#domain-'+k).oninput=()=>{domainDirty=true;domainGeneration++;$('#domain-save-state').textContent='Unsaved';clearTimeout(domainTimer);domainTimer=setTimeout(()=>saveDomain().catch(e=>error(e.message)),1400);};
 $('#save-domain').onclick=()=>saveDomain().catch(e=>error(e.message));
 if(!shortcutsBound)document.addEventListener('keydown',e=>{
  if(snapshotMode)return;
  if(e.isComposing||e.repeat)return;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){
   e.preventDefault();flushReading().catch(e=>error(e.message));
   if(!$('#synthesis-view').hidden)saveDomain().catch(e=>error(e.message));
   else if(classTab)saveClassification('draft').catch(e=>error(e.message));
   else persist('draft',true).catch(e=>error(e.message));
  }
  if(e.key!=='Enter'||$('#review-view').hidden||!current)return;
  const inControl=e.target instanceof Element&&e.target.closest('input,textarea,select,button,a,summary,[contenteditable]:not([contenteditable="false"]),[role="button"],[role="textbox"],[role="combobox"]');
  const modified=(e.ctrlKey||e.metaKey)&&!e.altKey;
  const plain=!e.ctrlKey&&!e.metaKey&&!e.altKey&&!e.shiftKey&&!inControl&&!classTab;
  if(modified||plain){
   e.preventDefault();
   const button=$(classTab?'#class-confirm':'#confirm');
   if(!button.disabled&&!button.hidden&&!navBusy&&!classBusy)button.click();
  }
 });
 shortcutsBound=true;
 window.addEventListener('beforeunload',e=>{if(readingDirty||readingPromise||classDirty||classBusy||dirty||savePromise||domainDirty||domainPromise){e.preventDefault();e.returnValue='';}});
 if(snapshotMode){classTab=false;$('#queue').value='all';setupSnapshot();}
 const rawQueue=new URLSearchParams(location.search).get('queue');
 const requestedQueue=rawQueue==='confirmed'?'assessed':rawQueue;
 if(requestedQueue&&[...$('#queue').options].some(o=>o.value===requestedQueue))$('#queue').value=requestedQueue;
 browse();await go(queue()[0]?.record_id);
 if(new URLSearchParams(location.search).get('view')==='synthesis')await setMode('synthesis');
}
init().catch(e=>error(e.message));

function renderPaperSections(){
 const data=current.paper_sections;
 const items=Object.values(data?.sections||{});
 $('#section-excerpts').innerHTML=items.length?items.map(section=>`<article class="section-excerpt"><h3>${esc(section.title)} <span class="small">${esc(section.status.replaceAll('_',' '))}${section.combined?' · combined section':''}</span></h3><p class="small">${esc(section.note)}</p>${section.spans.map(e=>`<div><a href="${pdfLink(e.page)}" target="_blank" rel="noopener">PDF p. ${e.page} ↗</a><p class="section-text">${esc(e.quote.replace(/\s+/g,' '))}</p><details><summary>Original extracted text</summary><pre>${esc(e.quote)}</pre></details></div>`).join('')}</article>`).join(''):`<p class="small">${esc(data?.warning||'Section extraction has not been prepared for this paper.')}</p>`;
}

function setupSnapshot(){
 document.body.classList.add('snapshot');
 $('.brand').textContent='Corpus explorer';
 if(!$('#snapshot-banner')){
  const banner=document.createElement('div');banner.id='snapshot-banner';banner.className='snapshot-banner';
  banner.innerHTML='<span id="snapshot-name"></span><label>Load CSV <input id="snapshot-file" type="file" accept=".csv,text/csv"></label>';
  $('.appbar').after(banner);$('.brand').href='#';$('.brand').onclick=e=>{e.preventDefault();setMode('review');};
  $('#snapshot-file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;window.reviewSnapshot.load(await file.text(),file.name);current=null;classReview=null;overview=null;synthesisFocus=null;$('#overview-state').value='assessed';await init();await setMode('review');error('');}catch(e){error(e.message);}};
  const lock=()=>{$$('#fields input,#fields select,#fields textarea,#classification-panel input,#classification-panel select,#classification-panel textarea').forEach(e=>e.disabled=true);$$('#fields a[href^="/pdf/"]').forEach(a=>{a.removeAttribute('href');a.removeAttribute('target');});};
  new MutationObserver(lock).observe($('#paper'),{childList:true,subtree:true});lock();
 }
 $('#snapshot-name').textContent=window.reviewSnapshot.name+' · Saved assessments only; source PDFs and extracts are not included.';
 const menu=$('.menu>div');menu.innerHTML='<a id="snapshot-download" download="assessments.csv">Download this CSV</a><p>Same paper views and synthesis maps as the review toolkit. This snapshot is read-only. Status and labels are retained from the export.</p><p>Developed with assistance from GPT-6 Astra.</p>';
 const a=$('#snapshot-download');a.href=URL.createObjectURL(new Blob([window.reviewSnapshot.csv],{type:'text/csv;charset=utf-8'}));
}
