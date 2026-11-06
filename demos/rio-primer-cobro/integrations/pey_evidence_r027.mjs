/**
 * RÍO Primer Cobro R027 — conservative provider contract reconciliation.
 * NOT a Pey client, a CoDi client, or a payment processor. No network calls.
 * Untrusted provider claims can NEVER independently confirm bank settlement.
 */
export const SCHEMA="RIO_R027_PROVIDER_EVIDENCE_V1";
export const RELEASE_MODE="DEMO_ONLY_NO_BANK";
const CLAIMS=Object.freeze([
  Object.freeze({provider:"PEY_CANDIDATE",field:"qrRoute",value:"POST /codi/qr",authority:"HISTORICAL_USER_CONTEXT_UNVERIFIED"}),
  Object.freeze({provider:"PEY_CANDIDATE",field:"authScheme",value:"Bearer",authority:"HISTORICAL_USER_CONTEXT_UNVERIFIED"}),
  Object.freeze({provider:"PEY_CANDIDATE",field:"webhookSignature",value:"UNKNOWN",authority:"UNKNOWN"}),
  Object.freeze({provider:"PEY_CANDIDATE",field:"bankAccountRoute",value:"POST /bank-account",authority:"HISTORICAL_USER_CONTEXT_UNVERIFIED"}),
  Object.freeze({provider:"PEY_CANDIDATE",field:"minimumQrValidity",value:"6 minutes (historical claim)",authority:"HISTORICAL_USER_CONTEXT_UNVERIFIED"}),
  Object.freeze({provider:"PEY_CANDIDATE",field:"sandbox",value:"NOT_OBSERVED",authority:"UNKNOWN"}),
  Object.freeze({provider:"THIRD_PARTY_CODI_API",field:"qrRoute",value:"POST /v2/codi/qr",authority:"THIRD_PARTY_SOURCE_REVIEWED"}),
  Object.freeze({provider:"THIRD_PARTY_CODI_API",field:"authScheme",value:"x-api-key",authority:"THIRD_PARTY_SOURCE_REVIEWED"}),
  Object.freeze({provider:"THIRD_PARTY_CODI_API",field:"bankAccountRoute",value:"NOT_DOCUMENTED_IN_REVIEWED_SOURCE",authority:"UNKNOWN"}),
  Object.freeze({provider:"THIRD_PARTY_CODI_API",field:"webhookSignature",value:"BANXICO_SIGNATURE_VALIDATION_CODE_PRESENT",authority:"THIRD_PARTY_SOURCE_REVIEWED"})
]);
const SIGNALS=new Set(["QR_RENDERED","PAYMENT_LINK_DISPLAYED","WEBHOOK_REPORTED",
  "WEBHOOK_SIGNATURE_CLAIMED","BANK_ABONO_CLAIMED","BANK_SETTLEMENT_CLAIMED",
  "SIMULATED_CONFIRMATION","DUPLICATE_EVENT","PROVIDER_RESPONSE_REPORTED"]);
