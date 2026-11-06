import test from "node:test";
import assert from "node:assert/strict";
import {CONTRACT,MODE,DEMO_ACCOUNT,createDemoIntent,applySyntheticEvent,signSyntheticEvent} from "../integrations/pey_emulated_r026.mjs";

const time=1800000000000, secret="THIS_IS_SYNTHETIC_TEST_ONLY_R026_SECRET";
function fixture(opts={}){
 const i={saleId:"RIO_R026_SALE_1",amountCents:1,createdAtMs:time,expiresAtMs:time+3600000,account:DEMO_ACCOUNT,...opts};
 return createDemoIntent(i);
}
function event(i,opts={}){return {eventId:"demo_evt_001",intentId:i.id,type:"DEMO_CONFIRMED",amountCents:i.amountCents,occurredAtMs:time+3000,...opts};}
const apply=(i,e,t=time+4000)=>applySyntheticEvent(i,e,signSyntheticEvent(e,secret),secret,t);
test("contract is explicitly emulated only",()=>{const i=fixture();assert.equal(i.schema,CONTRACT);assert.equal(i.mode,MODE);assert.match(i.qrPayload,/NO-PAGABLE/);assert.equal(i.realPaymentConfirmed,false);});
test("one cent remains exact integer",()=>assert.equal(fixture().amountCents,1));
test("two intents with same input are deterministic",()=>assert.equal(fixture().id,fixture().id));
test("different amount changes intent identity",()=>assert.notEqual(fixture().id,fixture({amountCents:2}).id));
test("not a real account",()=>assert.deepEqual(fixture().account,DEMO_ACCOUNT));
test("CLABE and other extra account keys rejected",()=>assert.throws(()=>fixture({account:{...DEMO_ACCOUNT,clabe:"INVALID_FIXTURE"}}),/UNRECOGNIZED/));
test("real account type forbidden",()=>assert.throws(()=>fixture({account:{type:"BankAccount",id:"x"}}),/REAL_ACCOUNT/));
test("top-level CLABE field rejected rather than silently ignored",()=>assert.throws(()=>fixture({clabe:"INVALID_FIXTURE"}),/UNRECOGNIZED/));
test("sale reference must have RIO namespace",()=>assert.throws(()=>fixture({saleId:"123456789012345678"}),/SALE_ID/));
test("amount is positive integer",()=>{for(const n of [0,-1,1.2,NaN,Infinity,9007199254740993])assert.throws(()=>fixture({amountCents:n}),/AMOUNT_CENTS/);});
test("expiry must be after creation",()=>assert.throws(()=>fixture({expiresAtMs:time}),/EXPIRY/));
test("expiry longer than a day rejected",()=>assert.throws(()=>fixture({expiresAtMs:time+86400001}),/EXPIRY/));
test("simulated confirmation does not mark real payment",()=>{const i=fixture();const out=apply(i,event(i));assert.equal(out.intent.status,"DEMO_SIMULATED_CONFIRMED");assert.equal(out.disposition,"APPLIED_SIMULATION_ONLY");assert.equal(out.intent.realPaymentConfirmed,false);assert.equal(out.intent.bankSettlementConfirmed,false);});
test("cancelled demo stays non-bank",()=>{const i=fixture();const e=event(i,{type:"DEMO_CANCELLED"});assert.equal(apply(i,e).intent.status,"DEMO_CANCELLED");});
test("exact replay is idempotent",()=>{const i=fixture();const e=event(i);const a=apply(i,e);const b=apply(a.intent,e);assert.equal(b.disposition,"DUPLICATE_NOOP");assert.deepEqual(b.intent,a.intent);});
test("same event id different payload is rejected",()=>{const i=fixture();const e=event(i);const a=apply(i,e).intent;assert.throws(()=>apply(a,event(i,{type:"DEMO_CANCELLED"})),/CONFLICTING_EVENT_ID/);});
test("signed event with modified amount rejected",()=>{const i=fixture();const e=event(i);const sig=signSyntheticEvent(e,secret);assert.throws(()=>applySyntheticEvent(i,{...e,amountCents:2},sig,secret,time+4000),/AMOUNT_MISMATCH/);});
test("wrong synthetic signature rejected",()=>{const i=fixture();const e=event(i);assert.throws(()=>applySyntheticEvent(i,e,"0".repeat(64),secret,time+4000),/INVALID_DEMO_SIGNATURE/);});
test("wrong intent reference rejected",()=>{const i=fixture();assert.throws(()=>apply(i,event(i,{intentId:"not-this-intent"})),/WRONG_INTENT/);});
test("unknown event type rejected",()=>{const i=fixture();const e=event(i,{type:"BANK_SETTLED"});assert.throws(()=>apply(i,e),/INVALID_DEMO_EVENT/);});
test("future event rejected",()=>{const i=fixture();const e=event(i,{occurredAtMs:time+10000});assert.throws(()=>apply(i,e,time+4000),/BAD_EVENT_TIME/);});
test("expired event rejected",()=>{const i=fixture();const e=event(i,{occurredAtMs:time+3600001});assert.throws(()=>apply(i,e,time+3600001),/EXPIRED/);});
test("final state cannot accept a second new event",()=>{const i=fixture();const a=apply(i,event(i)).intent;assert.throws(()=>apply(a,event(i,{eventId:"new_id"})),/FINAL_STATE/);});
test("event cannot inject CLABE",()=>{const i=fixture();const e={...event(i),clabe:"INVALID_FIXTURE"};assert.throws(()=>apply(i,e),/UNRECOGNIZED/);});
test("event signing cannot inject bank identifiers",()=>{const i=fixture();assert.throws(()=>signSyntheticEvent({...event(i),bankAccount:"x"},secret),/UNRECOGNIZED/);});
test("event signing rejects unsafe secret",()=>{const i=fixture();assert.throws(()=>signSyntheticEvent(event(i),"a"),/DEMO_SECRET/);});
