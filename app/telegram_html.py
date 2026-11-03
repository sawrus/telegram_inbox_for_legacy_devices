import re
import unicodedata
from urllib.parse import urlsplit

import bleach
from markupsafe import Markup
from telethon.extensions import html as telethon_html


ALLOWED_TAGS = frozenset({"a", "blockquote", "code", "del", "em", "pre", "strong", "u"})
ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto", "tg"})
LANGUAGE_CLASS_PATTERN = re.compile(r"language-[A-Za-z0-9_+-]+\Z")
EMPTY_ANCHOR_PATTERN = re.compile(r"<a>(.*?)</a>", re.DOTALL)


def _is_safe_url(value):
    if not value or value.startswith(("/", "\\")):
        return False
    if any(unicodedata.category(character).startswith("C") for character in value):
        return False

    try:
        parsed = urlsplit(value)
    except ValueError:
        return False

    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_PROTOCOLS:
        return False
    if scheme in {"http", "https", "tg"}:
        return bool(parsed.netloc)
    return scheme == "mailto" and bool(parsed.path) and not parsed.netloc


def _allow_attribute(tag, name, value):
    if tag == "a" and name == "href":
        return _is_safe_url(value)
    if tag == "code" and name == "class":
        return bool(LANGUAGE_CLASS_PATTERN.fullmatch(value))
    return False


_CLEANER = bleach.Cleaner(
    tags=ALLOWED_TAGS,
    attributes=_allow_attribute,
    protocols=ALLOWED_PROTOCOLS,
    strip=True,
    strip_comments=True,
)


def render_telegram_html(text, entities):
    entity_html = telethon_html.unparse(text or "", entities or [])
    sanitized_html = _CLEANER.clean(entity_html)
    sanitized_html = EMPTY_ANCHOR_PATTERN.sub(r"\1", sanitized_html)
    return Markup(sanitized_html)
