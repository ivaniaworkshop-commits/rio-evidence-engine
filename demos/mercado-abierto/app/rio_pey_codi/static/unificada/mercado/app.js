/* Mercado Abierto R003 | 100% browser/offline | toda cifra es sintética.
 * El motor Python + readback es la referencia para artefactos canónicos.
 * Esta calculadora del navegador es interactiva, no evidencia comercial real.
 */
(function () {
'use strict';
const D=globalThis.RIO_BOOTSTRAP;
if (!D) throw Error('Falta data.js sintético');
const money = x => Math.round((x + Number.EPSILON) * 100) / 100;
const clamp = (x,lo,hi) => Number.isFinite(+x) ? Math.min(hi,Math.max(lo,+x)) : lo;
const peso = x => new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN',maximumFractionDigits:2}).format(x);
const rnd = (seed) => {let s=(Number(seed)>>>0)||1234567;return ()=>{s^=s<<13;s^=s>>>17;s^=s<<5;return ((s>>>0)+0.5)/4294967296;};};
const suppliers=D.suppliers;
function calc(cfg={}) {
  const mode = cfg.mode==='private'?'private':'shared';
  const sup=suppliers.find(x=>x.id===cfg.supplier)||suppliers[0];
  const orders=mode==='shared'?Math.trunc(clamp(cfg.orders??12,1,12)):1;
  const baskets=mode==='private'?Math.trunc(clamp(cfg.baskets??2,1,5)):1;
  const count=mode==='shared'?orders:baskets;
  const fr=D.scenario.freight[mode],hd=D.scenario.handling[mode];
  const priceFactor=clamp(cfg.price??1,.7,1.4),costFactor=clamp(cfg.cost??1,.5,3),laborFactor=clamp(cfg.labor??1,.3,3),wait=clamp(cfg.wait??0,0,240);
  const fare=clamp(cfg.fare??(mode==='shared'?57:137.5),0,mode==='shared'?1000:5000);
  const b=D.scenario.basket;
  const retail=money(b.reduce((v,r)=>v+r.qty*r.retail_unit,0));
  const goods=money(b.reduce((v,r)=>v+r.qty*money(r.wholesale_unit*Number(sup.price_factor)*priceFactor),0));
  const kg=b.reduce((v,r)=>v+r.qty*r.kg,0)*count;
  const m3=b.reduce((v,r)=>v+r.qty*r.m3,0)*count;
  const factor=(x)=>x*laborFactor;
  const comp={
    'Carga fija':money(factor(hd.loading_fixed)),
    'Carga por kg':money(factor(hd.loading_per_kg)*kg),
    'Descarga por paradas':money(factor(hd.unloading_fixed_per_stop)*hd.stops),
    'Descarga por kg':money(factor(hd.unloading_per_kg)*kg),
    'Esperas':money((hd.waiting_minutes+wait)*factor(hd.waiting_per_minute))
  };
  const handling=money(Object.values(comp).reduce((a,c)=>a+c,0));
  const drive=money((fr.base_trip_operating_cost+sup.pickup_extra_mxn)*costFactor);
  const cost=money(drive+handling);
  const revenue=money(mode==='shared'?fare*orders:fare);
  const target=money(cost*(1+fr.target_markup_on_cost));
  const extra=mode==='shared'?money(fr.receiving_per_trip_basket+fr.buyer_time_per_trip_basket):money(fr.receiving_per_trip+fr.buyer_time_per_trip);
  const baseline=money(retail*baskets),totalGoods=money(goods*baskets);
  const saving=money(baseline-totalGoods-fare-extra);
  const contribution=money(revenue-cost);
  const eligible=count>=sup.min_baskets&&count<=sup.max_baskets;
  const capacity=kg<=fr.vehicle_capacity_kg&&m3<=fr.vehicle_capacity_m3&&(mode==='private'||orders<=fr.max_orders);
  const viable=eligible&&capacity&&saving>0&&contribution>=0&&revenue>=target;
  return {mode,orders,baskets,count,supplier:sup,retail,goods,baseline,totalGoods,
     saving,contribution,cost,handling,comp,drive,revenue,target,shortfall:money(Math.max(0,target-revenue)),
     kg:money(kg),m3:Math.round(m3*10000)/10000,extra,fare,eligible,capacity,viable,
     data_class:'SYNTHETIC_ONLY',real_transaction_authorized:false};
}
const STRESS=[
 {id:'BASE',label:'Base',show:1,fuel:1,labor:1,wait:0,stock:1,price:0},
 {id:'DEMANDA',label:'Demanda baja',show:.7,fuel:1,labor:1,wait:0,stock:1,price:0},
 {id:'COMBUSTIBLE',label:'Combustible +35%',show:1,fuel:1.35,labor:1,wait:0,stock:1,price:0},
 {id:'COMPUESTO',label:'Estrés combinado',show:.72,fuel:1.30,labor:1.35,wait:25,stock:.78,price:.04}
];
function monte(cfg,trials=600,seed=20261030){
 const n=Math.trunc(clamp(trials,100,2000)); const result=[];
 for(let ci=0;ci<STRESS.length;ci++){
    const st=STRESS[ci],next=rnd((Number(seed)^((ci+1)*0x9e3779b9))>>>0);
    let ok=0,sumBuyer=0,sumCarrier=0,stockOut=0,cancelled=0;
    for(let t=0;t<n;t++){
      const assigned=Math.trunc(clamp(cfg.orders??12,1,12));
      let occ=0;
      for(let i=0;i<assigned;i++) if(next()<.85*st.show)occ++;
      for(let i=occ;i>0;i--)if(next()<.075)occ--;
      occ=Math.max(0,occ);if(!occ)cancelled++;
      const stock=next()<.96*st.stock;if(!stock)stockOut++;
      const extraWait=next()*30+st.wait;
      const localCfg={...cfg,mode:'shared',orders:Math.max(1,occ),
         price:clamp((cfg.price??1)*(.96+next()*.08+st.price),.7,1.4),
         cost:clamp((cfg.cost??1)*(.88+next()*.32)*st.fuel,.5,3),
         labor:clamp((cfg.labor??1)*(.90+next()*.50)*st.labor,.3,3),
         wait:clamp((cfg.wait??0)+extraWait,0,240)};
      const r=calc(localCfg);
      const localPrice=money(r.retail*(.97+next()*.06));
      const buyer=money(localPrice-r.goods-r.fare-r.extra);
      const rev=occ*r.fare;
      const carrier=money(rev-r.cost);
      const capacity=occ>0&&r.capacity;
      const incident=next()<.025;
      const good=stock&&!incident&&capacity&&r.eligible&&buyer>0&&carrier>=0&&rev>=r.target;
      if(good)ok++;
      sumBuyer+=buyer;sumCarrier+=carrier;
    }
    result.push({id:st.id,label:st.label,viability_rate_under_assumptions:money(100*ok/n),
       avg_buyer_mxn:money(sumBuyer/n),avg_carrier_mxn:money(sumCarrier/n),
       stock_out_draws:stockOut,zero_order_draws:cancelled,trials:n,classification:'SYNTHETIC_ONLY'});
 }
 return {rows:result,draws:n*STRESS.length,seed,scope:'BROWSER_SYNTHETIC_MONTE_CARLO',real_probability:false};
}
const LEVERS=[
 {id:'PUNTO_UNICO',name:'Consolidar entrega'},
 {id:'CITA_CARGA',name:'Carga con cita'},
 {id:'PRECARGA',name:'Preclasificar carga'},
 {id:'TARIFA_77',name:'Negociar tarifa $77'},
 {id:'DESCUENTO_2',name:'Descuento 2%'}
];
function creative(cfg){
 const results=[];
 for(let bits=0;bits<32;bits++){
   const chosen=LEVERS.filter((x,i)=>bits&(1<<i));
   const local={...cfg,mode:'shared',orders:Math.trunc(clamp(cfg.orders??12,1,12))};
   const sc=structuredClone(D.scenario);
   if(bits&1) sc.handling.shared.stops=1;
   if(bits&2) sc.handling.shared.waiting_minutes=0;
   if(bits&4) sc.handling.shared.loading_fixed=20;
   if(bits&8) local.fare=77;
   if(bits&16) local.price=clamp((cfg.price??1)*.98,.7,1.4);
   // calc() utiliza D como fuente: sustituir únicamente durante el cálculo en esta función pura.
   const result=calcWithScenario(local,sc);
   results.push({id:bits,changes:chosen.map(x=>x.name),...result,
       evidence:'HYPOTHESIS_ONLY',authorization:false});
 }
 for(const a of results) a.nondominated=!results.some(b=>b!==a&&b.saving>=a.saving&&b.contribution>=a.contribution&&b.changes.length<=a.changes.length&&
 (b.saving>a.saving||b.contribution>a.contribution||b.changes.length<a.changes.length));
 results.sort((a,b)=>Number(b.viable)-Number(a.viable)||Number(b.nondominated)-Number(a.nondominated)||a.changes.length-b.changes.length||b.saving-a.saving||b.contribution-a.contribution);
 return {count:results.length,pareto:results.filter(r=>r.nondominated).length,top:results.slice(0,7),approval:'HOLD',data_class:'SYNTHETIC_ONLY'};
}
function calcWithScenario(cfg,sc){
 const old=D.scenario;
 // Evita reemplazar el escenario global: fórmula equivalente explícita para las 5 palancas.
 const r=calc(cfg);const h0=old.handling.shared, h1=sc.handling.shared;
 const kg=r.kg,labor=clamp(cfg.labor??1,.3,3),wait=clamp(cfg.wait??0,0,240);
 const delta=money(money((h1.loading_fixed-h0.loading_fixed)*labor)+
   money((h1.stops-h0.stops)*h0.unloading_fixed_per_stop*labor)+
   money((h1.waiting_minutes-h0.waiting_minutes)*h0.waiting_per_minute*labor));
 const cost=money(r.cost+delta), contribution=money(r.revenue-cost),target=money(cost*1.2);
 return {...r,cost,contribution,target,shortfall:money(Math.max(0,target-r.revenue)),
    viable:r.eligible&&r.capacity&&r.saving>0&&contribution>=0&&r.revenue>=target};
}
const $$=id=>document.getElementById(id);
function uiState(){return {supplier:$$('supplier').value,mode:$$('mode').value,
 orders:Math.trunc(clamp($$('orders').value,1,12)),baskets:Math.trunc(clamp($$('baskets').value,1,5)),
 fare:clamp($$('fare').value,0,5000),price:clamp($$('price').value,.7,1.4),
 cost:clamp($$('cost').value,.5,3),labor:clamp($$('labor').value,.3,3),wait:clamp($$('waiting').value,0,240),
 seed:Math.trunc(clamp($$('seed').value,0,4294967295)),trials:Math.trunc(clamp($$('trials').value,100,2000))};}
function cell(row,value){const td=document.createElement('td');td.textContent=value;row.appendChild(td);return td;}
function row(k,v,important=false){const d=document.createElement('div');d.className='cost-row'+(important?' important':'');
 const a=document.createElement('span'),b=document.createElement('strong');a.textContent=k;b.textContent=v;d.append(a,b);return d;}
function renderBasket(){const t=$$('basket');t.replaceChildren();
 for(const it of D.scenario.basket){const tr=document.createElement('tr');
  const label=it.sku.replace(/_/g,' ').replace(/(\d+)KG\b/g,'$1 kg').replace(/(\d+)G\b/g,'$1 g');
  [label,it.qty,peso(it.retail_unit),peso(it.wholesale_unit)].forEach(x=>cell(tr,x));t.appendChild(tr);}}
function renderQuote(cfg){const tbody=$$('suppliers');tbody.replaceChildren();const needed=cfg.mode==='shared'?cfg.orders:cfg.baskets;
 for(const sup of suppliers){const tr=document.createElement('tr');
  const price=money(D.scenario.basket.reduce((acc,r)=>acc+r.qty*money(r.wholesale_unit*Number(sup.price_factor)*cfg.price),0));
  const eligible=needed>=sup.min_baskets&&needed<=sup.max_baskets;
  [sup.name,peso(price),sup.min_baskets,eligible?'Elegible*':'No cumple MOQ/stock'].forEach((x,i)=>{
     const td=cell(tr,x);if(i===3)td.className=eligible?'positive':'negative';});tbody.appendChild(tr);}}
let lastMC=null;
function render(){const cfg=uiState(),r=calc(cfg);
 $$('buyer-saving').textContent=peso(r.saving);$$('buyer-saving').className=r.saving>0?'positive':'negative';
 $$('buyer-detail').textContent=cfg.mode==='shared'?'por cesta':'por viaje privado';
 $$('carrier-profit').textContent=peso(r.contribution);$$('carrier-profit').className=r.contribution>=0?'positive':'negative';
 $$('shortfall').textContent=peso(r.shortfall);$$('shortfall').className=r.shortfall>0?'negative':'positive';
 $$('eco-state').textContent=r.viable?'VIABLE*':'HOLD';$$('eco-state').className='status-value '+(r.viable?'positive':'neutral');
 $$('main-verdict').textContent='HOLD';$$('supplier-gate').textContent=r.eligible?'MOQ / STOCK OK*':'MOQ / STOCK NO';$$('supplier-gate').className='tag '+(r.eligible?'good':'bad');
 const rows=[['Referencia local',peso(r.baseline)],['Costo mercancía',peso(r.totalGoods)],
  ['Tarifa al comprador',peso(r.fare)],['Recepción y tiempo comprador',peso(r.extra)],
  ['Ahorro neto comprador',peso(r.saving)],['Conducción + recogida',peso(r.drive)],
  ...Object.entries(r.comp).map(([k,v])=>[k,peso(v)]),
  ['Costo operativo del fletero',peso(r.cost)],['Facturación del viaje',peso(r.revenue)],
  ['Meta ingreso fletero (20%)',peso(r.target)],['Carga total',r.kg+' kg / '+r.m3+' m³']];
 const cost=$$('cost-rows');cost.replaceChildren();for(const [k,v] of rows)cost.appendChild(row(k,v,/Ahorro neto|Costo operativo|Facturación/.test(k)));
 renderQuote(cfg);renderCreative(cfg);return r;
}
function renderCreative(cfg){const obj=creative(cfg);$$('creative-count').textContent=`${obj.count} combinaciones`;
 const container=$$('creative-results');container.replaceChildren();
 for(const item of obj.top){const box=document.createElement('div');box.className='candidate';
  const top=document.createElement('div');top.className='candidate-top';
  const name=document.createElement('span');name.textContent=item.changes.join(' + ')||'Sin cambios';
  const status=document.createElement('span');status.textContent=item.viable?'VIABLE*':'HOLD';status.className=item.viable?'positive':'negative';top.append(name,status);
  const m=document.createElement('div');m.className='candidate-meta';m.textContent=`Comprador ${peso(item.saving)} · Fletero ${peso(item.contribution)}`;
  const note=document.createElement('div');note.className='candidate-desc';note.textContent='HIPÓTESIS · no evidencia real';box.append(top,m,note);container.appendChild(box);
 }}
function renderMC(m){lastMC=m;$$('mc-samples').textContent=`${m.draws.toLocaleString('es-MX')} muestras`;
 const div=$$('monte-chart');div.replaceChildren();for(const x of m.rows){const block=document.createElement('div');
  const top=document.createElement('div');top.className='bar-head';const a=document.createElement('span');a.textContent=x.label;
  const b=document.createElement('strong');b.textContent=x.viability_rate_under_assumptions+'%';top.append(a,b);
  const track=document.createElement('div');track.className='bar-track';const fill=document.createElement('div');fill.className='bar-fill';fill.style.width=x.viability_rate_under_assumptions+'%';track.appendChild(fill);
  const note=document.createElement('div');note.className='bar-note';note.textContent=`Promedio comprador ${peso(x.avg_buyer_mxn)} · fletero ${peso(x.avg_carrier_mxn)}`;
  block.append(top,track,note);div.appendChild(block);}}
function renderMatrix(){const canvas=$$('matrix'),ctx=canvas.getContext('2d');if(!ctx)return;
 const names=D.vertices,idx=new Map(names.map((x,i)=>[x,i])); const n=names.length,size=canvas.width,cw=size/n;
 ctx.clearRect(0,0,size,size);ctx.fillStyle='#152a38';ctx.fillRect(0,0,size,size);
 for(let i=0;i<n;i++)for(let j=0;j<n;j++){ctx.fillStyle=i===j?'#345160':'#152b3a';ctx.fillRect(j*cw+1,i*cw+1,cw-2,cw-2);}
 for(const edge of D.edges){const i=idx.get(edge.from),j=idx.get(edge.to);
   if(i===undefined||j===undefined)continue;ctx.fillStyle='#5ff3d0';ctx.fillRect(j*cw+1,i*cw+1,cw-2,cw-2);}}
function renderGuards(){const rows=[['Precios y existencias reales','NO VERIFICADOS'],['Gastos y rutas reales','NO VERIFICADOS'],
 ['Cotización aprobada externamente','NO'],['Agentes IA independientes','NO IMPLEMENTADOS'],
 ['Autorización transacción','DENY'],['Promoción automática','DENY'],
 ['Readback histórico motor Python','VERIFICABLE POR CLI']];
 const t=$$('guard-list');t.replaceChildren();for(const [a,b] of rows){const div=document.createElement('div');div.className='guard-item';
  const c=document.createElement('span');c.textContent=a;const d=document.createElement('strong');d.textContent=b;div.append(c,d);t.appendChild(div);}}
function download(payload,name){const data=new Blob([JSON.stringify(payload,null,2)+'\n'],{type:'application/json'});
 const url=URL.createObjectURL(data),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();URL.revokeObjectURL(url);}
function initialize(){if(typeof document==='undefined')return;
 renderBasket();renderGuards();renderMatrix();
 document.querySelectorAll('input,select').forEach(el=>el.addEventListener('change',()=>{
    if(el.id==='mode'){const privateMode=el.value==='private';$$('orders-field').hidden=privateMode;$$('baskets-field').hidden=!privateMode;
       $$('fare').value=privateMode?'137.50':'57';}
    render();}));
 $$('reset').addEventListener('click',()=>{for(const [id,val] of Object.entries({supplier:'ALFA',mode:'shared',orders:12,baskets:2,fare:57,price:1,cost:1,labor:1,waiting:0,seed:20261030,trials:600}))$$(id).value=val;
    $$('orders-field').hidden=false;$$('baskets-field').hidden=true;lastMC=null;$$('monte-chart').replaceChildren();$$('mc-samples').textContent='Sin ejecutar';render();});
 $$('run-mc').addEventListener('click',()=>{const c=uiState();renderMC(monte(c,c.trials,c.seed));});
 $$('export').addEventListener('click',()=>{const c=uiState();download({schema:'RIO_BROWSER_DEMO_R003',classification:'SYNTHETIC_ONLY',inputs:c,
   economic:calc(c), creative:creative(c), monte_carlo:lastMC,
   gates:{verified_external_data:false,real_transaction_authorized:false,production:false,real_quote:false},
   note:'Reporte generado en navegador; no sustituye el readback byte-exacto del motor Python.'},'rio-demo-sintetica-r003.json');});
 $$('download-audit').addEventListener('click',()=>download({schema:'RIO_BROWSER_AUDIT_R003',data_class:'SYNTHETIC_ONLY',
   user_instruction_scope:'CONTRATO_PROGRAMACION_R003_NO_NATIVE_CHAT_BYTES',
   proven_data:false,real_payments:false,real_freight_dispatch:false,independent_AI_active:false,
   historical_round_python_replay:'NOT_EXECUTED_IN_BROWSER',
   browser_scenario:calc(uiState()),github_published:'NOT_VERIFIED'},'rio-auditoria-r003.json'));
 render();}
globalThis.RIO_ENGINE={calc,monte,creative,STRESS,LEVERS};
initialize();
})();
