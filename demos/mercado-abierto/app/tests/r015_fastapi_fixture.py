"""R015 browser fixture: genuine FastAPI app and AccountService, TEST-ONLY bootstrap.

Starts a local sqlite DEMO database and memory email outbox, binds 127.0.0.1 only.
Never expose this launcher to a public interface or deploy it to production.
"""
import argparse
import os
from pathlib import Path

import uvicorn
from fastapi import Header, HTTPException, Request
from rio_pey_codi.platform import Settings, create_platform


def make_test_app(db_file: Path, fixture_key: str, port: int):
    if not fixture_key or len(fixture_key) < 24:
        raise ValueError("A random fixture key of at least 24 characters is required")
    app = create_platform(Settings(
        env="local", mode="DEMO", live_enabled=False, database_url="sqlite+pysqlite:///" + str(db_file),
        auto_create=True, email_mode="memory", public_url=f"http://127.0.0.1:{port}",
        origin=f"http://127.0.0.1:{port}",
    ))

    @app.get("/__rio_r015/verification-token", include_in_schema=False)
    def fixture_token(x_rio_fixture_key: str = Header(default="")):
        if x_rio_fixture_key != fixture_key:
            raise HTTPException(status_code=403, detail="Fixture boundary")
        outbox = app.state.mailer.outbox
        if not outbox:
            raise HTTPException(status_code=404, detail="No synthetic mail")
        return {"token": outbox[-1]["token"]}

    @app.post("/__rio_r015/pin-owner", include_in_schema=False)
    def fixture_pin_owner(request: Request, x_rio_fixture_key: str = Header(default="")):
        # This loopback-only launcher can move its one pinned synthetic owner.
        # No roles or production routes are changed; ordinary sessions still
        # use the real AccountService checks and R003 stays denied.
        if x_rio_fixture_key != fixture_key:
            raise HTTPException(status_code=403, detail="Fixture boundary")
        principal = app.state.accounts.session(request)
        app.state.accounts.platform_owner_id = principal['id']
        return {"id": principal['id'], "can_access_market": app.state.accounts.can_invite(principal)}

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port < 65536:
        parser.error("Nonprivileged TCP port required")
    key = os.environ.get("RIO_R015_FIXTURE_KEY", "")
    app = make_test_app(args.db.resolve(), key, args.port)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="error")
