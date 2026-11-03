/* Browser-local demonstration; Python core remains authoritative. */
(function(root){
function parseStrict(text){
 if(typeof text!=='string')throw Error('JSON input must be text');
 if(new TextEncoder().encode(text).length>1048576)throw Error('JSON input exceeds 1 MiB limit');
 // JSON.parse validates grammar; scan member names before accepting its collapsed result.
 const value=JSON.parse(text);
 const stack=[];
 const numberToken=/-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
 for(let i=0;i<text.length;){
  const c=text[i];
  if(c==='"'){
   const start=i++;
   while(i<text.length){if(text[i]==='\\'){i+=2;continue;}if(text[i++]==='"')break;}
   const frame=stack[stack.length-1];
   if(frame&&frame.object&&frame.expectKey){
    const key=JSON.parse(text.slice(start,i));
    if(frame.keys.has(key))throw Error('duplicate JSON key: '+key);
    frame.keys.add(key);frame.expectKey=false;
   }
   continue;
  }
  if(c==='-'||(c>='0'&&c<='9')){
   // The JS parser has already validated JSON grammar, but may round integer literals.
   numberToken.lastIndex=i;
   const token=numberToken.exec(text)[0];
   if(token==='-0')throw Error('negative zero integer token is not cross-runtime portable');
   if(!/[.eE]/.test(token)){
    const digits=token[0]==='-'?token.slice(1):token;
    if(digits.length>16||(digits.length===16&&digits>'9007199254740991'))
     throw Error('unsafe JSON integer outside +/- (2^53 - 1)');
   }
   const numeric=Number(token);
   if(!Number.isFinite(numeric))throw Error('JSON number outside finite binary64 range');
   const mantissa=token.split(/[eE]/,1)[0];
   if(numeric===0&&/[1-9]/.test(mantissa))
    throw Error('nonzero JSON number underflows binary64');
   i+=token.length;
   continue;
  }
  if(c==='{')stack.push({object:true,expectKey:true,keys:new Set()});
  else if(c==='[')stack.push({object:false});
  else if(c==='}'||c===']')stack.pop();
  else if(c===','){
   const frame=stack[stack.length-1];
   if(frame&&frame.object)frame.expectKey=true;
  }
  i++;
 }
 return value;
}

const bitBuffer=new ArrayBuffer(8), bitView=new DataView(bitBuffer);
function binary64Units(value){
 // All finite binary64 values are integer multiples of the smallest subnormal.
 bitView.setFloat64(0,value,false);
 const bits=bitView.getBigUint64(0,false);
 const exponent=Number((bits>>52n)&2047n);
 const mantissa=bits&((1n<<52n)-1n);
 const units=exponent===0?mantissa:((1n<<52n)|mantissa)<<BigInt(exponent-1);
 return (bits>>63n)?-units:units;
}
function roundBinary64Mean(total,count){
 if(total===0n)return 0;
 const negative=total<0n;
 const numerator=negative?-total:total;
 const denominator=BigInt(count);
 let shift=Math.max(0,numerator.toString(2).length-denominator.toString(2).length-52);
 while(shift>0&&numerator<(denominator<<BigInt(52+shift)))shift--;
 while(numerator>=(denominator<<BigInt(53+shift)))shift++;
 const divisor=denominator<<BigInt(shift);
 let q=numerator/divisor;
 const rem=numerator%divisor;
 if(2n*rem>divisor||(2n*rem===divisor&&(q&1n)===1n))q++;
 if(q>=(1n<<53n)){q>>=1n;shift++;}
 let bits;
 if(q>=(1n<<52n)){
  const exp=BigInt(shift+1);
  if(exp>=2047n)throw Error('Mean latency cannot be represented in binary64');
  bits=(exp<<52n)|(q-(1n<<52n));
 }else bits=q;
 if(negative)bits|=1n<<63n;
 bitView.setBigUint64(0,bits,false);
 return bitView.getFloat64(0,false);
}

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
 let ac=0,bc=0,totalUnits=0n;
 for(const [k,row] of a){
  ac+=Number(row.correct);bc+=Number(b.get(k).correct);
  totalUnits+=binary64Units(b.get(k).latency_ms)-binary64Units(row.latency_ms);
 }
 // Exact BigInt accumulation; one final ties-to-even rounding, independent of row order.
 const latency=roundBinary64Mean(totalUnits,a.size);
 return {n:a.size,baseline_correct:ac,candidate_correct:bc,correct_delta:bc-ac,mean_latency_delta_ms:latency,scope:'SYNTHETIC_BROWSER_DEMO_NOT_USERS'};
}
compare.parseStrict=parseStrict;
root.rioCompare=compare;if(typeof module!=='undefined')module.exports=compare;
})(typeof globalThis!=='undefined'?globalThis:this);
