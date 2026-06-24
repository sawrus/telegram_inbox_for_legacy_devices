from flask import Blueprint, current_app, render_template


def create_blueprint():
    bp = Blueprint("main", __name__)

    @bp.route("/health")
    def health():
        return {"status": "ok"}

    @bp.route("/")
    def index():
        service = current_app.config["TELEGRAM_SERVICE"]
        error = None
        chats = []
        try:
            chats = service.list_chats()
        except Exception as exc:
            error = str(exc)
        return render_template("chats.html", chats=chats, error=error)

    @bp.route("/chats/<int:chat_id>")
    def chat_messages(chat_id):
        service = current_app.config["TELEGRAM_SERVICE"]
        error = None
        messages = []
        try:
            messages = service.list_incoming_messages(chat_id)
        except Exception as exc:
            error = str(exc)
        return render_template(
            "messages.html",
            chat_id=chat_id,
            messages=messages,
            error=error,
            refresh_seconds=current_app.config["REFRESH_SECONDS"],
        )

    return bp
