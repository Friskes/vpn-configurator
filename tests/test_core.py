import json

import pytest

import vpn_configurator as core


def build(ips, conf, **kwargs):
    return core.build_wireguard_conf(ips, conf, kwargs.pop("obfuscate", False), **kwargs)


class TestCollectIps:
    def test_per_line(self, tmp_path):
        file = tmp_path / "ips.txt"
        file.write_text("8.8.8.8\n1.1.1.0/24\n", encoding="utf-8")
        assert core.collect_ips([file]) == ["8.8.8.8", "1.1.1.0/24"]

    @pytest.mark.parametrize(
        "content",
        [
            "8.8.8.8, 1.1.1.1, 9.9.9.9",
            "8.8.8.8 1.1.1.1 9.9.9.9",
            "8.8.8.8;1.1.1.1;9.9.9.9",
            "8.8.8.8,\t1.1.1.1 ;9.9.9.9",
            "8.8.8.8 1.1.1.1\n9.9.9.9",
        ],
    )
    def test_separators_in_one_line(self, tmp_path, content):
        """Адреса в одной строке через запятую, пробел, точку с запятой или таб."""
        file = tmp_path / "ips.txt"
        file.write_text(content, encoding="utf-8")
        assert core.collect_ips([file]) == ["8.8.8.8", "1.1.1.1", "9.9.9.9"]

    def test_windows_route_format(self, tmp_path):
        """Формат route ADD: маска конвертируется в длину префикса, gateway отбрасывается."""
        file = tmp_path / "routes.bat"
        file.write_text(
            "route ADD 173.194.187.0 MASK 255.255.255.0 0.0.0.0\n"
            "route ADD 204.15.20.0 MASK 255.255.252.0 0.0.0.0\n"
            "route ADD 164.163.191.64 MASK 255.255.255.192 0.0.0.0\n"
            "route add 199.201.0.0 mask 255.255.0.0 10.0.0.1\n"
            "route ADD 8.8.8.8 MASK 255.255.255.255 0.0.0.0\n",
            encoding="utf-8",
        )
        assert core.collect_ips([file]) == [
            "173.194.187.0/24",
            "204.15.20.0/22",
            "164.163.191.64/26",
            "199.201.0.0/16",
            "8.8.8.8",
        ]

    def test_route_with_flags_and_without_mask(self, tmp_path):
        """route -p ADD и route ADD без MASK: маска и gateway не должны попадать в результат."""
        file = tmp_path / "routes.txt"
        file.write_text(
            "route -p ADD 157.0.0.0 MASK 255.0.0.0 157.55.80.1\nroute ADD 8.8.8.8 10.0.0.1\n",
            encoding="utf-8",
        )
        assert core.collect_ips([file]) == ["157.0.0.0/8", "8.8.8.8"]

    def test_route_delete_lines_do_not_abort(self, tmp_path):
        """Файл из 31 route DELETE не должен ронять операцию по лимиту некорректных адресов."""
        file = tmp_path / "del.bat"
        lines = [f"route DELETE 10.0.{i}.0 MASK 255.255.255.0 10.0.0.1" for i in range(31)]
        file.write_text("\n".join(lines) + "\n8.8.8.8\n", encoding="utf-8")
        assert core.collect_ips([file]) == ["8.8.8.8"]

    def test_file_without_extension(self, tmp_path):
        file = tmp_path / "noext"
        file.write_text("8.8.8.8", encoding="utf-8")
        assert core.collect_ips([file]) == ["8.8.8.8"]

    def test_amnezia_json(self, tmp_path):
        file = tmp_path / "ips.json"
        file.write_text(
            json.dumps([{"hostname": "9.9.9.9", "ip": ""}, {"hostname": "1.0.0.0/24", "ip": ""}]),
            encoding="utf-8",
        )
        assert core.collect_ips([file]) == ["9.9.9.9", "1.0.0.0/24"]

    def test_json_array_of_strings(self, tmp_path):
        file = tmp_path / "ips.json"
        file.write_text('["9.9.9.9", "1.0.0.0/24"]', encoding="utf-8")
        assert core.collect_ips([file]) == ["9.9.9.9", "1.0.0.0/24"]

    @pytest.mark.parametrize("content", ["[{broken", '{"hostname": "9.9.9.9"}'])
    def test_bad_json_raises(self, tmp_path, content):
        file = tmp_path / "ips.json"
        file.write_text(content, encoding="utf-8")
        with pytest.raises(core.VpnConfiguratorError):
            core.collect_ips([file])

    def test_bracket_header_text_is_not_json(self, tmp_path):
        """Текстовый файл, начинающийся с [заголовка], не должен падать как битый JSON."""
        file = tmp_path / "list.txt"
        file.write_text("[block Google]\n8.8.8.8\n", encoding="utf-8")
        assert core.collect_ips([file]) == ["8.8.8.8"]

    def test_mixed_files(self, tmp_path):
        txt = tmp_path / "a.txt"
        txt.write_text("8.8.8.8", encoding="utf-8")
        amnezia = tmp_path / "b.json"
        amnezia.write_text('[{"hostname": "9.9.9.9", "ip": ""}]', encoding="utf-8")
        assert core.collect_ips([txt, amnezia]) == ["8.8.8.8", "9.9.9.9"]

    def test_cidr_normalization(self, tmp_path):
        """Маска-октеты сводится к префиксу, /32 — к одиночному адресу."""
        file = tmp_path / "ips.txt"
        file.write_text("1.1.1.0/255.255.255.0\n2.2.2.2/32\n", encoding="utf-8")
        assert core.collect_ips([file]) == ["1.1.1.0/24", "2.2.2.2"]

    def test_duplicates_after_normalization(self, tmp_path):
        """8.8.8.8, 8.8.8.8/32 и route с маской /32 — один и тот же адрес."""
        file = tmp_path / "ips.txt"
        file.write_text(
            "8.8.8.8\n8.8.8.8/32\nroute ADD 8.8.8.8 MASK 255.255.255.255 0.0.0.0\n",
            encoding="utf-8",
        )
        assert core.collect_ips([file]) == ["8.8.8.8"]

    def test_invalid_skipped(self, tmp_path):
        file = tmp_path / "ips.txt"
        file.write_text("8.8.8.8\nnot-an-ip\n1.1.1.5/24\n", encoding="utf-8")
        assert core.collect_ips([file]) == ["8.8.8.8"]

    @pytest.mark.parametrize("prefix", ["#", ";", "//"])
    def test_comments_skipped(self, tmp_path, prefix):
        file = tmp_path / "ips.txt"
        file.write_text(f"{prefix} 10.0.0.1 comment text\n8.8.8.8\n", encoding="utf-8")
        assert core.collect_ips([file]) == ["8.8.8.8"]

    def test_inline_comment_after_ip(self, tmp_path):
        """Комментарий после адреса на той же строке отрезается, а не превращается в мусор-токены."""
        file = tmp_path / "ips.txt"
        long_comment = " ".join(f"word{i}" for i in range(40))
        file.write_text(f"8.8.8.8 # {long_comment}\n1.1.1.1 // tail\n", encoding="utf-8")
        assert core.collect_ips([file]) == ["8.8.8.8", "1.1.1.1"]

    def test_too_many_invalid_raises(self, tmp_path):
        file = tmp_path / "trash.txt"
        file.write_text("\n".join(f"garbage-{i}" for i in range(40)), encoding="utf-8")
        with pytest.raises(core.VpnConfiguratorError):
            core.collect_ips([file])

    def test_invalid_counter_resets_per_file(self, tmp_path):
        """Лимит «подряд» не должен суммироваться через границу файлов."""
        file_a = tmp_path / "a.txt"
        file_a.write_text("8.8.8.8\n" + "\n".join(f"trash-a{i}" for i in range(20)), encoding="utf-8")
        file_b = tmp_path / "b.txt"
        file_b.write_text("\n".join(f"trash-b{i}" for i in range(20)) + "\n1.1.1.1", encoding="utf-8")
        assert core.collect_ips([file_a, file_b]) == ["8.8.8.8", "1.1.1.1"]

    def test_no_valid_ips_raises(self, tmp_path):
        file = tmp_path / "empty.txt"
        file.write_text("\n\n", encoding="utf-8")
        with pytest.raises(core.VpnConfiguratorError):
            core.collect_ips([file])

    def test_null_hostname_skipped(self, tmp_path):
        file = tmp_path / "ips.json"
        file.write_text('[{"hostname": null, "ip": ""}, {"hostname": "8.8.8.8", "ip": ""}]')
        assert core.collect_ips([file]) == ["8.8.8.8"]

    def test_utf8_bom_plaintext(self, tmp_path):
        """BOM от Notepad не должен ломать первый адрес."""
        file = tmp_path / "ips.txt"
        file.write_bytes("8.8.8.8\n1.1.1.1\n".encode("utf-8-sig"))
        assert file.read_bytes().startswith(b"\xef\xbb\xbf")
        assert core.collect_ips([file]) == ["8.8.8.8", "1.1.1.1"]

    def test_utf8_bom_json(self, tmp_path):
        file = tmp_path / "ips.json"
        file.write_bytes('[{"hostname": "9.9.9.9", "ip": ""}]'.encode("utf-8-sig"))
        assert core.collect_ips([file]) == ["9.9.9.9"]

    def test_utf16_file(self, tmp_path):
        """UTF-16 с BOM — типичный результат редиректа в Windows PowerShell 5."""
        file = tmp_path / "ips.txt"
        file.write_text("8.8.8.8\n1.1.1.1\n", encoding="utf-16")
        assert core.collect_ips([file]) == ["8.8.8.8", "1.1.1.1"]

    def test_utf32_file(self, tmp_path):
        """UTF-32 с BOM (порядок проверок BOM load-bearing: UTF-32 LE начинается с UTF-16 LE BOM)."""
        file = tmp_path / "ips.txt"
        file.write_text("8.8.8.8\n1.1.1.1\n", encoding="utf-32")
        assert core.collect_ips([file]) == ["8.8.8.8", "1.1.1.1"]

    def test_unsupported_encoding_raises(self, tmp_path):
        """cp1251 с кириллицей — понятная ошибка вместо UnicodeDecodeError."""
        file = tmp_path / "ips.txt"
        file.write_bytes("# Список IP\n8.8.8.8\n".encode("cp1251"))
        with pytest.raises(core.VpnConfiguratorError):
            core.collect_ips([file])

    def test_truncated_utf16_reports_encoding_error(self, tmp_path):
        file = tmp_path / "ips.txt"
        file.write_bytes(b"\xff\xfe8\x00.\x008")
        with pytest.raises(core.VpnConfiguratorError):
            core.collect_ips([file])