function reject(x){throw new TypeError(x);}
function plain(v,keys){
  if(v===null||typeof v!=="object"||Array.isArray(v)||
    (Object.getPrototypeOf(v)!==Object.prototype&&Object.getPrototypeOf(v)!==null))reject("PLAIN_OBJECT_REQUIRED");
  if(Object.keys(v).some(k=>!keys.includes(k)))reject("UNRECOGNIZED_OR_SENSITIVE_FIELD");
}
function text(v,max=128){if(typeof v!=="string"||v.length===0||v.length>max||/[\u0000-\u001f]/.test(v))reject("TEXT_INVALID");}
export function providerEvidenceMatrix(){
  return {schema:SCHEMA,mode:RELEASE_MODE,claims:CLAIMS.map(x=>({...x})),
    equivalence:"NOT_ESTABLISHED",officialPeyDocumentation:"NOT_VERIFIED",
    externalBankConnectivity:"NOT_OBSERVED",productionPaymentActivation:"BLOCKED"};
}
export function compareProviderContracts(){
  const a=CLAIMS.find(x=>x.provider==="PEY_CANDIDATE"&&x.field==="qrRoute");
  const b=CLAIMS.find(x=>x.provider==="THIRD_PARTY_CODI_API"&&x.field==="qrRoute");
  const x=CLAIMS.find(x=>x.provider==="PEY_CANDIDATE"&&x.field==="authScheme");
  const y=CLAIMS.find(x=>x.provider==="THIRD_PARTY_CODI_API"&&x.field==="authScheme");
  return {schema:SCHEMA,qrRoute:{peyCandidate:a.value,thirdParty:b.value,same:a.value===b.value},
    authScheme:{peyCandidate:x.value,thirdParty:y.value,same:x.value===y.value},
    compatibility:"UNVERIFIED_NOT_INTERCHANGEABLE",automaticFieldMapping:false,
    evidenceLimit:"CANDIDATE_VS_THIRD_PARTY_NOT_OFFICIAL_PEY",activation:"BLOCKED"};
}
/**
 * Only metadata here. Reject any free-text account, CLABE, person or callback bodies.
 * This is a policy guard; user-provided booleans cannot grant trusted-host authority.
 */
export function assessProductionEligibility(request={}){
  plain(request,["providerId","officialContractVerified","sandboxObserved",
    "merchantAuthorizationVerified","webhookVerificationObserved","settlementReconciliationObserved",
    "secretEnvironmentProtected","githubReleaseAuthorized"]);
  text(request.providerId);
  if(request.providerId!=="PEY_CANDIDATE" && request.providerId!=="THIRD_PARTY_CODI_API")reject("PROVIDER_ID_UNKNOWN");
  const checks=["officialContractVerified","sandboxObserved","merchantAuthorizationVerified",
    "webhookVerificationObserved","settlementReconciliationObserved","secretEnvironmentProtected",
    "githubReleaseAuthorized"];
  for(const key of checks)if(typeof request[key]!=="boolean")reject("CHECK_MISSING_OR_INVALID:"+key);
  const missing=checks.filter(k=>request[k]!==true);
  return {schema:SCHEMA,mode:RELEASE_MODE,providerId:request.providerId,
    checksReportedByCaller:checks.length,unverifiedChecks:missing,
    claimedReady:missing.length===0,authorization:"BLOCKED_UNTRUSTED_SELF_ATTESTATION",
    hostAttestation:"NOT_OBSERVED",enabled:false,mayCreateRealQr:false,
    mayRegisterBankAccount:false,mayReceiveFunds:false,
    paidStateAllowed:false};
}
/**
 * Does not parse payment details. All signals are classified as non-settling.
 * Trustworthy independent payment adjudication requires a different, authorized host.
 */
export function classifyUnverifiedPaymentSignal(signal){
  plain(signal,["kind","origin","referenceId","reportedAtMs"]);
  if(!SIGNALS.has(signal.kind))reject("SIGNAL_KIND_INVALID");
  if(!["SYNTHETIC_TEST","EXTERNAL_UNVERIFIED"].includes(signal.origin))reject("SIGNAL_ORIGIN_INVALID");
  text(signal.referenceId,64);
  if(!/^RIO[-_][a-zA-Z0-9_-]{1,60}$/.test(signal.referenceId))reject("UNSAFE_REFERENCE");
  if(!Number.isSafeInteger(signal.reportedAtMs)||signal.reportedAtMs<=0)reject("TIMESTAMP_INVALID");
  return {schema:SCHEMA,signalKind:signal.kind,evidence:"UNVERIFIED_NON_SETTLING",
    paymentState:"UNPAID_OR_UNKNOWN",bankSettlementConfirmed:false,
    realPaymentConfirmed:false,mayIssuePaidReceipt:false,
    disposition:signal.origin==="SYNTHETIC_TEST"?"DEMO_EVIDENCE_ONLY":"QUARANTINE_EXTERNAL_SIGNAL",
    providerSignatureVerified:false};
}
