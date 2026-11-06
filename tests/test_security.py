import base64

import pytest

from app import create_app
from conftest import FakeTelegramService, TestConfig


def auth(username="test", password="test-password"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_missing_credentials_prevent_startup():
    class MissingConfig(TestConfig):
        INBOX_PASSWORD = ""

    with pytest.raises(RuntimeError, match="INBOX_USERNAME"):
        create_app(MissingConfig, FakeTelegramService())


def test_authorization_covers_sensitive_routes():
    app = create_app(TestConfig, FakeTelegramService())
    client = app.test_client()
    assert client.get("/health/live").status_code == 200
    for path in ("/", "/health/ready", "/media/example.jpg", "/chats/1"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=auth(password="wrong")).status_code == 401
    assert client.get("/", headers=auth()).status_code == 200
    assert client.get("/health/ready", headers=auth()).status_code == 200
    assert client.get("/media/example.jpg", headers=auth()).status_code == 404


def test_failed_authentication_and_rpc_are_limited():
    app = create_app(TestConfig, FakeTelegramService())
    client = app.test_client()
    for _ in range(10):
        assert client.get("/", headers=auth(password="wrong")).status_code == 401
    assert client.get("/", headers=auth()).status_code == 429
    assert client.get("/health/live").status_code == 200

    app = create_app(TestConfig, FakeTelegramService())
    client = app.test_client()
    for _ in range(60):
        assert client.get("/health/ready", headers=auth()).status_code == 200
    assert client.get("/health/ready", headers=auth()).status_code == 429


def test_security_headers_apply_to_errors_and_content():
    app = create_app(TestConfig, FakeTelegramService())
    for response in (app.test_client().get("/"), app.test_client().get("/", headers=auth())):
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert response.headers["Cache-Control"] == "no-store"