class TestAppNames:
    def test_per_line_with_comments(self, tmp_path):
        """Комментарии (#, ;, //) отсекаются построчно: `;` не должен работать как разделитель."""
        file = tmp_path / "apps.txt"
        file.write_text(
            "# comment\nchrome\n; another comment\n// third\ntelegram\n", encoding="utf-8"
        )
        assert core.collect_app_names([file]) == ["chrome", "telegram"]

    def test_mixed_separators(self, tmp_path):
        """Запятая, точка с запятой, пробел и таб в одной строке."""
        file = tmp_path / "apps.txt"
        file.write_text("chrome, firefox telegram;discord\tspotify\nqbittorrent\n", encoding="utf-8")
        assert core.collect_app_names([file]) == [
            "chrome",
            "firefox",
            "telegram",
            "discord",
            "spotify",
            "qbittorrent",
        ]

    def test_full_paths_with_spaces_kept_whole(self):
        """Полный путь содержит пробелы, но не должен разбиваться на части."""
        assert core.parse_app_names("C:\\Program Files\\App\\app.exe\n/Applications/Foo.app") == [
            "C:\\Program Files\\App\\app.exe",
            "/Applications/Foo.app",
        ]

    def test_exe_gives_stem(self):
        assert core.collect_app_names([r"C:\Program Files\Google\Chrome\chrome.exe"]) == ["chrome"]

    def test_binary_without_extension_gives_stem(self, tmp_path):
        """Бинарь другой ОС не декодируется как текст — именем становится имя файла."""
        binary = tmp_path / "my-daemon"
        binary.write_bytes(b"\x7fELF\x02\x01\x01\x00\xff\xfe\xfd")
        assert core.collect_app_names([binary]) == ["my-daemon"]

    def test_dedup_case_insensitive(self, tmp_path):
        file = tmp_path / "apps.txt"
        file.write_text("chrome\nCHROME\nChrome\n", encoding="utf-8")
        assert core.collect_app_names([file]) == ["chrome"]

    def test_empty_list(self):
        assert core.parse_app_names("") == []
        assert core.collect_app_names([]) == []


