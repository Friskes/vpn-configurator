"""Общие фикстуры: эталонные входные файлы и защита глобального языка от утечки между тестами."""

import pytest

from vpn_i18n import language


@pytest.fixture(autouse=True)
def _language_guard():
    """Фиксирует язык на en для детерминизма сообщений и восстанавливает после теста;
    GUI-тесты в своей фикстуре app сами переставляют язык на ru поверх."""
    saved = language.code
    language.code = "en"
    yield
    language.code = saved


@pytest.fixture
def ips_file(tmp_path):
    file = tmp_path / "ips.txt"
    file.write_text("8.8.8.8, 1.1.1.0/24", encoding="utf-8")
    return file


@pytest.fixture
def wg_conf(tmp_path):
    conf = tmp_path / "src.conf"
    conf.write_text(
        "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\nAllowedIPs = 0.0.0.0/0\n",
        encoding="utf-8",
    )
    return conf
