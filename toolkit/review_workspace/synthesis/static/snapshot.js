'use strict';
// Read-only transport for the SAME application used by the live CSV toolkit.
// No fetch, server, database, source-paper text, or model service is used here.
(function(){
 function parseCSV(text){
  text=text.replace(/^\uFEFF/,'');const rows=[];let row=[],cell='',quoted=false,closed=false;
  for(let i=0;i<text.length;i++){
   const c=text[i];
   if(quoted){if(c==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}else cell+=c;continue;}
   if(c==='"'){if(cell||closed)throw Error('Unexpected quote in CSV.');quoted=true;continue;}
   if(c===','||c==='\n'||c==='\r'){row.push(cell);cell='';closed=false;if(c!==','){if(c==='\r'&&text[i+1]==='\n')i++;if(row.some(v=>v!==''))rows.push(row);row=[];}continue;}
   if(closed)throw Error('Unexpected text after a quoted CSV field.');cell+=c;
  }
  if(quoted)throw Error('The CSV ends inside a quoted field.');
  if(cell||row.length){row.push(cell);rows.push(row);}
  const headers=rows.shift()||[];
  if(!headers.includes('record_id')||!headers.includes('title'))throw Error('Choose an assessment-summary CSV with record_id and title columns.');
  if(new Set(headers).size!==headers.length)throw Error('Duplicate CSV column names.');
  const ids=new Set();return rows.map((values,i)=>{
   if(values.length!==headers.length)throw Error('Incorrect field count on CSV row '+(i+2));
   const r=Object.fromEntries(headers.map((k,j)=>[k,values[j]]));
   if(!r.record_id||ids.has(r.record_id))throw Error('Missing or duplicate paper ID: '+r.record_id);ids.add(r.record_id);return r;
  });
 }
 const split=v=>String(v||'').split(';').map(s=>s.trim()).filter(Boolean);
 const unique=arr=>[...new Set(arr)];
 let records=[],fields=[],project={},csvText='',sourceName='Packaged CSV snapshot';
 const states=new Set(['unchecked','recorded','not_reported','not_applicable','unclear']);
 const decode64=s=>new TextDecoder().decode(Uint8Array.from(atob(s.trim()),c=>c.charCodeAt(0)));
 const settings=JSON.parse(decode64(document.getElementById('snapshot-settings').textContent));
 function load(text,name){
  const parsed=parseCSV(text);if(!parsed.length)throw Error('This CSV has no paper records.');
  const keys=Object.keys(parsed[0]).filter(k=>k.endsWith('_state')).map(k=>k.slice(0,-6));
  if(!keys.length)throw Error('This CSV has no assessment fields with matching _state columns.');
  const inferred=keys.map(id=>{
   const configured=settings.fields?.find(f=>f.id===id);
   const values=unique(parsed.flatMap(r=>r[id+'_state']==='recorded'?(r[id+'_choices']?parseChoices(r[id+'_choices'],r.record_id):configured?.type==='multi'||id==='gap_compact'?split(r[id]):[r[id]].filter(Boolean)):[]));
   const special=id==='farm_use_compact'?{title:'Testing and farm use',group:'Evidence',type:'single'}:id==='gap_compact'?{title:'Main gap',group:'Synthesis',type:'multi',author:true}:{};
   return {...{id,title:id.replaceAll('_',' '),group:'Evidence',type:'text',hint:'Saved assessment from the CSV.',required:false,author:false},...special,...configured,options:unique([...(configured?.options||[]),...values])};
  });
  const next=parsed.map(r=>{
   const fieldValues={};for(const f of inferred){const state=r[f.id+'_state']||'unchecked';if(!states.has(state))throw Error('Unknown field state for '+r.record_id+': '+state);fieldValues[f.id]={state,value:r[f.id]||'',choices:state==='recorded'&&f.type!=='text'?(r[f.id+'_choices']?parseChoices(r[f.id+'_choices'],r.record_id):f.type==='single'?[r[f.id]].filter(Boolean):split(r[f.id])):[],pages:r[f.id+'_pages']||'',evidence:[]};}
   return {...r,year:r.year||'',authors:r.authors||'',report_categories:r.report_categories||'',report_core_domains:r.report_core_domains||'',status:r.status||'unreviewed',classification_status:r.classification_status||'exported',reading_priority:Number(r.reading_priority)||999,revision:0,review:{id:r.record_id,status:r.status||'unreviewed',revision:0,updated_at:r.verification_recorded_at||'',payload:{fields:fieldValues,reviewer:r.verification_reviewer||'',verified:r.extraction_verified==='true'}}};
  });
  fields=inferred;records=next;csvText=text;sourceName=name;
  project={...settings,name:settings.name||'Corpus explorer',fields,categories:(settings.categories?.length?settings.categories:unique(records.flatMap(r=>split(r.report_categories))).map(name=>({name})))};
 }
 function parseChoices(raw,id){const value=JSON.parse(raw);if(!Array.isArray(value)||value.some(x=>typeof x!=='string'))throw Error('Invalid saved choices for '+id);return value;}
 const categoryNames=()=>project.categories.map(c=>typeof c==='string'?c:c.name);
 const domainNames=()=>unique(records.flatMap(r=>split(r.report_core_domains)));
 function record(id){const r=records.find(r=>r.record_id===id);if(!r)throw Error('Paper not found: '+id);return r;}
 const snapshot={parseCSV,load,get csv(){return csvText;},get name(){return sourceName;},api:async(path,body)=>{
  if(body!==undefined)throw Error('This is a read-only CSV snapshot. Use the toolkit to edit.');
  if(path==='/api/meta')return {version:'unified-review-2026-09-30-v18-csv',project,fields,groups:unique(fields.map(f=>f.group)),domains:domainNames(),domain_fields:[],records,reading_plan:{groups:[]}};
  if(path==='/api/overview')return {records,domain_notes:[]};
  if(path.startsWith('/api/domain'))return {payload:{},revision:0};
  if(path.startsWith('/api/record/')){const r=record(decodeURIComponent(path.split('/').pop()));return {record:r,review:r.review,evidence:[],candidates:{},paper_sections:null,stale:[]};}
  if(path.startsWith('/api/classification/')){const r=record(decodeURIComponent(path.split('/').pop()));return {record:{...r,review_status:'exported',review:{payload:{labels:Object.fromEntries(categoryNames().map(k=>[k,split(r.report_categories).includes(k)?'yes':'uncertain'])),domains:{core:split(r.report_core_domains),secondary:[],primary:'',reviewed:r.author_verified==='true',note:''}}}},categories:categoryNames(),domains:domainNames(),project};}
  throw Error('This function is not available in the CSV snapshot.');
 }};
 load(decode64(document.getElementById('snapshot-csv').textContent),settings.snapshot_label||'Packaged CSV snapshot');window.reviewSnapshot=snapshot;
})();
