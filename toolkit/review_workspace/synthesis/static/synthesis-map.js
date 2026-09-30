'use strict';

// Count unique papers. Missing/unclear fields never become negative findings.
function uniqueSynthesisRows(rows){return [...new Map(rows.map(r=>[r.record_id,r])).values()];}
function synthesisGroups(row,dimension){
 const key=dimension==='categories'?'report_categories':'report_core_domains';
 return [...new Set(String(row[key]||'').split(';').map(s=>s.trim()).filter(Boolean))];
}
function synthesisChoices(row,field){
 const item=row.review?.payload?.fields?.[field.id];
 return item?.state==='recorded'?[...new Set((item.choices||[]).filter(v=>field.options.includes(v)))]:[];
}
function synthesisCounts(rows,field){
 const papers=uniqueSynthesisRows(rows),counts=field.options.map(option=>({option,n:papers.filter(r=>synthesisChoices(r,field).includes(option)).length}));
 return {total:papers.length,counts,missing:papers.filter(r=>!synthesisChoices(r,field).length).length};
}
function makeSynthesisMatrix(rows,field,dimension,groups){
 const papers=uniqueSynthesisRows(rows),names=[...new Set(groups)];
 if(papers.some(r=>!synthesisGroups(r,dimension).length))names.push(null);
 return names.map(name=>{
  const selected=papers.filter(r=>name===null?!synthesisGroups(r,dimension).length:synthesisGroups(r,dimension).includes(name));
  return {name,...synthesisCounts(selected,field)};
 });
}
function filterSynthesisRows(rows,focus,fields){
 if(!focus)return uniqueSynthesisRows(rows);
 const field=fields.find(f=>f.id===focus.fieldId);
 return uniqueSynthesisRows(rows).filter(r=>{
  if(focus.dimension){const groups=synthesisGroups(r,focus.dimension);if(focus.group===null?groups.length:!groups.includes(focus.group))return false;}
  if(!focus.fieldId)return true;
  if(!field)return false;
  const choices=synthesisChoices(r,field);
  return focus.option===null?!choices.length:choices.includes(focus.option);
 });
}

