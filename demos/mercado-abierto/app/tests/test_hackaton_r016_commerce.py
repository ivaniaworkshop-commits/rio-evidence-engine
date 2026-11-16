"""R016 actual gateway SQLite snapshot API: CAS, CSRF, tenant boundaries."""
import json
import pytest
from fastapi.testclient import TestClient
from rio_pey_codi.platform import Settings, create_platform


@pytest.fixture
def environment(tmp_path):
    app=create_platform(Settings(env="local",mode="DEMO",email_mode="memory",auto_create=True,
        database_url="sqlite+pysqlite:///"+str(tmp_path/"r016.sqlite"),
        public_url="http://testserver",origin="http://testserver"))
    with TestClient(app) as a, TestClient(app) as b:
        yield app,a,b


def sign_up(app,client,email):
    response=client.post("/v1/auth/signup",json={
        "email":email,"password":"Synthetic-Commercial-2026","business_name":"Comercio sintético"})
    assert response.status_code==201,response.text
    token=app.state.mailer.outbox[-1]["token"]
    assert client.post("/v1/auth/verify-email",json={"token":token}).status_code==200
    logged=client.post("/v1/auth/login",json={"email":email,"password":"Synthetic-Commercial-2026"})
    assert logged.status_code==200
    return logged.json()["csrf_token"]


def state(rfq="RFQ-1"):
    return {"schema":"RIO_MERCADO_DEMO_R001","version":1,"createdAt":"2026-11-10T00:00:00Z",
            "businesses":[{"id":"NEG-1","type":"minorista","name":"Demo"}],
            "products":[{"id":"SKU-1","name":"Arroz","price":27}],
            "rfqs":[{"id":rfq,"status":"abierta","buyer":"NEG-1"}],
            "offers":[],"orders":[],"freights":[],"sales":[],"events":[]}


def put(client,csrf,revision,body):
    return client.put("/api/hackaton/commercial-state",
        headers={"X-CSRF-Token":csrf},json={"revision":revision,"state":body})


def test_auth_and_csrf_fail_closed(environment):
    app,a,b=environment
    assert a.get("/api/hackaton/commercial-state").status_code==401
    assert put(a,"missing",0,state()).status_code==401
    csrf=sign_up(app,a,"r016-a@example.org")
    assert a.get("/api/hackaton/commercial-state").json()=={"revision":0,"state":None}
    assert a.put("/api/hackaton/commercial-state",json={"revision":0,"state":state()}).status_code==403
    assert put(a,"invalid-csrf",0,state()).status_code==403
    assert put(a,csrf,0,state()).status_code==200


def test_revision_and_cross_account_isolation(environment):
    app,a,b=environment
    csrf_a=sign_up(app,a,"r016-c@example.org")
    csrf_b=sign_up(app,b,"r016-d@example.org")
    first=put(a,csrf_a,0,state("RFQ-A"))
    assert first.status_code==200,first.text
    assert first.json()["revision"]==1
    assert len(first.json()["sha256"])==64
    assert b.get("/api/hackaton/commercial-state").json()=={"revision":0,"state":None}
    assert put(b,csrf_b,0,state("RFQ-B")).status_code==200
    assert put(a,csrf_a,0,state("RFQ-STALE")).status_code==409
    assert put(a,csrf_b,1,state("RFQ-CROSS")).status_code==403
    assert put(a,csrf_a,1,state("RFQ-A2")).json()["revision"]==2
    assert a.get("/api/hackaton/commercial-state").json()["state"]["rfqs"][0]["id"]=="RFQ-A2"
    assert b.get("/api/hackaton/commercial-state").json()["state"]["rfqs"][0]["id"]=="RFQ-B"


def test_invalid_duplicate_oversized_payload(environment):
    app,a,_=environment
    csrf=sign_up(app,a,"r016-e@example.org")
    assert put(a,csrf,0,{"schema":"other"}).status_code==422
    duplicate=b'{"revision":0,"revision":0,"state":{}}'
    response=a.put("/api/hackaton/commercial-state",content=duplicate,
        headers={"X-CSRF-Token":csrf,"Content-Type":"application/json"})
    assert response.status_code==422
    large=b' '*(1024*1024+1)
    result=a.put("/api/hackaton/commercial-state",content=large,
        headers={"X-CSRF-Token":csrf,"Content-Type":"application/json"})
    assert result.status_code==413
    corrupted=state()
    corrupted["rfqs"]=[{"id":"duplicate"},{"id":"duplicate"}]
    assert put(a,csrf,0,corrupted).status_code==422
    assert a.get("/api/hackaton/commercial-state").json()["revision"]==0
    nonfinite=state()
    nonfinite["products"][0]["price"]=float("inf")
    invalid_json=json.dumps({"revision":0,"state":nonfinite}).encode()
    assert a.put("/api/hackaton/commercial-state",content=invalid_json,
        headers={"X-CSRF-Token":csrf,"Content-Type":"application/json"}).status_code==422
    nested=state()
    deep={}
    cursor=deep
    for _ in range(26):
        cursor["child"]={}
        cursor=cursor["child"]
    nested["events"].append({"id":"EV-DEEP","detail":deep})
    assert put(a,csrf,0,nested).status_code==422
    assert a.get("/api/hackaton/commercial-state").json()["revision"]==0


def test_revocation_prevents_read_write(environment):
    app,a,_=environment
    csrf=sign_up(app,a,"r016-f@example.org")
    assert put(a,csrf,0,state()).status_code==200
    assert a.post("/api/auth/logout",headers={"X-CSRF-Token":csrf},json={}).status_code==200
    assert a.get("/api/hackaton/commercial-state").status_code==401
    assert put(a,csrf,1,state("RFQ-OTHER")).status_code==401
