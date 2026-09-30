const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const base=__dirname;
function run(text,settings={}){
 const b64=s=>Buffer.from(s,'utf8').toString('base64');const elements={'snapshot-csv':{textContent:b64(text)},'snapshot-settings':{textContent:b64(JSON.stringify(settings))}};
 const c={window:{},TextDecoder,Uint8Array,atob:s=>Buffer.from(s,'base64').toString('binary'),document:{getElementById:id=>elements[id]}};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(base,'synthesis/static/snapshot.js'),'utf8'),c);vm.runInContext(fs.readFileSync(path.join(base,'synthesis/static/synthesis-map.js'),'utf8'),c);return c;
}
(async()=>{
 const csv='record_id,title,report_categories,report_core_domains,status,test,test_state,test_pages,test_evidence_ids\r\nA,"Title, with ""quotes""\nand a line",X; Y,One,assessed,Field,recorded,2,e1\r\nB,Other,Y,Two,draft,,unclear,,\r\n';
 const c=run(csv,{fields:[{id:'test',title:'Test',group:'Evidence',type:'single',options:['Lab','Field']}]});const s=c.window.reviewSnapshot;const m=await s.api('/api/meta');
 assert.equal(m.records.length,2);assert.equal(m.records[0].title,'Title, with "quotes"\nand a line');assert.equal(m.records[1].review.payload.fields.test.state,'unclear');assert.equal(m.records[0].status,'assessed');assert.equal(m.records[1].status,'draft');
 const cats=await s.api('/api/classification/B');assert.equal(cats.record.review.payload.labels.X,'uncertain');assert.equal(cats.record.review.payload.labels.Y,'yes');
 await assert.rejects(s.api('/api/save',{}),/read-only/);assert.throws(()=>s.parseCSV('record_id,title\nA,First\nA,Second'),/duplicate/);assert.throws(()=>s.parseCSV('record_id,title\nA,"truncated'),/quoted/);assert.throws(()=>s.parseCSV('record_id,title\nA,B,C'),/field count/);
 c.rows=m.records;c.field=m.fields[0];const counts=vm.runInContext('synthesisCounts(rows,field)',c);assert.equal(counts.total,2);assert.equal(counts.missing,1);assert.equal(counts.counts[1].n,1);
 const q=v=>'"'+String(v).replaceAll('"','""')+'"';
 const precise=[['record_id','title','eligibility','test','test_state','test_choices'],['C','Excluded example','exclude','Field; controlled','recorded',JSON.stringify(['Field; controlled'])]].map(row=>row.map(q).join(',')).join('\n');
 const exact=run(precise,{fields:[{id:'test',title:'Test',group:'Evidence',type:'single',options:['Field; controlled']}]});const exactMeta=await exact.window.reviewSnapshot.api('/api/meta');assert.equal(exactMeta.records[0].eligibility,'exclude');assert.deepEqual(Array.from(exactMeta.records[0].review.payload.fields.test.choices),['Field; controlled']);assert.equal(exactMeta.fields[0].options.length,1);
 console.log('CSV parser, read-only API, overlapping categories, field states and map counts: passed.');
})().catch(e=>{console.error(e);process.exit(1)});
