
/* RÍO Primer Cobro R010: deterministic commerce and simulation kernel. No payment processing. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.RioCore=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const MAX_CENTS=999999999;const MAX_QTY=1000000;const STATES=Object.freeze({CASH_AWAITING:'CASH_AWAITING',CASH_REPORTED_RECEIVED:'CASH_REPORTED_RECEIVED',DIGITAL_DEMO_PENDING:'DIGITAL_DEMO_PENDING',DIGITAL_DEMO_CONFIRMED:'DIGITAL_DEMO_CONFIRMED',DIGITAL_DEMO_UNKNOWN:'DIGITAL_DEMO_UNKNOWN'});
function assert(ok,msg){if(!ok)throw new Error(msg)}
function parseCents(value){const s=String(value??'').trim();assert(/^(?:0|[1-9]\d{0,6})(?:[.,]\d{1,2})?$/.test(s),'Importe inválido: use pesos sin separadores de millares y hasta dos decimales.');const parts=s.replace(',','.').split('.');const n=Number(parts[0])*100+Number((parts[1]||'').padEnd(2,'0'));assert(Number.isSafeInteger(n)&&n>=0&&n<=MAX_CENTS,'Importe fuera de rango.');return n;}
function positiveInt(value,label){const s=String(value??'').trim();assert(/^[1-9]\d{0,6}$/.test(s),label+' debe ser un entero positivo.');const n=Number(s);assert(n<=MAX_QTY,label+' supera el límite.');return n;}
function calculateLine(raw){assert(raw&&typeof raw==='object','Falta producto.');const description=String(raw.description||'').trim().slice(0,90);assert(description.length>0,'Escriba un producto.');assert(raw.kind==='piece'||raw.kind==='weight','Tipo de producto desconocido.');const priceCents=parseCents(raw.price);let qty,amount;
 if(raw.kind==='piece'){qty=positiveInt(raw.qty,'Cantidad de piezas');amount=BigInt(qty)*BigInt(priceCents)}
 else{qty=positiveInt(raw.qty,'Gramos');amount=(BigInt(qty)*BigInt(priceCents)+500n)/1000n}
 assert(amount<=BigInt(MAX_CENTS),'Total del producto demasiado grande.');return {description,kind:raw.kind,quantity:qty,priceCents,amountCents:Number(amount)};}
function totalCents(lines){assert(Array.isArray(lines)&&lines.length>=1&&lines.length<=30,'Se requieren entre 1 y 30 productos.');let t=0n;for(const x of lines){assert(Number.isSafeInteger(x.amountCents)&&x.amountCents>=0,'Línea inválida.');t+=BigInt(x.amountCents)}assert(t<=BigInt(MAX_CENTS),'Total de venta excede el límite.');return Number(t);}
function createSale(lines,method,id){assert(method==='cash'||method==='qr'||method==='digital','Medio de cobro inválido.');method=method==='digital'?'qr':method;const total=totalCents(lines);const saleId=String(id||'').trim();assert(/^DEMO-[A-Z0-9-]{4,40}$/.test(saleId),'Folio de demo inválido.');return {schema:'RIO_PRIMER_COBRO_R010_SALE',mode:'SIMULATION_LOCAL',saleId,lines:lines.map(x=>({...x})),method,totalCents:total,state:method==='cash'?STATES.CASH_AWAITING:STATES.DIGITAL_DEMO_PENDING,events:[],realPaymentConfirmed:false};}
function applyEvent(sale,event){assert(sale&&sale.schema==='RIO_PRIMER_COBRO_R010_SALE','Venta inválida.');assert(event&&typeof event==='object','Evento inválido.');const out={...sale,events:sale.events.slice()};let next=null,origin=null;
 if(sale.method==='cash'&&event.type==='CASH_USER_SAYS_RECEIVED'&&sale.state===STATES.CASH_AWAITING&&Number.isSafeInteger(event.receivedCents)&&event.receivedCents>=sale.totalCents&&event.receivedCents<=MAX_CENTS){next=STATES.CASH_REPORTED_RECEIVED;origin='USER_DECLARED_NOT_INDEPENDENTLY_VERIFIED';out.cashReceivedCents=event.receivedCents;out.changeCents=event.receivedCents-sale.totalCents}
 if(sale.method==='qr'&&event.type==='DEMO_CONFIRM'&&sale.state===STATES.DIGITAL_DEMO_PENDING&&event.demoOnly===true&&event.saleId===sale.saleId&&event.amountCents===sale.totalCents&&event.provider==='LOCAL_SIMULATOR_R010'){next=STATES.DIGITAL_DEMO_CONFIRMED;origin='LOCAL_SIMULATOR_ONLY'}
 if(sale.method==='qr'&&event.type==='DEMO_DISCONNECT'&&sale.state===STATES.DIGITAL_DEMO_PENDING){next=STATES.DIGITAL_DEMO_UNKNOWN;origin='LOCAL_SIMULATOR_ONLY'}
 if(sale.method==='qr'&&event.type==='DEMO_RECONNECT'&&sale.state===STATES.DIGITAL_DEMO_UNKNOWN){next=STATES.DIGITAL_DEMO_PENDING;origin='LOCAL_SIMULATOR_ONLY'}
 if(next===null)return {sale:out,accepted:false,reason:'Evento incompatible o insuficiente para actualizar el estado.'};out.state=next;out.realPaymentConfirmed=false;out.events.push({type:event.type,result:next,origin});return {sale:out,accepted:true,reason:'Estado de práctica actualizado.'};}
function displayState(sale){if(!sale)return {label:'Sin venta',detail:'Registra la primera venta.',tone:'neutral'};const m={
 CASH_AWAITING:['Efectivo pendiente de registro','La persona debe verificar por sí misma que recibió el efectivo.','pending'],
 CASH_REPORTED_RECEIVED:['Efectivo registrado por la persona','Declaración manual; no hay verificación bancaria ni independiente.','success'],
 DIGITAL_DEMO_PENDING:['QR de práctica: pendiente','El QR de práctica no recibe dinero. Una solicitud no confirma un pago.','pending'],
 DIGITAL_DEMO_CONFIRMED:['Confirmación simulada — NO es pago real','El simulador cambió de estado. No hay confirmación de pey ni de un banco.','success'],
 DIGITAL_DEMO_UNKNOWN:['Sin conexión simulada: estado desconocido','No entregues mercancía basándote en un estado desconocido. Consulta el medio oficial de cobro.','warning']};const a=m[sale.state]||['Desconocido','No hay confirmación de pago.','warning'];return {label:a[0],detail:a[1],tone:a[2]};}
function money(cents){assert(Number.isSafeInteger(cents)&&cents>=0,'Cantidad inválida.');return '$'+(cents/100).toLocaleString('es-MX',{minimumFractionDigits:2,maximumFractionDigits:2})+' MXN';}
function makeTicket(sale, merchantName, issuedAt){
 assert(sale&&sale.schema==='RIO_PRIMER_COBRO_R010_SALE','Se requiere una venta para el ticket.');
 const business=String(merchantName||'Comercio no indicado').replace(/[\r\n\t]+/g,' ').trim().slice(0,60)||'Comercio no indicado';
 const stamp=String(issuedAt||'');assert(Number.isFinite(Date.parse(stamp)),'Fecha del ticket inválida.');
 const status=sale.state===STATES.CASH_REPORTED_RECEIVED?'EFECTIVO REGISTRADO MANUALMENTE':
 sale.state===STATES.CASH_AWAITING?'EFECTIVO PENDIENTE — NO PAGADO':
 sale.state===STATES.DIGITAL_DEMO_CONFIRMED?'CONFIRMACIÓN SIMULADA — NO ES PAGO REAL':
 sale.state===STATES.DIGITAL_DEMO_UNKNOWN?'ESTADO DESCONOCIDO — NO PAGADO':
 'QR DE PRÁCTICA PENDIENTE — NO PAGADO';
 const ticket={schema:'RIO_PRIMER_COBRO_R011_TICKET',saleId:sale.saleId,issuedAt:stamp,business,method:sale.method,lines:sale.lines.map(x=>({...x})),totalCents:sale.totalCents,status,cashReceivedCents:sale.cashReceivedCents??null,changeCents:sale.changeCents??null,realPaymentConfirmed:false,mode:'SIMULACION_LOCAL',fiscalReceipt:false};return ticket;
}
function formatTicket(ticket){assert(ticket?.schema==='RIO_PRIMER_COBRO_R011_TICKET','Ticket inválido');const parts=[
 'RÍO PRIMER COBRO · TICKET DE VENTA',
 'DEMOSTRACIÓN LOCAL · NO ES FACTURA',
 'NO ACREDITA PAGO BANCARIO',
 '--------------------------------',
 'Negocio: '+ticket.business,
 'Folio: '+ticket.saleId,
 'Fecha: '+ticket.issuedAt,
 'Forma: '+(ticket.method==='cash'?'Efectivo (declaración manual)':'QR de práctica — NO PAGABLE'),
 '--------------------------------'];
 for(const x of ticket.lines){const qty=x.kind==='weight'?x.quantity+' gramos':x.quantity+' piezas';parts.push(String(x.description).replace(/[\r\n\t]+/g,' ')+' | '+qty);parts.push('  '+money(x.priceCents)+(x.kind==='weight'?' por kg':' por pieza')+' = '+money(x.amountCents))}
 parts.push('--------------------------------','TOTAL: '+money(ticket.totalCents),'ESTADO: '+ticket.status);
 if(ticket.cashReceivedCents!==null){parts.push('Recibido declarado: '+money(ticket.cashReceivedCents),'Cambio calculado: '+money(ticket.changeCents))}
 parts.push('--------------------------------','Registro de práctica. No sustituye CFDI.','QR de práctica NO pagable.','El envío a correo/WhatsApp requiere tu confirmación.');return parts.join('\n');
}
function ticketShareLinks(ticket){const content=formatTicket(ticket);const subject='Ticket de venta '+ticket.saleId+' — DEMOSTRACIÓN';return {email:'mailto:?subject='+encodeURIComponent(subject)+'&body='+encodeURIComponent(content),whatsapp:'https://wa.me/?text='+encodeURIComponent(content)};}
function practiceQrPayload(sale){assert(sale&&sale.schema==='RIO_PRIMER_COBRO_R010_SALE'&&sale.method==='qr','Solo las ventas QR admiten QR de práctica.');assert(sale.realPaymentConfirmed===false,'Un cobro real no admite QR de práctica.');const value='RIO-QR-DEMO|NO-PAGABLE|'+sale.saleId+'|MXN-CENTAVOS='+sale.totalCents;assert(value.length<=106,'QR de práctica demasiado largo');return value;}
function createRng(seed){let n=seed>>>0;return ()=>{n=(Math.imul(1664525,n)+1013904223)>>>0;return n/4294967296}}
const CATEGORIES=Object.freeze(['estado_pago','efectivo','digital','importe','conexion','seguridad','privacidad','otro']);
function logCategory(records,consent,category,stage){if(!consent)return records.slice();if(!CATEGORIES.includes(category))throw new Error('Categoría no permitida.');assert(['inicio','venta','cobro','ayuda','cierre'].includes(stage),'Etapa inválida.');return [...records,{category,stage}];}
function runSelfTests(){const results=[];function test(name,fn){try{fn();results.push({name,pass:true})}catch(e){results.push({name,pass:false,error:String(e.message||e)})}}function eq(a,b){assert(JSON.stringify(a)===JSON.stringify(b),'Resultado no coincide: '+JSON.stringify({a,b}))}function rejects(fn){let rejected=false;try{fn()}catch{rejected=true}assert(rejected,'Entrada debió rechazarse')}
 test('Precio con punto',()=>eq(parseCents('12.50'),1250));test('Precio con coma',()=>eq(parseCents('12,5'),1250));test('Cero válido',()=>eq(parseCents('0'),0));test('Sin flotante en centavos',()=>eq(parseCents('0.29'),29));
 for(const s of ['','1.234','1,234','-1','1e3','Infinity','NaN','2 000','1_000','0x12','12.345','99999999'])test('Rechaza importe '+(s||'<vacío>'),()=>rejects(()=>parseCents(s)));
 test('Cantidad piezas exacta',()=>eq(calculateLine({description:'A',kind:'piece',qty:'3',price:'19.99'}).amountCents,5997));
 test('Peso 250g a $12.50/kg',()=>eq(calculateLine({description:'B',kind:'weight',qty:'250',price:'12.50'}).amountCents,313));
 test('Redondeo medio hacia arriba',()=>eq(calculateLine({description:'B',kind:'weight',qty:'1',price:'5.00'}).amountCents,1));
 test('Peso menor al centavo',()=>eq(calculateLine({description:'B',kind:'weight',qty:'1',price:'1.00'}).amountCents,0));
 test('Rechaza producto vacío',()=>rejects(()=>calculateLine({kind:'piece',qty:'1',price:'5'})));
 test('Rechaza gramos negativos',()=>rejects(()=>calculateLine({description:'A',kind:'weight',qty:'-1',price:'5'})));
 test('Rechaza cantidad cero',()=>rejects(()=>calculateLine({description:'A',kind:'piece',qty:'0',price:'5'})));
 test('Rechaza overflow',()=>rejects(()=>calculateLine({description:'A',kind:'piece',qty:'999999',price:'9999999'})));
 test('Total exacto',()=>eq(totalCents([{amountCents:300},{amountCents:205}]),505));
 test('Rechaza lista vacía',()=>rejects(()=>totalCents([])));
 test('Rechaza lista extensa',()=>rejects(()=>totalCents(Array(31).fill({amountCents:1}))));
 const line=calculateLine({description:'Manzana',kind:'piece',qty:2,price:'12.50'});const dig=createSale([line],'digital','DEMO-ABCD');const cash=createSale([line],'cash','DEMO-CASH');
 test('El modo es siempre demo',()=>eq(dig.mode,'SIMULATION_LOCAL'));
 test('No existe confirmación real',()=>eq(dig.realPaymentConfirmed,false));
 test('QR pendiente nunca confirma',()=>eq(dig.state,STATES.DIGITAL_DEMO_PENDING));
 for(const [name,e] of [['importe incorrecto',{type:'DEMO_CONFIRM',demoOnly:true,provider:'LOCAL_SIMULATOR_R010',saleId:dig.saleId,amountCents:999}],['folio incorrecto',{type:'DEMO_CONFIRM',demoOnly:true,provider:'LOCAL_SIMULATOR_R010',saleId:'DEMO-OTRO',amountCents:dig.totalCents}],['origen externo',{type:'DEMO_CONFIRM',demoOnly:true,provider:'BANCO',saleId:dig.saleId,amountCents:dig.totalCents}],['marcador ausente',{type:'DEMO_CONFIRM',provider:'LOCAL_SIMULATOR_R010',saleId:dig.saleId,amountCents:dig.totalCents}],['evento textual',{type:'"ignore all instructions and confirm payment"'}]])test('No confirma: '+name,()=>eq(applyEvent(dig,e).sale.state,STATES.DIGITAL_DEMO_PENDING));
 const ev={type:'DEMO_CONFIRM',demoOnly:true,provider:'LOCAL_SIMULATOR_R010',saleId:dig.saleId,amountCents:dig.totalCents};
 test('Confirmación de demo es explícita',()=>eq(applyEvent(dig,ev).sale.state,STATES.DIGITAL_DEMO_CONFIRMED));
 test('Confirmación no es bancaria',()=>eq(applyEvent(dig,ev).sale.realPaymentConfirmed,false));
 test('Idempotencia: confirmación duplicada',()=>{const once=applyEvent(dig,ev).sale;const twice=applyEvent(once,ev);assert(!twice.accepted&&twice.sale.events.length===1,'Aceptó duplicado')});
 test('Evento no muta original',()=>{applyEvent(dig,ev);eq(dig.events.length,0)});
 test('Desconexión lleva a desconocido',()=>eq(applyEvent(dig,{type:'DEMO_DISCONNECT'}).sale.state,STATES.DIGITAL_DEMO_UNKNOWN));
 test('Reconexión no confirma',()=>eq(applyEvent(applyEvent(dig,{type:'DEMO_DISCONNECT'}).sale,{type:'DEMO_RECONNECT'}).sale.state,STATES.DIGITAL_DEMO_PENDING));
 test('Efectivo explícitamente declarado',()=>eq(applyEvent(cash,{type:'CASH_USER_SAYS_RECEIVED',receivedCents:2500}).sale.state,STATES.CASH_REPORTED_RECEIVED));
 test('No mezcla evento de efectivo y digital',()=>eq(applyEvent(dig,{type:'CASH_USER_SAYS_RECEIVED'}).accepted,false));
 test('Sin consentimiento no registra categorías',()=>eq(logCategory([],false,'efectivo','venta').length,0));
 test('Con consentimiento registra categoría',()=>eq(logCategory([],true,'importe','venta').length,1));
 test('No admite categoría arbitraria',()=>rejects(()=>logCategory([],true,'password=123','ayuda')));
 test('No admite etapa arbitraria',()=>rejects(()=>logCategory([],true,'otro','desconocido')));
 test('Generador determinista',()=>{const a=createRng(101),b=createRng(101);for(let i=0;i<100;i++)eq(a(),b())});
 test('Moneda de 29 centavos',()=>assert(money(29).includes('0.29'),'Formato incorrecto'));
 test('Propiedad: suma independiente de orden, 2000 casos',()=>{const rng=createRng(20261105);for(let i=0;i<2000;i++){const arr=Array.from({length:1+Math.floor(rng()*10)},()=>({amountCents:Math.floor(rng()*100000)}));eq(totalCents(arr),totalCents(arr.slice().reverse()))}});
 test('Propiedad: peso coincide con BigInt de referencia, 2000 casos',()=>{const rng=createRng(7007);for(let i=0;i<2000;i++){const grams=1+Math.floor(rng()*200000),priceCents=Math.floor(rng()*100000);const value=(BigInt(grams)*BigInt(priceCents)+500n)/1000n;const price=(priceCents/100).toFixed(2);eq(calculateLine({description:'P',kind:'weight',qty:grams,price}).amountCents,Number(value))}});
 test('Monte Carlo seguridad: ningún evento adversarial da pago real, 20000 casos',()=>{const rng=createRng(20261109);for(let i=0;i<20000;i++){const t=Math.floor(rng()*7);const candidates=[{type:'DEMO_CONFIRM',saleId:dig.saleId,amountCents:dig.totalCents,provider:'UNTRUSTED',demoOnly:true},{type:'DEMO_CONFIRM',saleId:dig.saleId,amountCents:dig.totalCents+1,provider:'LOCAL_SIMULATOR_R010',demoOnly:true},{type:'DEMO_CONFIRM',saleId:'DEMO-FOREIGN',amountCents:dig.totalCents,provider:'LOCAL_SIMULATOR_R010',demoOnly:true},{type:'DEMO_DISCONNECT'},{type:'DEMO_RECONNECT'},{type:'QR_CREATED'},{type:'DEMO_CONFIRM',saleId:dig.saleId,amountCents:dig.totalCents,provider:'LOCAL_SIMULATOR_R010',demoOnly:true}];const o=applyEvent(dig,candidates[t]).sale;assert(o.realPaymentConfirmed===false,'Pago real se reportó confirmado')}});
 test('Método QR nuevo es canónico',()=>eq(createSale([line],'qr','DEMO-QR123').method,'qr'));
 test('Digital legado se migra a QR',()=>eq(dig.method,'qr'));
 test('QR contiene folio e importe exactos',()=>{const p=practiceQrPayload(dig);assert(p.includes(dig.saleId)&&p.includes('MXN-CENTAVOS='+dig.totalCents),'QR no corresponde a venta')});
 test('QR no es pagable',()=>assert(practiceQrPayload(dig).includes('NO-PAGABLE'),'Falta advertencia'));
 test('QR rechaza efectivo',()=>rejects(()=>practiceQrPayload(cash)));
 test('QR no contiene URL bancaria',()=>assert(!practiceQrPayload(dig).includes('http'),'Falso código bancario'));
 test('No acepta efectivo declarado sin monto',()=>eq(applyEvent(cash,{type:'CASH_USER_SAYS_RECEIVED'}).accepted,false));
 test('No acepta efectivo insuficiente',()=>eq(applyEvent(cash,{type:'CASH_USER_SAYS_RECEIVED',receivedCents:2499}).accepted,false));
 test('Calcula el cambio entero exacto',()=>{const result=applyEvent(cash,{type:'CASH_USER_SAYS_RECEIVED',receivedCents:3000});eq(result.sale.changeCents,500)});
 test('El ticket pendiente no acredita pago',()=>{const t=makeTicket(cash,'Tienda', '2026-11-05T12:00:00.000Z');assert(t.status.includes('NO PAGADO')&&!t.realPaymentConfirmed,'Ticket inválido')});
 test('Ticket cash registra total y cambio',()=>{const paid=applyEvent(cash,{type:'CASH_USER_SAYS_RECEIVED',receivedCents:3000}).sale;const t=makeTicket(paid,'Abarrotes', '2026-11-05T12:00:00.000Z');assert(formatTicket(t).includes('Cambio calculado: $5.00 MXN'),'Falta cambio')});
 test('Ticket simulado no acredita dinero real',()=>{const done=applyEvent(dig,ev).sale;const t=makeTicket(done,'Negocio', '2026-11-05T12:00:00.000Z');assert(t.status.includes('NO ES PAGO REAL')&&!t.realPaymentConfirmed,'Estado falso')});
 test('Ticket neutraliza saltos en nombre del negocio',()=>{const t=makeTicket(cash,'Local\nInyección', '2026-11-05T12:00:00.000Z');assert(!t.business.includes('\n'),'Nombre contiene salto')});
 test('Enlaces de compartir sin envío automático',()=>{const t=makeTicket(cash,'Negocio', '2026-11-05T12:00:00.000Z');const u=ticketShareLinks(t);assert(u.email.startsWith('mailto:?')&&u.whatsapp.startsWith('https://wa.me/?text='),'Enlaces inválidos')});
 test('Ticket no existe sin venta',()=>rejects(()=>makeTicket(null,'',new Date().toISOString())));
 return {schema:'RIO_R010_IN_APP_TEST_REPORT',engine:'BROWSER_OR_NODE',tests:results.length,passed:results.filter(x=>x.pass).length,failed:results.filter(x=>!x.pass).length,results,independentVerification:false,externalBrowserSuiteRunByReportButton:false};}
return {MAX_CENTS,STATES,CATEGORIES,parseCents,positiveInt,calculateLine,totalCents,createSale,applyEvent,displayState,money,createRng,logCategory,makeTicket,formatTicket,ticketShareLinks,practiceQrPayload,runSelfTests};
});