@pytest.fixture
def conf_lines():
    return "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\nAllowedIPs = 0.0.0.0/0\n"


class TestBuildWireguardConf:
    def test_without_obfuscation(self, wg_conf):
        text = build(["8.8.8.8", "1.1.1.0/24"], wg_conf)
        assert "AllowedIPs = 8.8.8.8, 1.1.1.0/24" in text
        assert "ObfuscateKey" not in text
        assert "rustdesk" not in text

    def test_with_obfuscation(self, wg_conf):
        """Обфускация добавляет только свои ключи; rustdesk управляется auto_disallowed_apps."""
        text = build(["8.8.8.8"], wg_conf, obfuscate=True)
        assert "ObfuscateKey" in text
        assert "ObfuscateMethod = xor" in text
        assert "rustdesk" not in text

    def test_auto_disallowed_apps(self, wg_conf):
        text = build(["8.8.8.8"], wg_conf, auto_disallowed_apps=("rustdesk",))
        assert "DisallowedApps = rustdesk" in text

    def test_auto_disallowed_not_duplicated(self, tmp_path):
        """rustdesk уже в DisallowedApps (в любом регистре) — второй раз не добавляется."""
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\n"
            "DisallowedApps = firefox, RustDesk\n",
            encoding="utf-8",
        )
        text = build(["8.8.8.8"], conf, auto_disallowed_apps=("rustdesk",))
        assert "DisallowedApps = firefox, RustDesk" in text
        assert text.lower().count("rustdesk") == 1

    def test_bypass_lan_added(self, wg_conf):
        text = build(["8.8.8.8"], wg_conf, bypass_lan=True)
        assert "BypassLanTraffic = true" in text

    def test_bypass_lan_absent_by_default(self, wg_conf):
        assert "BypassLanTraffic" not in build(["8.8.8.8"], wg_conf, obfuscate=True)

    @pytest.mark.parametrize("content", ["[Interface]\nPrivateKey = abc\n", "[Peer]\nPublicKey = d\n"])
    def test_missing_section_raises(self, tmp_path, content):
        conf = tmp_path / "src.conf"
        conf.write_text(content, encoding="utf-8")
        with pytest.raises(core.VpnConfiguratorError):
            build(["8.8.8.8"], conf)

    def test_missing_conf_file_raises(self, tmp_path):
        with pytest.raises(core.VpnConfiguratorError, match="missing.conf"):
            build(["8.8.8.8"], tmp_path / "missing.conf")

    def test_conf_with_utf8_bom(self, tmp_path):
        conf = tmp_path / "src.conf"
        conf.write_bytes(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\n".encode("utf-8-sig")
        )
        assert "AllowedIPs = 8.8.8.8" in build(["8.8.8.8"], conf)

    def test_multiple_peer_sections_rejected(self, tmp_path):
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = one\n\n[Peer]\nPublicKey = two\n",
            encoding="utf-8",
        )
        with pytest.raises(core.VpnConfiguratorError):
            build(["8.8.8.8"], conf)

    def test_percent_in_values_does_not_break(self, tmp_path):
        """Знак % (пути с переменными окружения) не должен ломать разбор."""
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\n"
            "DisallowedApps = %ProgramFiles%\\app.exe\n",
            encoding="utf-8",
        )
        text = build(["8.8.8.8"], conf, auto_disallowed_apps=("rustdesk",))
        assert "%ProgramFiles%\\app.exe, rustdesk" in text

    def test_lowercase_keys_replaced_not_duplicated(self, tmp_path):
        """WireGuard парсит ключи регистронезависимо: 'allowedips' должен замениться,
        а не получить второй ключ AllowedIPs рядом (иначе split tunneling молча не работает)."""
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\n"
            "allowedips = 0.0.0.0/0\ndisallowedapps = chrome\n",
            encoding="utf-8",
        )
        text = build(
            ["8.8.8.8"],
            conf,
            disallowed_apps=["telegram"],
            auto_disallowed_apps=("rustdesk",),
        )
        assert "0.0.0.0/0" not in text
        assert "AllowedIPs = 8.8.8.8" in text
        assert text.lower().count("allowedips") == 1
        assert "DisallowedApps = chrome, telegram, rustdesk" in text
        assert text.lower().count("disallowedapps") == 1

    def test_lowercase_sections_accepted(self, tmp_path):
        conf = tmp_path / "src.conf"
        conf.write_text("[interface]\nPrivateKey = abc\n\n[peer]\nPublicKey = def\n", encoding="utf-8")
        assert "AllowedIPs = 8.8.8.8" in build(["8.8.8.8"], conf)

    def test_comments_and_repeated_keys_preserved(self, tmp_path):
        """Комментарии и повторяющиеся PostUp (валидный wg-quick приём) переживают обработку."""
        conf = tmp_path / "src.conf"
        conf.write_text(
            "# main tunnel\n[Interface]\nPrivateKey = abc\nPostUp = cmd1\nPostUp = cmd2\n\n"
            "[Peer]\n; peer comment\nPublicKey = def\nAllowedIPs = 0.0.0.0/0\n",
            encoding="utf-8",
        )
        text = build(["8.8.8.8"], conf)
        assert "# main tunnel" in text
        assert "; peer comment" in text
        assert "PostUp = cmd1" in text
        assert "PostUp = cmd2" in text

    def test_repeated_allowedips_collapsed_to_one(self, tmp_path):
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\n"
            "AllowedIPs = 0.0.0.0/0\nAllowedIPs = ::/0\n",
            encoding="utf-8",
        )
        text = build(["8.8.8.8"], conf)
        assert text.lower().count("allowedips") == 1
        assert "AllowedIPs = 8.8.8.8" in text

    def test_indented_key_recognized(self, tmp_path):
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\n   AllowedIPs = 0.0.0.0/0\n",
            encoding="utf-8",
        )
        text = build(["8.8.8.8"], conf)
        assert text.lower().count("allowedips") == 1
        assert "AllowedIPs = 8.8.8.8" in text


