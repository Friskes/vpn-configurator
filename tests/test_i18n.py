import locale

import pytest

from vpn_i18n import TRANSLATIONS, detect_system_language


def test_translations_keys_symmetric():
    """Наборы ключей ru и en обязаны совпадать, иначе tr() упадёт при переключении языка."""
    assert set(TRANSLATIONS["ru"]) == set(TRANSLATIONS["en"])


@pytest.mark.parametrize(
    ("locale_value", "expected"),
    [
        (("ru_RU", "UTF-8"), "ru"),
        (("Russian_Russia", "1251"), "ru"),
        (("en_US", "UTF-8"), "en"),
        (("de_DE", "UTF-8"), "en"),
        ((None, None), "en"),
    ],
)
def test_detect_system_language(monkeypatch, locale_value, expected):
    monkeypatch.setattr(locale, "getlocale", lambda: locale_value)
    assert detect_system_language() == expected


def test_detect_system_language_locale_error(monkeypatch):
    def raise_value_error():
        raise ValueError("unknown locale")

    monkeypatch.setattr(locale, "getlocale", raise_value_error)
    assert detect_system_language() == "en"
