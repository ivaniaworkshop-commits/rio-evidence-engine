/**
 * R026: PEY_EMULATED_ONLY. Pure offline contract, never a bank or provider adapter.
 * No network, no CLABE, no customer data, no payment confirmation.
 */
import {createHash, createHmac, timingSafeEqual} from "node:crypto";

export const CONTRACT = "RIO_PEY_EMULATED_R026_V1";
export const MODE = "DEMO_ONLY_NO_BANK";
export const DEMO_ACCOUNT = Object.freeze({type:"DemoAccount",id:"demo-account-001"});

function fail(reason){throw new TypeError(reason);}
function obj(value,keys){
  if(!value || typeof value!=="object" || Array.isArray(value) ||
     (Object.getPrototypeOf(value)!==Object.prototype && Object.getPrototypeOf(value)!==null))fail("OBJECT_REQUIRED");
  for(const key of Object.keys(value))if(!keys.includes(key))fail("UNRECOGNIZED_OR_SENSITIVE_FIELD");
}
function str(value,pattern,name){if(typeof value!=="string"||!pattern.test(value))fail(name+"_INVALID");}
function integer(value,min,max,name){if(!Number.isSafeInteger(value)||value<min||value>max)fail(name+"_INVALID");}
function digest(value){return createHash("sha256").update(value,"utf8").digest("hex");}
function canonical(event){
  return JSON.stringify([event.eventId,event.intentId,event.type,event.amountCents,event.occurredAtMs]);
}
export function signSyntheticEvent(event,syntheticSecret){
  obj(event,["eventId","intentId","type","amountCents","occurredAtMs"]);
  if(typeof syntheticSecret!=="string"||syntheticSecret.length<24||syntheticSecret.length>128)fail("DEMO_SECRET_INVALID");
  return createHmac("sha256",syntheticSecret).update(canonical(event),"utf8").digest("hex");
}
export function createDemoIntent({saleId,amountCents,createdAtMs,expiresAtMs,account}={}){
  str(saleId,/^[A-Za-z0-9_-]{1,64}$/,"SALE_ID");
  integer(amountCents,1,100000000,"AMOUNT_CENTS");
  integer(createdAtMs,1,8640000000000000,"CREATED_AT");
  integer(expiresAtMs,1,8640000000000000,"EXPIRES_AT");
  if(expiresAtMs<=createdAtMs||expiresAtMs-createdAtMs>86400000)fail("EXPIRY_WINDOW_INVALID");
  obj(account,["type","id"]);
  if(account.type!==DEMO_ACCOUNT.type||account.id!==DEMO_ACCOUNT.id)fail("REAL_ACCOUNT_FORBIDDEN");
  const id="demo_"+digest(JSON.stringify([saleId,amountCents,createdAtMs])).slice(0,24);
  return {
    schema:CONTRACT,mode:MODE,provider:"PEY_EMULATED_UNVERIFIED",
    id,saleId,currency:"MXN",amountCents,createdAtMs,expiresAtMs,
    account:{type:DEMO_ACCOUNT.type,id:DEMO_ACCOUNT.id},
    status:"DEMO_PENDING",realPaymentConfirmed:false,
    bankSettlementConfirmed:false,externalTransferExecuted:false,
    qrPayload:"RIO-PEY-SIM|NO-PAGABLE|"+id+"|CENTAVOS="+amountCents,
    eventHashes:{},events:[],
  };
}
export function applySyntheticEvent(intent,event,signature,syntheticSecret,nowMs){
  obj(intent,["schema","mode","provider","id","saleId","currency","amountCents","createdAtMs",
      "expiresAtMs","account","status","realPaymentConfirmed","bankSettlementConfirmed",
      "externalTransferExecuted","qrPayload","eventHashes","events"]);
  if(intent.schema!==CONTRACT||intent.mode!==MODE||intent.realPaymentConfirmed!==false||
     intent.bankSettlementConfirmed!==false||intent.externalTransferExecuted!==false)fail("NON_DEMO_INTENT_FORBIDDEN");
  obj(intent.account,["type","id"]);
  if(intent.account.type!==DEMO_ACCOUNT.type||intent.account.id!==DEMO_ACCOUNT.id)fail("REAL_ACCOUNT_FORBIDDEN");
  obj(event,["eventId","intentId","type","amountCents","occurredAtMs"]);
  str(event.eventId,/^[a-zA-Z0-9_-]{1,48}$/,"EVENT_ID");
  if(event.intentId!==intent.id)fail("WRONG_INTENT");
  if(!["DEMO_CONFIRMED","DEMO_CANCELLED"].includes(event.type))fail("INVALID_DEMO_EVENT");
  integer(event.amountCents,1,100000000,"AMOUNT_CENTS");
  if(event.amountCents!==intent.amountCents)fail("AMOUNT_MISMATCH");
  integer(event.occurredAtMs,1,8640000000000000,"OCCURRED_AT");
  integer(nowMs,1,8640000000000000,"NOW");
  if(event.occurredAtMs<intent.createdAtMs||event.occurredAtMs>nowMs)fail("BAD_EVENT_TIME");
  str(signature,/^[0-9a-f]{64}$/,"SIGNATURE");
  const computed=signSyntheticEvent(event,syntheticSecret);
  if(!timingSafeEqual(Buffer.from(computed,"hex"),Buffer.from(signature,"hex")))fail("INVALID_DEMO_SIGNATURE");
  obj(intent.eventHashes,Object.keys(intent.eventHashes));
  if(!Array.isArray(intent.events)||intent.events.length>100)fail("EVENT_LEDGER_INVALID");
  const eventHash=digest(canonical(event));
  if(Object.prototype.hasOwnProperty.call(intent.eventHashes,event.eventId)){
    if(intent.eventHashes[event.eventId]!==eventHash)fail("CONFLICTING_EVENT_ID");
    return {intent,disposition:"DUPLICATE_NOOP"};
  }
  if(intent.status!=="DEMO_PENDING")fail("FINAL_STATE_TRANSITION_FORBIDDEN");
  if(event.occurredAtMs>intent.expiresAtMs||nowMs>intent.expiresAtMs)fail("DEMO_INTENT_EXPIRED");
  if(intent.events.length>=100)fail("EVENT_LIMIT_REACHED");
  const next={
    ...intent,eventHashes:{...intent.eventHashes,[event.eventId]:eventHash},
    events:[...intent.events,{id:event.eventId,kind:event.type,occurredAtMs:event.occurredAtMs}],
    status:event.type==="DEMO_CONFIRMED"?"DEMO_SIMULATED_CONFIRMED":"DEMO_CANCELLED",
    realPaymentConfirmed:false,bankSettlementConfirmed:false,externalTransferExecuted:false
  };
  return {intent:next,disposition:"APPLIED_SIMULATION_ONLY"};
}
