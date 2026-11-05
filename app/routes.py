from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_from_directory, url_for

from .telegram_client import ChatSummary, TelegramConfigurationError, TelegramUnavailableError


TELEGRAM_EXPECTED_ERRORS = (TelegramUnavailableError, TelegramConfigurationError)
TELEGRAM_UNAVAILABLE_MESSAGE = "Telegram временно недоступен. Повторите попытку позже."


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


def _merge_pinned_chats(chats, pinned_chats):
    merged = list(chats)
    known_ids = {chat.id for chat in merged}
    for chat_id, title in pinned_chats:
        if chat_id not in known_ids:
            merged.append(ChatSummary(id=chat_id, title=title))
            known_ids.add(chat_id)
    return merged


def _build_loaded_pane(name, chats, selected_chat_id, page_result):
    selected_chat = _find_chat(chats, selected_chat_id)
    messages = page_result.messages_by_chat_id.get(selected_chat_id, [])
    for message in messages:
        if message.media_kind == "photo" and message.media_filename:
            message.media_url = url_for("main.media_file", filename=message.media_filename)
    error = None
    if selected_chat_id in page_result.errors_by_chat_id:
        current_app.logger.warning(
            "telegram_pane_failed path=/ pane=%s error_type=%s",
            name,
            type(page_result.errors_by_chat_id[selected_chat_id]).__name__,
        )
        error = TELEGRAM_UNAVAILABLE_MESSAGE
    if selected_chat_id in page_result.stale_chat_ids:
        current_app.logger.warning("telegram_pane_stale path=/ pane=%s", name)
    return {
        "name": name,
        "selected_chat": selected_chat,
        "selected_chat_id": selected_chat_id or "",
        "chats": list(chats),
        "messages": messages,
        "error": error,
    }


def _empty_pane(name):
    return {
        "name": name,
        "selected_chat": None,
        "selected_chat_id": "",
        "chats": [],
        "messages": [],
        "error": None,
    }


def create_blueprint():
    bp = Blueprint("main", __name__)

    @bp.route("/health")
    @bp.route("/health/live")
    def health():
        return {"status": "ok"}

    @bp.route("/health/ready")
    def readiness():
        service = current_app.config["TELEGRAM_SERVICE"]
        timeout_seconds = current_app.config["TELEGRAM_PAGE_TIMEOUT_SECONDS"]
        try:
            service.check_readiness(timeout_seconds=timeout_seconds)
        except TELEGRAM_EXPECTED_ERRORS as exc:
            current_app.logger.warning(
                "telegram_readiness_failed error_type=%s",
                type(exc).__name__,
            )
            return {"status": "unavailable"}, 503
        return {"status": "ready"}

    @bp.route("/")
    def index():
        service = current_app.config["TELEGRAM_SERVICE"]
        left_chat_id = _parse_chat_id(request.args.get("left_chat_id") or current_app.config.get("LEFT_CHAT_ID"))
        right_chat_id = _parse_chat_id(request.args.get("right_chat_id") or current_app.config.get("RIGHT_CHAT_ID"))
        error = None
        chats = []
        status_code = 200
        page_result = None
        try:
            page_result = service.load_page(
                left_chat_id,
                right_chat_id,
                dialog_timeout_seconds=current_app.config["TELEGRAM_DIALOG_LIST_TIMEOUT_SECONDS"],
                timeout_seconds=current_app.config["TELEGRAM_PAGE_TIMEOUT_SECONDS"],
            )
            chats = _merge_pinned_chats(page_result.chats, current_app.config.get("PINNED_CHATS", ()))
        except TELEGRAM_EXPECTED_ERRORS as exc:
            current_app.logger.warning(
                "telegram_page_failed path=/ error_type=%s",
                type(exc).__name__,
            )
            error = TELEGRAM_UNAVAILABLE_MESSAGE
            status_code = 503

        left_pane = _empty_pane("left")
        right_pane = _empty_pane("right")
        if not error:
            left_pane = _build_loaded_pane("left", chats, left_chat_id, page_result)
            right_pane = _build_loaded_pane("right", chats, right_chat_id, page_result)

        return render_template(
            "chats.html",
            left_pane=left_pane,
            right_pane=right_pane,
            error=error,
            refresh_seconds=current_app.config["REFRESH_SECONDS"],
            message_timezone=current_app.config["MESSAGE_TIMEZONE"],
        ), status_code

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
