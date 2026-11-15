import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const Field=require('../app/field_r015.js');
for(const t of Field.selfTests())test(t.name,()=>assert.equal(t.pass,true,t.error));
test('No se registra información bancaria en el informe',()=>{const mem={getItem:()=>null};const output=Field.report(mem,'boot',{viewport_width_css:390});assert.equal(output.financial_payment,'NO');assert.equal(output.physical_device,'NOT_INDEPENDENTLY_VERIFIED')});
test('No se admite elevar QR de práctica a pago real',()=>{let raw=null;const s={getItem:()=>raw,setItem(k,v){raw=v}};assert.throws(()=>Field.begin(s,'test-boot',{saleId:'DEMO-1',method:'qr',totalCents:200,state:'DIGITAL_DEMO_PENDING',realPaymentConfirmed:true}));assert.equal(raw,null)});
