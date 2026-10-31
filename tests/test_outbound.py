from __future__ import annotations

from doge_telegram_channel.outbound import inline_keyboard_from_actions


def test_inline_keyboard_from_openapi_actions() -> None:
    markup = inline_keyboard_from_actions(
        [
            {"label": "Yes", "token": "tok-yes", "style": "primary"},
            {"label": "No", "token": "tok-no", "style": "default"},
        ]
    )
    assert markup == {
        "inline_keyboard": [
            [
                {"text": "Yes", "callback_data": "tok-yes"},
                {"text": "No", "callback_data": "tok-no"},
            ]
        ]
    }
