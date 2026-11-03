from markupsafe import Markup
from telethon.tl.types import MessageEntityBold, MessageEntityTextUrl, MessageEntityUrl

from app.telegram_html import render_telegram_html


def test_entities_are_rendered_using_telegram_utf16_offsets():
    rendered = render_telegram_html("😀 bold", [MessageEntityBold(offset=3, length=4)])

    assert rendered == "😀 <strong>bold</strong>"
    assert isinstance(rendered, Markup)


def test_raw_html_in_message_text_is_escaped():
    rendered = render_telegram_html('<script>alert(1)</script><b onclick="x">raw</b>', [])

    assert "<script" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&lt;b onclick=&quot;x&quot;&gt;" in rendered


def test_safe_absolute_entity_link_is_preserved():
    rendered = render_telegram_html(
        "OpenAI",
        [MessageEntityTextUrl(offset=0, length=6, url="https://openai.com/docs?q=1")],
    )

    assert rendered == '<a href="https://openai.com/docs?q=1">OpenAI</a>'


def test_relative_protocol_relative_control_and_disallowed_links_are_removed():
    urls = [
        "/local",
        "//evil.example",
        "https://good.example/\nattack",
        "https://good.example/\u202eattack",
        "javascript:alert(1)",
    ]

    for url in urls:
        rendered = render_telegram_html("click", [MessageEntityTextUrl(offset=0, length=5, url=url)])
        assert rendered == "click"


def test_bare_url_entity_is_sanitized_with_the_same_url_policy():
    rendered = render_telegram_html("https://example.com", [MessageEntityUrl(offset=0, length=19)])

    assert rendered == '<a href="https://example.com">https://example.com</a>'
