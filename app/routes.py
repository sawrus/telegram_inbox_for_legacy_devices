from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_from_directory, url_for


def _parse_chat_id(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_chat(chats, chat_id):
    for chat in chats:
        if chat.id == chat_id:
            return chat
    return None


def _build_pane(name, chats, selected_chat_id, service):
    selected_chat = _find_chat(chats, selected_chat_id)

    messages = []
    error = None
    if selected_chat:
        try:
            messages = service.list_messages(selected_chat.id)
            for message in messages:
                if message.media_kind == "photo" and message.media_filename:
                    message.media_url = url_for("main.media_file", filename=message.media_filename)
        except Exception as exc:
            error = str(exc)

    return {
        "name": name,
        "selected_chat": selected_chat,
        "selected_chat_id": selected_chat.id if selected_chat else "",
        "chats": list(chats),
        "messages": messages,
        "error": error,
    }


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
            if hasattr(service, "validate_timezone"):
                service.validate_timezone()
            chats = service.list_chats()
        except Exception as exc:
            error = str(exc)

        left_chat_id = _parse_chat_id(request.args.get("left_chat_id") or current_app.config.get("LEFT_CHAT_ID"))
        right_chat_id = _parse_chat_id(request.args.get("right_chat_id") or current_app.config.get("RIGHT_CHAT_ID"))

        left_pane = _build_pane("left", chats, left_chat_id, service) if not error else {
            "name": "left",
            "selected_chat": None,
            "selected_chat_id": "",
            "chats": [],
            "messages": [],
            "error": None,
        }
        right_pane = _build_pane("right", chats, right_chat_id, service) if not error else {
            "name": "right",
            "selected_chat": None,
            "selected_chat_id": "",
            "chats": [],
            "messages": [],
            "error": None,
        }

        return render_template(
            "chats.html",
            left_pane=left_pane,
            right_pane=right_pane,
            error=error,
            refresh_seconds=current_app.config["REFRESH_SECONDS"],
            message_timezone=current_app.config["MESSAGE_TIMEZONE"],
        )

    @bp.route("/chats/<int:chat_id>")
    def chat_messages(chat_id):
        return redirect(url_for("main.index", left_chat_id=chat_id))

    @bp.route("/media/<path:filename>")
    def media_file(filename):
        media_cache_dir = Path(current_app.config["MEDIA_CACHE_DIR"]).resolve()
        file_path = (media_cache_dir / filename).resolve()
        if media_cache_dir not in file_path.parents or not file_path.is_file():
            abort(404)
        return send_from_directory(media_cache_dir, file_path.name, conditional=True, max_age=3600)

    return bp