class TestWireSockRules:
    def test_disallowed_ips_and_apps(self, wg_conf):
        text = build(
            ["8.8.8.8"],
            wg_conf,
            obfuscate=True,
            disallowed_ips=["192.168.0.0/16", "10.0.0.0/8"],
            disallowed_apps=["chrome", "telegram"],
            auto_disallowed_apps=("rustdesk",),
        )
        assert "DisallowedIPs = 192.168.0.0/16, 10.0.0.0/8" in text
        assert "DisallowedApps = chrome, telegram, rustdesk" in text

    def test_disallowed_merged_with_existing(self, tmp_path):
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\n"
            "DisallowedIPs = 172.16.0.0/12\nDisallowedApps = Chrome, RustDesk\n",
            encoding="utf-8",
        )
        text = build(
            ["8.8.8.8"],
            conf,
            obfuscate=True,
            disallowed_ips=["192.168.0.0/16", "172.16.0.0/12"],
            disallowed_apps=["chrome", "discord"],
        )
        assert "DisallowedIPs = 172.16.0.0/12, 192.168.0.0/16" in text
        assert "DisallowedApps = Chrome, RustDesk, discord" in text

    def test_allowed_apps(self, wg_conf):
        """Белый список: rustdesk в DisallowedApps не дописывается — режимы взаимоисключающие."""
        text = build(["8.8.8.8"], wg_conf, obfuscate=True, allowed_apps=["qbittorrent", "firefox"])
        assert "AllowedApps = qbittorrent, firefox" in text
        assert "DisallowedApps" not in text
        assert "rustdesk" not in text

    def test_whitelist_removes_existing_disallowed_apps(self, tmp_path):
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\nDisallowedApps = rustdesk\n",
            encoding="utf-8",
        )
        text = build(["8.8.8.8"], conf, obfuscate=True, allowed_apps=["qbittorrent"])
        assert "AllowedApps = qbittorrent" in text
        assert "DisallowedApps" not in text

    def test_blacklist_removes_existing_allowed_apps(self, tmp_path):
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\nAllowedApps = firefox\n",
            encoding="utf-8",
        )
        text = build(["8.8.8.8"], conf, disallowed_apps=["chrome"])
        assert "DisallowedApps = chrome" in text
        assert "AllowedApps" not in text

    def test_rustdesk_skipped_when_source_has_allowed_apps(self, tmp_path):
        conf = tmp_path / "src.conf"
        conf.write_text(
            "[Interface]\nPrivateKey = abc\n\n[Peer]\nPublicKey = def\nAllowedApps = firefox\n",
            encoding="utf-8",
        )
        text = build(["8.8.8.8"], conf, obfuscate=True)
        assert "AllowedApps = firefox" in text
        assert "rustdesk" not in text

    def test_both_app_lists_rejected(self, wg_conf):
        with pytest.raises(ValueError):
            build(
                ["8.8.8.8"],
                wg_conf,
                obfuscate=True,
                disallowed_apps=["chrome"],
                allowed_apps=["firefox"],
            )


