'use strict';
function choiceControl(f,selected,scope){
 if(f.type==='single')return `<select class="single-choice" id="value-${esc(f.id)}" data-single-choice-field="${esc(f.id)}" aria-label="${esc(f.title)}"><option value="">Choose…</option>${f.options.map(o=>`<option ${selected.includes(o)?'selected':''}>${esc(o)}</option>`).join('')}</select>`;
 return `<details class="choice-picker"><summary><span data-choice-caption="${esc(f.id)}">${esc(selected.length?selected.join(' · '):'Choose one or more…')}</span></summary><div class="choice-options" id="value-${esc(f.id)}" role="group" aria-label="${esc(f.title)}">${f.options.map((o,i)=>`<label><input type="checkbox" name="${esc(scope)}" data-choice-field="${esc(f.id)}" value="${esc(o)}" ${selected.includes(o)?'checked':''}><span>${esc(o)}</span></label>`).join('')}</div></details>`;
}

function bindChoices(container,update){
 $$(container+' [data-single-choice-field]').forEach(el=>el.onchange=()=>update(el.dataset.singleChoiceField,el.value?[el.value]:[]));
 $$(container+' .choice-picker').forEach(el=>el.ontoggle=()=>{if(el.open)$$(container+' .choice-picker').forEach(other=>{if(other!==el)other.open=false;});});
 $$(container+' [data-choice-field]').forEach(el=>el.onchange=()=>{
  const key=el.dataset.choiceField,spec=meta.fields.find(f=>f.id===key),inputs=$$(container+` [data-choice-field="${key}"]`);
  if(el.checked&&spec.exclusive_options?.includes(el.value))inputs.forEach(i=>{if(i!==el)i.checked=false;});
  else if(el.checked)inputs.forEach(i=>{if(spec.exclusive_options?.includes(i.value))i.checked=false;});
  const values=inputs.filter(i=>i.checked).map(i=>i.value);$(`[data-choice-caption="${key}"]`).textContent=values.length?values.join(' · '):'Choose one or more…';update(key,values);
 });
}
function renderChoiceSummary(rows,fields){
 $('#choice-summary').innerHTML=fields.filter(f=>f.type&&f.type!=='text').map(f=>{
  const items=rows.map(r=>r.review.payload.fields[f.id]);
  const n=items.filter(x=>x.state==='recorded').length;
  return `<article><h3>${esc(f.title)}</h3><p class="small">${n} recorded / ${rows.length} papers shown${f.type==='multi'?' · several choices allowed':''}</p>${f.options.map(o=>{const c=items.filter(x=>x.state==='recorded'&&x.choices?.includes(o)).length;return `<div class="choice-count"><span>${esc(o)}</span><b>${c}</b><progress max="${rows.length||1}" value="${c}" aria-label="${esc(o)}: ${c}"></progress></div>`;}).join('')}<p class="small">${['unchecked','not_reported','not_applicable','unclear'].map(s=>`${labels[s]}: ${items.filter(x=>x.state===s).length}`).join(' · ')}</p></article>`;
 }).join('');
}
function renderLegacy(){
 const old=current.review.payload.legacy_fields||{},items=Object.entries(old).filter(([k,v])=>v.value||v.pages||v.evidence?.length||v.state!=='unchecked');
 $('#legacy-notes').hidden=!items.length;
 $('#legacy-content').innerHTML='<p class="small">Your earlier entries are preserved verbatim. They have not been automatically converted into choices or counted as confirmed structured extraction.</p>'+items.map(([k,v])=>`<h3>${esc(meta.project.legacy_field_titles?.[k]||k)}</h3><p>${esc(v.value)}</p><p class="small">${esc(v.state)} · ${esc(v.pages||'')}</p>`).join('');
}
