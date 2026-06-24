from flask import Flask

from .config import Config
from .routes import create_blueprint
from .telegram_client import TelegramService


def create_app(config_class=Config, telegram_service=None):
    app = Flask(__name__)
    app.config.from_object(config_class)

    service = telegram_service or TelegramService.from_config(app.config)
    app.config["TELEGRAM_SERVICE"] = service

    app.register_blueprint(create_blueprint())
    return app
