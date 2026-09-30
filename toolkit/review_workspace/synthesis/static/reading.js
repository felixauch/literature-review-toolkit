'use strict';
let readingDirty=false,readingPromise=null,readingTimer=null,readingGeneration=0;
const readingNames={unreviewed:'Not yet checked',draft:'Brief-check draft',brief_done:'Brief check complete',detailed_needed:'Selected for detailed extraction',later:'Decide later',needs_recheck:'Labels changed — recheck reading choice'};
function readingPending(r){return r.eligibility!=='exclude'&&r.status!=='confirmed'&&r.reading_status!=='brief_done';}
function initReading(){
 const groups=meta.reading_plan?.groups||[];if(!groups.length)return;
 $('#queue').insertAdjacentHTML('afterbegin','<option value="reading_pending">Reading to do</option><option value="reading_selected">Selected for detailed reading</option><option value="brief_done">Brief checks completed</option>');
 $('#queue').value='reading_pending';classTab=false;
 $('#reading-filter-wrap').hidden=false;
 for(const [i,g] of groups.entries()){
  const n=meta.records.filter(r=>r.reading_group===g.id&&r.eligibility!=='exclude').length;
  const option=document.createElement('option');option.value=g.id;option.textContent=`${i+1}. ${g.title} (${n})`;$('#reading-filter').append(option);
 }
 const option=document.createElement('option');option.value='unassigned';option.textContent='Unassigned — check manually';$('#reading-filter').append(option);
 $('#reading-filter').onchange=async()=>{try{await flushReading();browse();await go(queue()[0]?.record_id);}catch(e){error(e.message);}};
 for(const reason of meta.reading_plan.reason_choices||[]){const o=document.createElement('option');o.textContent=reason;$('#reading-note').append(o);}
 $('#reading-note').onchange=()=>{readingDirty=true;readingGeneration++;$('#reading-checked').checked=false;$('#reading-state').textContent='Unsaved brief-check note';clearTimeout(readingTimer);readingTimer=setTimeout(()=>saveReading('draft').catch(e=>error(e.message)),1100);};
 $('#reading-checked').onchange=()=>{readingDirty=true;readingGeneration++;};
 $('#reading-brief').onclick=()=>completeReading('brief_done',true);
 $('#reading-detail').onclick=()=>completeReading('detailed_needed',false);
 $('#reading-later').onclick=()=>completeReading('later',true);
 $('#reading-start').onclick=startDetailed;
}
function renderReading(){
 const enabled=!!meta.reading_plan?.groups?.length;$('#reading-panel').hidden=!enabled;if(!enabled||!current)return;
 const r=current.record,review=current.reading_review;
 $('#reading-title').textContent=`${r.reading_priority===999?'':`Priority ${r.reading_priority} · `}${r.reading_title}`;
 $('#reading-state').textContent=readingNames[r.reading_status]||'Not yet checked';
 const brief=r.reading_depth==='brief';$('#brief-controls').hidden=!brief;
 $('#reading-guidance').textContent=brief?'Check the abstract and conclusion first. Select detailed reading for relevant validation, useful capabilities, important limitations or gaps in domain coverage. Open the PDF when the extracts are missing or unclear.':'Prioritise detailed reading of the application, evaluation and reported results. Complete only the extraction fields relevant to your synthesis; required fields are marked *.';
 for(const o of $('#reading-note').options)o.selected=(review?.payload?.reason_choices||[]).includes(o.value);$('#reading-checked').checked=review?.payload?.checked===true;
 $('#reading-start').hidden=brief&&r.reading_status!=='detailed_needed';
}
async function startDetailed(){try{await flushReading();await flushClassification();classTab=false;group=meta.groups[0];activeField=meta.fields.find(f=>f.group===group).id;renderClassification();renderSteps();renderFields();renderEvidence();$('#steps').scrollIntoView({block:'start',behavior:'smooth'});}catch(e){error(e.message);}}
async function saveReading(status='draft'){
 clearTimeout(readingTimer);if(readingPromise)await readingPromise;if(!current||!meta.reading_plan?.groups?.length)return;
 const selected=current,id=selected.record.record_id,gen=readingGeneration;
 const payload={note:[...$('#reading-note').selectedOptions].map(o=>o.value).join('; '),reason_choices:[...$('#reading-note').selectedOptions].map(o=>o.value),reviewer:$('#reviewer').value.trim(),checked:$('#reading-checked').checked};
 readingPromise=api('/api/reading',{id,revision:selected.reading_review?.revision||0,status,payload});
 try{
  const saved=await readingPromise;selected.reading_review=saved;
  const index=meta.records.find(r=>r.record_id===id);Object.assign(index,{reading_status:saved.status,reading_note:saved.payload.note,reading_reviewer:saved.payload.reviewer});selected.record.reading_status=saved.status;
  if(current===selected&&gen===readingGeneration){readingDirty=false;$('#reading-state').textContent=readingNames[saved.status];}
  browse();error('');return saved;
 }catch(e){error(e.message);throw e;}finally{readingPromise=null;}
}
async function flushReading(){clearTimeout(readingTimer);if(readingPromise)await readingPromise;if(readingDirty){await saveReading('draft');if(readingDirty)await flushReading();}}
async function completeReading(status,advance){
 if(navBusy)return;navBusy=true;const selected=current;$('#paper').inert=true;
 try{
  await flushClassification();await flush();
  const rows=queue(),i=rows.findIndex(r=>r.record_id===selected.record.record_id),next=rows.slice(i+1).concat(rows.slice(0,i)).find(r=>r.record_id!==selected.record.record_id)?.record_id;
  await saveReading(status);renderReading();navBusy=false;
  if(advance)await go(next||queue().find(r=>r.record_id!==selected.record.record_id)?.record_id||null);else await startDetailed();
 }catch(e){error(e.message);}finally{navBusy=false;$('#paper').inert=false;}
}
