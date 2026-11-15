
/* RÍO Primer Cobro R013: QR versión 5, corrección L, máscara 0.
 * Implementación original de codificación QR de bytes ASCII para DEMOSTRACIÓN.
 * No genera solicitudes CoDi, enlaces bancarios ni instrumentos de pago.
 */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.RioQR=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const SIZE=37, DATA=108, ECC=26;
function invariant(v,msg){if(!v)throw new Error(msg)}
function gfMultiply(x,y){let z=0;for(let i=7;i>=0;i--){z=(z<<1)^((z>>>7)*0x11d);z^=((y>>>i)&1)*x;}return z;}
function ecc(data){let gen=[1],power=1;
 for(let i=0;i<ECC;i++){const next=new Array(gen.length+1).fill(0);for(let j=0;j<gen.length;j++){next[j]^=gen[j];next[j+1]^=gfMultiply(gen[j],power);}gen=next;power=gfMultiply(power,2);}
 const result=data.concat(Array(ECC).fill(0));for(let i=0;i<DATA;i++){const factor=result[i];for(let j=0;j<gen.length;j++)result[i+j]^=gfMultiply(gen[j],factor);}return result.slice(DATA);
}
function encodeBytes(payload){invariant(typeof payload==='string'&&/^[\x20-\x7E]+$/.test(payload),'QR requiere texto ASCII imprimible.');const bytes=Array.from(payload).map(c=>c.charCodeAt(0));invariant(bytes.length<=106,'Contenido de QR demasiado extenso.');
 const bits=[];function put(n,len){for(let i=len-1;i>=0;i--)bits.push((n>>>i)&1)}put(4,4);put(bytes.length,8);for(const b of bytes)put(b,8);for(let i=0;i<4&&bits.length<DATA*8;i++)bits.push(0);while(bits.length%8)bits.push(0);
 const result=[];for(let i=0;i<bits.length;i+=8){let n=0;for(let j=0;j<8;j++)n=n*2+bits[i+j];result.push(n)}let padIndex=0;while(result.length<DATA)result.push((padIndex++%2===0)?0xec:0x11);return result;
}
function matrix(payload){const data=encodeBytes(payload),all=data.concat(ecc(data));invariant(all.length===134,'Longitud QR inválida');const mods=Array.from({length:SIZE},()=>Array(SIZE).fill(false)),func=Array.from({length:SIZE},()=>Array(SIZE).fill(false));
 function mark(x,y,dark){if(x>=0&&y>=0&&x<SIZE&&y<SIZE){mods[y][x]=!!dark;func[y][x]=true;}}
 function finder(cx,cy){for(let dy=-4;dy<=4;dy++)for(let dx=-4;dx<=4;dx++){const dist=Math.max(Math.abs(dx),Math.abs(dy));mark(cx+dx,cy+dy,dist!==2&&dist!==4);}}
 finder(3,3);finder(SIZE-4,3);finder(3,SIZE-4);
 for(let i=8;i<SIZE-8;i++){mark(i,6,i%2===0);mark(6,i,i%2===0);}
 for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++)mark(30+dx,30+dy,Math.max(Math.abs(dx),Math.abs(dy))!==1);
 function fmt(i,dark){if(i<=5)mark(8,i,dark);else if(i===6)mark(8,7,dark);else if(i===7)mark(8,8,dark);else if(i===8)mark(7,8,dark);else mark(14-i,8,dark);
 if(i<8)mark(SIZE-1-i,8,dark);else mark(8,SIZE-15+i,dark);}
 // Reserva las celdas de formato antes de ubicar datos.
 for(let i=0;i<15;i++)fmt(i,false);mark(8,SIZE-8,true);
 const bitdata=all.flatMap(n=>Array.from({length:8},(_,i)=>(n>>>(7-i))&1));let k=0;
 for(let right=SIZE-1;right>=1;right-=2){if(right===6)right=5;for(let vert=0;vert<SIZE;vert++){const y=((right+1)&2)===0?SIZE-1-vert:vert;for(let j=0;j<2;j++){const x=right-j;if(func[y][x])continue;const bit=k<bitdata.length?bitdata[k]:0;k++;mods[y][x]=!!(bit^(((x+y)&1)===0?1:0));}}}
 invariant(k===SIZE*SIZE-func.flat().filter(Boolean).length,'Ubicación QR incompleta');
 const ecLevel=1,mask=0,formatData=(ecLevel<<3)|mask;let rem=formatData;for(let i=0;i<10;i++)rem=(rem<<1)^(((rem>>>9)&1)*0x537);const fmtBits=((formatData<<10)|rem)^0x5412;for(let i=0;i<15;i++)fmt(i,((fmtBits>>>i)&1)!==0);mark(8,SIZE-8,true);
 return mods;
}
function svgText(payload,scale=7){const q=matrix(payload),quiet=4,count=SIZE+2*quiet;let paths=[];for(let y=0;y<SIZE;y++)for(let x=0;x<SIZE;x++)if(q[y][x])paths.push('M'+(x+quiet)+' '+(y+quiet)+'h1v1h-1z');return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+count+' '+count+'" width="'+(count*scale)+'" height="'+(count*scale)+'" role="img" aria-label="QR de práctica, no pagable"><rect width="'+count+'" height="'+count+'" fill="#fff"/><path d="'+paths.join('')+'" fill="#122638"/></svg>';}
return {matrix,svgText,encodeBytes};
});