let synthesisFocus=null,synthesisMatrixField='',synthesisMatrixDimension='domains',synthesisCohort='';
function synthesisFocusTitle(focus,fields){
 if(!focus)return 'All papers in the current view';
 const parts=[];
 if(focus.dimension)parts.push(focus.group===null?'Unassigned':focus.group);
 if(focus.fieldId){const field=fields.find(f=>f.id===focus.fieldId);parts.push(`${field?.title||focus.fieldId}: ${focus.option===null?'No recorded choice':focus.option}`);}
 return parts.join(' · ');
}
function pickSynthesisFocus(focus){
 synthesisFocus=JSON.stringify(synthesisFocus)===JSON.stringify(focus)?null:focus;
 renderOverview();$('#synthesis-papers').scrollIntoView({behavior:'smooth',block:'start'});
}
function resetSynthesisFocus(){synthesisFocus=null;renderOverview();}
function renderSynthesisMap(rows,all){
 const host=$('#synthesis-visuals'),choiceFields=meta.fields.filter(f=>['single','multi'].includes(f.type)&&f.options?.length);
 const cohort=[$('#overview-state').value,$('#overview-domain').value,$('#overview-category').value].join('|');
 if(synthesisCohort!==cohort){synthesisFocus=null;synthesisCohort=cohort;}
 if(!choiceFields.some(f=>f.id===synthesisMatrixField))synthesisMatrixField=(choiceFields.find(f=>!f.author&&f.type==='single')||choiceFields[0])?.id||'';
 if(!choiceFields.length){host.innerHTML='<p class="map-empty">Add choice fields in project setup to build a visual map. Your text entries remain available below.</p>';return;}
 const field=choiceFields.find(f=>f.id===synthesisMatrixField),selectedDomain=$('#overview-domain').value,selectedCategory=$('#overview-category').value;
 const present=[...new Set(all.flatMap(r=>synthesisGroups(r,synthesisMatrixDimension)))];
 const configured=synthesisMatrixDimension==='domains'?meta.domains:(meta.project.categories||[]).map(c=>c.name);
 const selected=synthesisMatrixDimension==='domains'?selectedDomain:selectedCategory;
 const groups=selected?[selected]:[...new Set([...configured.filter(g=>present.includes(g)),...present])];
 const matrix=makeSynthesisMatrix(rows,field,synthesisMatrixDimension,groups),focusButtons=[];
 const makeFocus=(focus,content,n,extra='')=>{
  const id=focusButtons.push(focus)-1,active=JSON.stringify(focus)===JSON.stringify(synthesisFocus);
  return `<button type="button" data-map-focus="${id}" ${n?'':'disabled'} aria-pressed="${active}" class="${extra}${active?' is-selected':''}">${content}</button>`;
 };
 const cards=choiceFields.map((spec,index)=>{
  const stat=synthesisCounts(rows,spec),tone=spec.author?(index%2?'amber':'teal'):'blue';
  return `<article class="map-card tone-${tone}"><div class="map-card-top"><span class="map-kicker">${spec.author?'Interpretation':'Reported evidence'}</span><span class="map-answer-count">${stat.total-stat.missing} / ${stat.total} answered</span></div><h2>${esc(spec.title)}</h2><div class="map-bars">${stat.counts.map(({option,n})=>makeFocus({fieldId:spec.id,option},`<span class="map-bar-label">${esc(option)}</span><b>${n}</b><progress max="${stat.total||1}" value="${n}" aria-label="${esc(option)}: ${n} of ${stat.total} papers"></progress>`,n,'map-bar')).join('')}</div><div class="map-card-bottom"><span>${spec.type==='multi'?'Several choices per paper':'One choice per paper'}</span>${stat.missing?makeFocus({fieldId:spec.id,option:null},`${stat.missing} with no recorded choice`,stat.missing,'map-missing'):'<span>All answered</span>'}</div></article>`;
 }).join('');
 const empty=!rows.length?`<div class="map-empty"><strong>No ${$('#overview-state').value==='confirmed'?'confirmed':'saved'} extraction entries in this selection yet.</strong><p>${$('#overview-state').value==='confirmed'?'You can preview saved drafts, or confirm papers to build the map.':'Change the filters or record extraction choices first.'}</p>${$('#overview-state').value==='confirmed'&&all.some(r=>r.status!=='unreviewed'&&r.status!=='confirmed')?'<button type="button" id="map-show-drafts">Preview saved drafts</button>':''}</div>`:'';
 const matrixRows=matrix.map(row=>{
  const title=row.name===null?'Unassigned':row.name;
  const cells=[...row.counts,{option:null,n:row.missing}].map(({option,n})=>{
   const share=row.total?n/row.total:0,level=n?Math.max(1,Math.ceil(share*5)):0;
   const cellTitle=`${title} · ${option===null?'No recorded choice':option}: ${n} of ${row.total} papers (${Math.round(share*100)}%)`;
   const contents=`<span class="matrix-number">${row.total?n:'—'}</span><span class="matrix-share">${row.total?Math.round(share*100)+'%':'no entries'}</span>`;
   return `<td title="${esc(cellTitle)}">${makeFocus({fieldId:field.id,option,dimension:synthesisMatrixDimension,group:row.name},`<span class="sr-only">${esc(cellTitle)}</span><span aria-hidden="true">${contents}</span>`,n,`matrix-cell level-${level}${option===null?' matrix-missing':''}`)}</td>`;
  }).join('');
  return `<tr><th scope="row">${makeFocus({dimension:synthesisMatrixDimension,group:row.name},`<span>${esc(title)}</span><small>${row.total} ${row.total===1?'paper':'papers'}</small>`,row.total,'matrix-row-label')}</th>${cells}</tr>`;
 }).join('');
 host.innerHTML=`${empty}<div class="map-cards">${cards}</div><section class="matrix-panel"><div class="matrix-heading"><div><span class="map-kicker">Explore the evidence</span><h2>Papers by ${synthesisMatrixDimension==='domains'?'domain':'category'}</h2><p>Click a count to see the papers behind it.</p></div><div class="matrix-controls"><label>Rows<select id="matrix-dimension"><option value="domains" ${synthesisMatrixDimension==='domains'?'selected':''}>Domains</option><option value="categories" ${synthesisMatrixDimension==='categories'?'selected':''}>Categories</option></select></label><label>Columns<select id="matrix-field">${choiceFields.map(f=>`<option value="${esc(f.id)}" ${field.id===f.id?'selected':''}>${esc(f.title)}</option>`).join('')}</select></label></div></div><div class="matrix-scroll" tabindex="0" role="region" aria-label="Scrollable paper matrix"><table class="evidence-matrix"><caption class="sr-only">${esc(field.title)} by ${synthesisMatrixDimension}. Cells show unique paper counts and percentages within each row.</caption><thead><tr><th scope="col">${synthesisMatrixDimension==='domains'?'Domain':'Category'} / papers shown</th>${field.options.map(o=>`<th scope="col">${esc(o)}</th>`).join('')}<th scope="col" class="matrix-missing-head">No recorded choice</th></tr></thead><tbody>${matrixRows||'<tr><td colspan="99">No matching groups.</td></tr>'}</tbody></table></div><div class="matrix-foot"><span><span class="matrix-ramp" aria-hidden="true"></span> Lighter to darker = lower to higher share within a row.</span><span>A paper can appear in several rows${field.type==='multi'?' and columns':''}.</span></div><p class="matrix-note">${field.author?'These are interpretation choices, not measured outcomes.':'This maps the evidence recorded for each paper, not the number of farms using a technology.'} “No recorded choice” includes unclear, unchecked, not reported and not applicable entries.</p></section>`;
 host.querySelectorAll('[data-map-focus]').forEach(b=>b.onclick=()=>pickSynthesisFocus(focusButtons[Number(b.dataset.mapFocus)]));
 $('#matrix-dimension').onchange=e=>{synthesisMatrixDimension=e.target.value;synthesisFocus=null;renderOverview();};
 $('#matrix-field').onchange=e=>{synthesisMatrixField=e.target.value;synthesisFocus=null;renderOverview();};
 if($('#map-show-drafts'))$('#map-show-drafts').onclick=()=>{$('#overview-state').value='all';renderOverview();};
}

if(typeof module!=='undefined'&&module.exports)module.exports={uniqueSynthesisRows,synthesisGroups,synthesisChoices,synthesisCounts,makeSynthesisMatrix,filterSynthesisRows};
