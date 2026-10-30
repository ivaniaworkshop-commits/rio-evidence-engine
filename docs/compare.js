/* Browser-local demonstration; Python core remains authoritative. */
(function(root){
function compare(baseline,candidate){
 function keyed(rows){
  if(!Array.isArray(rows)||!rows.length)throw Error('Expected a nonempty array of cases');
  const map=new Map();
  for(const row of rows){
   if(!row||typeof row!=='object'||Array.isArray(row)||Object.keys(row).sort().join(',')!=='case_id,correct,latency_ms')throw Error('Each row needs exactly case_id, correct, latency_ms');
   if(typeof row.case_id!=='string'||!row.case_id.trim()||map.has(row.case_id))throw Error('Missing or duplicate case id');
   if(typeof row.correct!=='boolean'||typeof row.latency_ms!=='number'||!Number.isFinite(row.latency_ms)||row.latency_ms<0)throw Error('Invalid correctness or latency');
   map.set(row.case_id,row);
  }return map;
 }
 const a=keyed(baseline),b=keyed(candidate);
 if(a.size!==b.size||[...a.keys()].some(k=>!b.has(k)))throw Error('Unpaired case ids');
 let ac=0,bc=0,latency=0;for(const [k,row] of a){ac+=Number(row.correct);bc+=Number(b.get(k).correct);latency+=(b.get(k).latency_ms-row.latency_ms)/a.size;}
 if(!Number.isFinite(latency))throw Error('Latency arithmetic overflow');
 return {n:a.size,baseline_correct:ac,candidate_correct:bc,correct_delta:bc-ac,mean_latency_delta_ms:latency,scope:'SYNTHETIC_BROWSER_DEMO_NOT_USERS'};
}
root.rioCompare=compare;if(typeof module!=='undefined')module.exports=compare;
})(typeof globalThis!=='undefined'?globalThis:this);
