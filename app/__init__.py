import hmac
import threading
import time
from collections import deque

from flask import Flask, Response, request

from .config import Config
from .routes import create_blueprint
from .telegram_client import TelegramService


def create_app(config_class=Config, telegram_service=None):
    app = Flask(__name__)
    app.config.from_object(config_class)
    username = app.config.get("INBOX_USERNAME", "")
    password = app.config.get("INBOX_PASSWORD", "")
    if not username or not password or ":" in username:
        raise RuntimeError("INBOX_USERNAME and INBOX_PASSWORD must be set; username must not contain ':'")

    # One worker is used in production; bounds prevent untrusted clients exhausting memory.
    lock = threading.Lock()
    failures = {}
    rpc_requests = deque()

    @app.before_request
    def authorize_and_limit():
        if request.path in ("/health", "/health/live"):
            return None
        now = time.monotonic()
        peer = request.remote_addr or "unknown"
        with lock:
            for key in list(failures):
                if now - failures[key][1] >= 60:
                    del failures[key]
            if peer in failures and failures[peer][0] >= 10:
                return Response("Too many requests", 429, headers={"Retry-After": "60"})
        auth = request.authorization
        valid = (auth is not None and auth.type.lower() == "basic"
                 and hmac.compare_digest((auth.username or "").encode(), username.encode())
                 and hmac.compare_digest((auth.password or "").encode(), password.encode()))
        if not valid:
            with lock:
                if peer not in failures and len(failures) >= 1024:
                    # Fail closed rather than allow unlimited distinct source addresses.
                    return Response("Too many requests", 429, headers={"Retry-After": "60"})
                count, started = failures.get(peer, (0, now))
                failures[peer] = (count + 1, started)
            app.logger.warning("authentication_failed")
            return Response("Authentication required", 401, headers={"WWW-Authenticate": 'Basic realm="Telegram Inbox", charset="UTF-8"'})
        if request.path in ("/", "/health/ready"):
            with lock:
                while rpc_requests and now - rpc_requests[0] >= 60:
                    rpc_requests.popleft()
                if len(rpc_requests) >= 60:
                    return Response("Too many requests", 429, headers={"Retry-After": "60"})
                rpc_requests.append(now)
        return None

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers["Cache-Control"] = "no-store"
        return response

    service = telegram_service or TelegramService.from_config(app.config)
    app.config["TELEGRAM_SERVICE"] = service
    app.register_blueprint(create_blueprint())
    return app