@pytest.fixture
def android_conf(tmp_path):
    def make(interface_extra="", peer_extra=""):
        conf = tmp_path / "src.conf"
        conf.write_text(
            f"[Interface]\nPrivateKey = abc\n{interface_extra}\n[Peer]\nPublicKey = def\n{peer_extra}",
            encoding="utf-8",
        )
        return conf

    return make


class TestAndroidRules:
    def test_absent_by_default(self, wg_conf):
        text = build(["8.8.8.8"], wg_conf)
        assert "ExcludedApplications" not in text
        assert "IncludedApplications" not in text

    def test_excluded_lands_in_interface_section(self, wg_conf):
        """Android читает списки приложений только из [Interface]; в [Peer] они игнорируются."""
        text = build(["8.8.8.8"], wg_conf, excluded_apps=["com.android.chrome"])
        interface, _, peer = text.partition("[Peer]")
        assert "ExcludedApplications = com.android.chrome" in interface
        assert "ExcludedApplications" not in peer

    def test_auto_excluded_adds_rustdesk_package(self, wg_conf):
        text = build(["8.8.8.8"], wg_conf, auto_excluded_apps=core.DEFAULT_EXCLUDED_APPS)
        assert "ExcludedApplications = com.carriez.flutter_hbb" in text

    def test_auto_excluded_merged_with_existing(self, android_conf):
        conf = android_conf(interface_extra="ExcludedApplications = com.android.chrome\n")
        text = build(["8.8.8.8"], conf, auto_excluded_apps=core.DEFAULT_EXCLUDED_APPS)
        assert "ExcludedApplications = com.android.chrome, com.carriez.flutter_hbb" in text

    def test_auto_excluded_not_duplicated(self, android_conf):
        conf = android_conf(interface_extra="excludedapplications = com.carriez.flutter_hbb\n")
        text = build(["8.8.8.8"], conf, auto_excluded_apps=core.DEFAULT_EXCLUDED_APPS)
        assert text.count("com.carriez.flutter_hbb") == 1

    def test_whitelist_removes_excluded_and_skips_rustdesk(self, android_conf):
        conf = android_conf(interface_extra="ExcludedApplications = com.android.chrome\n")
        text = build(
            ["8.8.8.8"],
            conf,
            included_apps=["org.telegram.messenger"],
            auto_excluded_apps=core.DEFAULT_EXCLUDED_APPS,
        )
        assert "IncludedApplications = org.telegram.messenger" in text
        assert "ExcludedApplications" not in text
        assert "com.carriez.flutter_hbb" not in text

    def test_blacklist_removes_existing_included(self, android_conf):
        conf = android_conf(interface_extra="IncludedApplications = com.android.chrome\n")
        text = build(["8.8.8.8"], conf, excluded_apps=["org.telegram.messenger"])
        assert "ExcludedApplications = org.telegram.messenger" in text
        assert "IncludedApplications" not in text

    def test_rustdesk_skipped_when_source_has_included(self, android_conf):
        conf = android_conf(interface_extra="IncludedApplications = com.android.chrome\n")
        text = build(["8.8.8.8"], conf, auto_excluded_apps=core.DEFAULT_EXCLUDED_APPS)
        assert "ExcludedApplications" not in text

    def test_both_package_lists_rejected(self, wg_conf):
        with pytest.raises(ValueError):
            build(
                ["8.8.8.8"],
                wg_conf,
                excluded_apps=["com.android.chrome"],
                included_apps=["org.telegram.messenger"],
            )


