"""R014: real FastAPI AccountService with two independent synthetic sessions.

Local SQLite, in-memory mailer, DEMO only. Never handles live merchants or money.
"""
import pytest
from fastapi.testclient import TestClient
from rio_pey_codi.platform import Settings, create_platform


@pytest.fixture
def app(tmp_path):
    return create_platform(Settings(
        env="local", mode="DEMO",
        database_url="sqlite+pysqlite:///" + str(tmp_path / "r014.sqlite"),
        auto_create=True, email_mode="memory", public_url="http://testserver",
        origin="http://testserver",
    ))


def register(app, client, email, business):
    signup=client.post("/v1/auth/signup", json={
        "email":email,"password":"R014-Synthetic-Test-Password-2026",
        "business_name":business,
    })
    assert signup.status_code==201,signup.text
    token=app.state.mailer.outbox[-1]["token"]
    verify=client.post("/v1/auth/verify-email",json={"token":token})
    assert verify.status_code==200,verify.text
    login=client.post("/v1/auth/login",json={
        "email":email,"password":"R014-Synthetic-Test-Password-2026",
    })
    assert login.status_code==200,login.text
    return login.json()["csrf_token"]


def test_two_sessions_are_independent_and_tenant_scoped(app):
    with TestClient(app) as a, TestClient(app) as b:
        csrf_a=register(app,a,"r014-a@example.org","Negocio A")
        csrf_b=register(app,b,"r014-b@example.org","Negocio B")
        identity_a=a.get("/api/auth/me")
        identity_b=b.get("/api/auth/me")
        assert identity_a.status_code==identity_b.status_code==200
        user_a=identity_a.json()["user"]
        user_b=identity_b.json()["user"]
        assert user_a["id"]!=user_b["id"]
        assert user_a["email"]=="r014-a@example.org"
        assert user_b["email"]=="r014-b@example.org"
        merchants_a=a.get("/v1/merchants")
        merchants_b=b.get("/v1/merchants")
        assert merchants_a.status_code==merchants_b.status_code==200
        ids_a={x["id"] for x in merchants_a.json()["merchants"]}
        ids_b={x["id"] for x in merchants_b.json()["merchants"]}
        assert ids_a and ids_b and ids_a.isdisjoint(ids_b)
        assert identity_a.json()["csrf_token"]==csrf_a
        assert identity_b.json()["csrf_token"]==csrf_b
        assert csrf_a!=csrf_b


def test_cross_session_csrf_cannot_logout_another_user(app):
    with TestClient(app) as a, TestClient(app) as b:
        csrf_a=register(app,a,"r014-c@example.org","Negocio C")
        csrf_b=register(app,b,"r014-d@example.org","Negocio D")
        denied=a.post("/api/auth/logout",headers={"X-CSRF-Token":csrf_b},json={})
        assert denied.status_code==403
        assert a.get("/api/auth/me").status_code==200
        assert b.get("/api/auth/me").status_code==200
        success=a.post("/api/auth/logout",headers={"X-CSRF-Token":csrf_a},json={})
        assert success.status_code==200
        assert a.get("/api/auth/me").status_code==401
        assert a.get("/hackaton", follow_redirects=False).status_code==303
        assert b.get("/api/auth/me").status_code==200
        assert b.get("/hackaton").status_code==200


def test_no_r003_admin_privileges_for_either_session(app):
    with TestClient(app) as a, TestClient(app) as b:
        register(app,a,"r014-e@example.org","Negocio E")
        register(app,b,"r014-f@example.org","Negocio F")
        for client in (a,b):
            result=client.get("/api/auth/me")
            assert result.status_code==200
            assert result.json()["permissions"]==["account.manage"]
            assert result.json()["auth_source"]=="RIO_GATEWAY_RIO_SID"
            assert client.get("/api/admin/dashboard").status_code==403
            assert client.get("/api/admin/users").status_code==403