class TestPersistentKeepalive:
    def test_untouched_without_argument(self, android_conf):
        conf = android_conf(peer_extra="PersistentKeepalive = 0\n")
        assert "PersistentKeepalive = 0" in build(["8.8.8.8"], conf)

    def test_added_when_missing(self, wg_conf):
        text = build(["8.8.8.8"], wg_conf, keepalive=core.DEFAULT_KEEPALIVE)
        interface, _, peer = text.partition("[Peer]")
        assert "PersistentKeepalive = 25" in peer
        assert "PersistentKeepalive" not in interface

    def test_zero_replaced_without_duplicating_key(self, android_conf):
        conf = android_conf(peer_extra="persistentkeepalive = 0\n")
        text = build(["8.8.8.8"], conf, keepalive=25)
        assert "PersistentKeepalive = 25" in text
        assert text.lower().count("persistentkeepalive") == 1

    def test_read_missing_key(self, wg_conf):
        assert core.read_persistent_keepalive(wg_conf) is None

    @pytest.mark.parametrize("value", ["0", "abc", "", "-5", "99999"])
    def test_read_unusable_values_are_none(self, android_conf, value):
        conf = android_conf(peer_extra=f"PersistentKeepalive = {value}\n")
        assert core.read_persistent_keepalive(conf) is None

    def test_read_existing_value(self, android_conf):
        conf = android_conf(peer_extra="persistentkeepalive = 15\n")
        assert core.read_persistent_keepalive(conf) == 15

    def test_read_missing_file(self, tmp_path):
        assert core.read_persistent_keepalive(tmp_path / "nope.conf") is None


class TestValidateWireguardText:
    def test_generated_config_is_clean(self, wg_conf):
        text = build(["8.8.8.8"], wg_conf, obfuscate=True, bypass_lan=True)
        assert core.validate_wireguard_text(text) == []

    def test_missing_sections_flagged(self):
        problems = core.validate_wireguard_text("PrivateKey = abc\n")
        assert any("Interface" in p for p in problems)
        assert any("Peer" in p for p in problems)

    def test_line_outside_section(self):
        problems = core.validate_wireguard_text(
            "orphan\n[Interface]\nPrivateKey = a\n[Peer]\nAllowedIPs = 8.8.8.8\n"
        )
        assert any("orphan" in p for p in problems)

    def test_broken_line_flagged(self):
        problems = core.validate_wireguard_text(
            "[Interface]\nPrivateKey = a\n[Peer]\nAllowedIPs = 8.8.8.8\nбитая строка\n"
        )
        assert any("битая строка" in p for p in problems)

    def test_comments_allowed(self):
        text = "[Interface]\n# comment\nPrivateKey = a\n\n[Peer]\n; note\nAllowedIPs = 8.8.8.8\n"
        assert core.validate_wireguard_text(text) == []

    def test_missing_allowed_ips_flagged(self):
        problems = core.validate_wireguard_text("[Interface]\nPrivateKey = a\n[Peer]\nPublicKey = b\n")
        assert any("AllowedIPs" in p for p in problems)

    def test_invalid_address_flagged_ipv6_ok(self):
        problems = core.validate_wireguard_text(
            "[Interface]\nPrivateKey = a\n[Peer]\nAllowedIPs = 8.8.8.999, ::/0\n"
        )
        assert any("8.8.8.999" in p for p in problems)
        assert not any("::/0" in p for p in problems)

    def test_multi_peer_flagged(self):
        problems = core.validate_wireguard_text(
            "[Interface]\nPrivateKey = a\n[Peer]\nAllowedIPs = 8.8.8.8\n[Peer]\nAllowedIPs = 1.1.1.1\n"
        )
        assert problems

    @pytest.mark.parametrize("value", ["abc", "-5", "99999"])
    def test_invalid_keepalive_flagged(self, value):
        problems = core.validate_wireguard_text(
            f"[Interface]\nPrivateKey = a\n[Peer]\nAllowedIPs = 8.8.8.8\nPersistentKeepalive = {value}\n"
        )
        assert any(value in p for p in problems)

    def test_valid_keepalive_accepted(self):
        text = "[Interface]\nPrivateKey = a\n[Peer]\nAllowedIPs = 8.8.8.8\nPersistentKeepalive = 25\n"
        assert core.validate_wireguard_text(text) == []


class TestValidateAmneziaText:
    def test_valid_json(self):
        assert core.validate_amnezia_text('[{"hostname": "8.8.8.8", "ip": ""}]') == []

    def test_broken_json(self):
        assert core.validate_amnezia_text('[{"hostname": broken') != []


class TestMergeUnique:
    def test_merge_unique(self):
        assert core.merge_unique(["Chrome", "firefox"], ["CHROME", "discord", "Firefox"]) == [
            "Chrome",
            "firefox",
            "discord",
        ]
        assert core.merge_unique([], []) == []


class TestFormatters:
    def test_plaintext(self):
        assert core.format_plaintext(["8.8.8.8", "1.1.1.0/24"]) == "8.8.8.8\n1.1.1.0/24\n"

    def test_amnezia(self):
        assert json.loads(core.format_amnezia(["8.8.8.8"])) == [{"hostname": "8.8.8.8", "ip": ""}]

    def test_route(self):
        """CIDR разворачивается в MASK-октеты, одиночный адрес — в маску /32."""
        assert core.format_route(["173.194.187.0/24", "8.8.8.8", "199.201.0.0/16"]) == (
            "route ADD 173.194.187.0 MASK 255.255.255.0 0.0.0.0\n"
            "route ADD 8.8.8.8 MASK 255.255.255.255 0.0.0.0\n"
            "route ADD 199.201.0.0 MASK 255.255.0.0 0.0.0.0\n"
        )

    def test_route_newline_in_registry(self):
        """CRLF для .bat живёт в OUTPUT_FORMATS — единственном источнике правды для записи."""
        assert core.OUTPUT_FORMATS["route"].newline == "\r\n"
        assert core.OUTPUT_FORMATS["plaintext"].newline is None

    def test_route_roundtrip(self, tmp_path):
        """Текст format_route, записанный с CRLF, читается collect_ips без потерь."""
        file = tmp_path / "out.bat"
        original = ["173.194.187.0/24", "8.8.8.8"]
        with open(file, "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(core.format_route(original))
        assert core.collect_ips([file]) == original
