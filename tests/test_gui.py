import tkinter as tk
import types

import pytest

from vpn_i18n import language

pytest.importorskip("tkinter")
vpn_gui = pytest.importorskip("vpn_gui")


@pytest.fixture
def app():
    """Живое окно приложения; скип только при реальном отсутствии дисплея (TclError) —
    прочие ошибки конструктора должны валить тест, а не маскироваться под скип."""
    language.code = "ru"
    try:
        application = vpn_gui.VpnConfiguratorApp()
    except tk.TclError as exc:
        pytest.skip(f"no display available: {exc}")
    try:
        application.update()
        yield application
    finally:
        application._cancel_preview_job()
        application.destroy()


@pytest.fixture
def dialogs(monkeypatch):
    """Перехват модальных окон: успех/ошибка/подтверждение больше не пишутся в лог."""
    captured = {"error": [], "info": [], "warning": [], "askyesno": True}
    monkeypatch.setattr(
        vpn_gui.messagebox, "showerror", lambda _t, message: captured["error"].append(message)
    )
    monkeypatch.setattr(
        vpn_gui.messagebox, "showinfo", lambda _t, message: captured["info"].append(message)
    )
    monkeypatch.setattr(
        vpn_gui.messagebox, "showwarning", lambda _t, message: captured["warning"].append(message)
    )
    monkeypatch.setattr(vpn_gui.messagebox, "askyesno", lambda *a, **k: captured["askyesno"])
    return captured


def drop_event(path):
    return types.SimpleNamespace(data="{%s}" % str(path).replace("\\", "/"))


def test_blocks_visibility(app):
    """Файлы скрываются при «весь трафик», WireSock-рамка — при классическом WireGuard."""
    assert app.wg_files.winfo_ismapped()
    app.wg_route.set("all")
    app._on_wg_route_change()
    app.update()
    assert not app.wg_files.winfo_ismapped()

    assert not app.wiresock_frame.winfo_ismapped()
    app.wg_client.set(vpn_gui.CLIENT_WIRESOCK)
    app._on_wg_client_change()
    app.update()
    assert app.wiresock_frame.winfo_ismapped()


def test_client_choice_is_two_options(app, tmp_path, wg_conf, ips_file):
    """Классический WireGuard не добавляет WireSock-ключей, WireSock — добавляет."""
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])

    app.wg_client.set(vpn_gui.CLIENT_WIREGUARD)
    app._on_wg_client_change()
    app._refresh_preview()
    app.update()
    assert "ObfuscateKey" not in app.preview_box.get("1.0", "end")

    app.wg_client.set(vpn_gui.CLIENT_WIRESOCK)
    app._on_wg_client_change()
    app._refresh_preview()
    app.update()
    assert "ObfuscateKey" in app.preview_box.get("1.0", "end")


def test_file_list_remove_single(app, tmp_path, ips_file):
    """Мусорка убирает один файл из списка, остальные остаются."""
    other = tmp_path / "other.txt"
    other.write_text("9.9.9.9\n", encoding="utf-8")
    app.wg_files.add_paths([str(ips_file), str(other)])
    assert app.wg_files.paths == [str(ips_file), str(other)]

    app.wg_files.remove(str(ips_file))
    assert app.wg_files.paths == [str(other)]

    app.wg_files.clear()
    assert app.wg_files.paths == []


def test_file_list_rows_have_remove_buttons(app, ips_file):
    """На каждый файл в списке отрисована своя кнопка удаления."""
    app.wg_files.add_paths([str(ips_file)])
    app.update()
    buttons = [
        w
        for w in app.wg_files.list_frame.winfo_children()
        if isinstance(w, vpn_gui.ctk.CTkButton)
    ]
    assert len(buttons) == 1


def test_disallowed_ips_holds_paths_not_values(app, tmp_path, wg_conf, ips_file):
    """DisallowedIPs показывает пути файлов; адреса из них видны в предпросмотре
    и дополняют LAN-диапазоны чекбокса, а не заменяют их."""
    local = tmp_path / "local.txt"
    local.write_text("100.64.0.0/10\n", encoding="utf-8")

    app.wg_client.set(vpn_gui.CLIENT_WIRESOCK)
    app._on_wg_client_change()
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app.wg_exclude_lan.set(True)
    app.wg_disallowed_ips.add_paths([str(local)])
    assert app.wg_disallowed_ips.paths == [str(local)]

    app._refresh_preview()
    app.update()
    preview = app.preview_box.get("1.0", "end")
    assert "192.168.0.0/16" in preview
    assert "100.64.0.0/10" in preview


def test_exclude_lan_checkbox(app, wg_conf, ips_file):
    """Чекбокс по умолчанию выключен; включение добавляет LAN-диапазоны и rustdesk."""
    app.wg_client.set(vpn_gui.CLIENT_WIRESOCK)
    app._on_wg_client_change()
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()

    preview = app.preview_box.get("1.0", "end")
    assert "DisallowedIPs" not in preview
    assert "rustdesk" not in preview

    app.wg_exclude_lan.set(True)
    app._refresh_preview()
    app.update()
    preview = app.preview_box.get("1.0", "end")
    assert (
        "DisallowedIPs = 192.168.0.0/16, 172.16.0.0/12, 169.254.0.0/16, "
        "224.0.0.0/4, 255.255.255.255/32" in preview
    )
    assert "DisallowedApps = rustdesk" in preview
    assert "10.0.0.0/8" not in preview


def test_exclude_lan_whitelist_mode_keeps_ips_skips_rustdesk(app, tmp_path, wg_conf, ips_file):
    """Белый список: LAN-диапазоны остаются, rustdesk в DisallowedApps не добавляется."""
    apps_list = tmp_path / "apps.txt"
    apps_list.write_text("firefox\n", encoding="utf-8")

    app.wg_client.set(vpn_gui.CLIENT_WIRESOCK)
    app._on_wg_client_change()
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app.wg_exclude_lan.set(True)
    app.wg_app_mode.set(vpn_gui.APP_MODE_ALLOWED)
    app.wg_apps.add_paths([str(apps_list)])
    app._refresh_preview()
    app.update()

    preview = app.preview_box.get("1.0", "end")
    assert "DisallowedIPs = 192.168.0.0/16" in preview
    assert "AllowedApps = firefox" in preview
    assert "rustdesk" not in preview


def test_bypass_lan_checkbox(app, wg_conf, ips_file):
    """Чекбокс по умолчанию выключен; включение добавляет BypassLanTraffic = true."""
    app.wg_client.set(vpn_gui.CLIENT_WIRESOCK)
    app._on_wg_client_change()
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()
    assert "BypassLanTraffic" not in app.preview_box.get("1.0", "end")

    app.wg_bypass_lan.set(True)
    app._refresh_preview()
    app.update()
    assert "BypassLanTraffic = true" in app.preview_box.get("1.0", "end")


def test_classic_client_ignores_wiresock_checkboxes(app, wg_conf, ips_file):
    """Классический WireGuard: включённые чекбоксы WireSock не влияют на конфиг."""
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app.wg_exclude_lan.set(True)
    app.wg_bypass_lan.set(True)
    app._refresh_preview()
    app.update()
    preview = app.preview_box.get("1.0", "end")
    assert "DisallowedIPs" not in preview
    assert "BypassLanTraffic" not in preview
    assert "rustdesk" not in preview


def test_preview_wheel_scrolls_box_only(app):
    """Колесо над предпросмотром скроллит его и возвращает 'break' — страница не дёргается."""
    app._set_preview("\n".join(f"10.0.0.{i}" for i in range(200)))
    app.update()
    box = app._preview_textbox()
    assert box.yview()[0] == 0.0
    result = app._on_preview_wheel(types.SimpleNamespace(delta=-120))
    assert result == "break"
    assert box.yview()[0] > 0.0


def test_invalid_manual_edit_asks_before_save(app, tmp_path, wg_conf, ips_file, dialogs, monkeypatch):
    """Кривая ручная правка конфига: перед сохранением задаётся вопрос; отказ отменяет запись."""
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()
    app.preview_box.insert("end", "оборванная строка без знака равно\n")
    app.update()

    questions = []

    def ask(title, message):
        questions.append(message)
        return False

    monkeypatch.setattr(vpn_gui.messagebox, "askyesno", ask)
    out = tmp_path / "out.conf"
    app.wg_dst.set(str(out))
    app._execute(app._run_wireguard)
    assert questions and "оборванная строка" in questions[0]
    assert not out.exists()


def test_valid_manual_edit_saved_without_question(app, tmp_path, wg_conf, ips_file, monkeypatch, dialogs):
    """Корректная ручная правка сохраняется без вопроса валидации."""
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()
    app.preview_box.insert("end", "PersistentKeepalive = 25\n")
    app.update()

    def fail(*a, **k):
        raise AssertionError("no dialogs expected")

    monkeypatch.setattr(vpn_gui.messagebox, "askyesno", fail)
    out = tmp_path / "out.conf"
    app.wg_dst.set(str(out))
    app._execute(app._run_wireguard)
    assert "PersistentKeepalive = 25" in out.read_text(encoding="utf-8")


def test_apps_from_binary_and_text_list(app, tmp_path, wg_conf, ips_file):
    """Приложения берутся и из исполняемого файла, и из текстового списка имён."""
    apps_list = tmp_path / "apps.txt"
    apps_list.write_text("chrome, telegram\n", encoding="utf-8")
    binary = tmp_path / "my-daemon"
    binary.write_bytes(b"\x7fELF\x02\x01\x01\x00\xff\xfe\xfd")

    app.wg_client.set(vpn_gui.CLIENT_WIRESOCK)
    app._on_wg_client_change()
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app.wg_apps.add_paths([str(apps_list), str(binary)])
    app._refresh_preview()
    app.update()

    preview = app.preview_box.get("1.0", "end")
    assert "DisallowedApps = chrome, telegram, my-daemon" in preview
    assert "rustdesk" not in preview

    app.wg_app_mode.set(vpn_gui.APP_MODE_ALLOWED)
    app._refresh_preview()
    app.update()
    preview = app.preview_box.get("1.0", "end")
    assert "AllowedApps = chrome, telegram, my-daemon" in preview
    assert "DisallowedApps" not in preview


def test_run_wireguard_shows_success_dialog(app, tmp_path, wg_conf, ips_file, dialogs):
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    out = tmp_path / "out.conf"
    app.wg_dst.set(str(out))
    app._execute(app._run_wireguard)

    assert "AllowedIPs = 8.8.8.8, 1.1.1.0/24" in out.read_text(encoding="utf-8")
    assert dialogs["info"] and str(out) in dialogs["info"][0]
    assert dialogs["error"] == []


def test_run_reports_error_dialog(app, tmp_path, dialogs):
    """Незаполненная форма: ошибка показывается окном, а не молча."""
    app.wg_dst.set(str(tmp_path / "out.conf"))
    app._execute(app._run_wireguard)
    assert dialogs["error"] and ".conf" in dialogs["error"][0]


def test_run_reports_os_error_dialog(app, tmp_path, wg_conf, ips_file, dialogs):
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app.wg_dst.set(str(tmp_path / "no_such_dir" / "out.conf"))
    app._execute(app._run_wireguard)
    assert dialogs["error"] and "файловой операции" in dialogs["error"][0]


def test_bad_file_error_surfaces_on_run(app, tmp_path, wg_conf, dialogs):
    """Битый файл: предпросмотр молча пуст, а причина всплывает окном при сохранении."""
    bad = tmp_path / "bad.txt"
    bad.write_bytes("# список\n8.8.8.8\n".encode("cp1251"))
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(bad)])
    app._refresh_preview()
    app.update()
    assert app._preview_is_placeholder

    app.wg_dst.set(str(tmp_path / "out.conf"))
    app._execute(app._run_wireguard)
    assert dialogs["error"] and "кодировк" in dialogs["error"][0].lower()


def test_report_callback_exception_shows_dialog(app, dialogs):
    """Исключение из Tk-колбэка идёт в окно, а не в None-stderr windowed-бинаря."""
    import vpn_configurator as core

    app.report_callback_exception(ValueError, ValueError("boom"), None)
    assert "boom" in dialogs["error"][0]

    app.report_callback_exception(OSError, OSError("disk full"), None)
    assert "файловой операции" in dialogs["error"][1]

    app.report_callback_exception(
        core.VpnConfiguratorError, core.VpnConfiguratorError("нет секции"), None
    )
    assert "нет секции" in dialogs["error"][2]


def test_overwrite_declined_leaves_file(app, tmp_path, wg_conf, ips_file, dialogs):
    out = tmp_path / "out.conf"
    out.write_text("ORIGINAL", encoding="utf-8")
    dialogs["askyesno"] = False

    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app.wg_dst.set(str(out))
    app._execute(app._run_wireguard)
    assert out.read_text(encoding="utf-8") == "ORIGINAL"


def test_overwrite_skipped_after_save_dialog(app, tmp_path, wg_conf, ips_file, monkeypatch, dialogs):
    """Путь, подтверждённый системным «Сохранить как…», не переспрашивается повторно."""
    out = tmp_path / "out.conf"
    out.write_text("ORIGINAL", encoding="utf-8")
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    monkeypatch.setattr(vpn_gui.filedialog, "asksaveasfilename", lambda **k: str(out))
    app.wg_dst.browse()

    def fail(*a, **k):
        raise AssertionError("askyesno should not be called")

    monkeypatch.setattr(vpn_gui.messagebox, "askyesno", fail)
    app._execute(app._run_wireguard)
    assert "AllowedIPs = 8.8.8.8" in out.read_text(encoding="utf-8")


def test_manual_preview_edit_saved_verbatim(app, tmp_path, wg_conf, ips_file, dialogs):
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()
    assert not app._preview_dirty

    app.preview_box.insert("end", "# manual edit\n")
    app.update()
    assert app._preview_dirty
    assert "вручную" in app.preview_label.cget("text")

    out = tmp_path / "manual.conf"
    app.wg_dst.set(str(out))
    app._execute(app._run_wireguard)
    assert "# manual edit" in out.read_text(encoding="utf-8")
    assert not app._preview_dirty


def test_form_change_regenerates_preview(app, wg_conf, ips_file):
    """Онлайн-модель: правка формы перегенерирует предпросмотр поверх ручных правок."""
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()

    app.preview_box.insert("end", "# edit\n")
    app.update()
    assert app._preview_dirty

    app._refresh_preview()
    app.update()
    assert "# edit" not in app.preview_box.get("1.0", "end")
    assert not app._preview_dirty


def test_active_tab_click_keeps_manual_edits(app, wg_conf, ips_file):
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()
    app.preview_box.insert("end", "# manual edit\n")
    app.update()

    app._select_page("wireguard")
    app.update()
    assert "# manual edit" in app.preview_box.get("1.0", "end")
    assert app._preview_dirty


def test_dirty_tab_switch_declined_keeps_edits(app, wg_conf, ips_file, dialogs):
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()
    app.preview_box.insert("end", "# edit\n")
    app.update()
    assert app._preview_dirty

    dialogs["askyesno"] = False
    app._select_page("merge")
    assert app.current_page == "wireguard"
    assert "# edit" in app.preview_box.get("1.0", "end")


def test_all_traffic_generates_config(app, tmp_path, wg_conf, dialogs):
    app.wg_src.set(str(wg_conf))
    app.wg_route.set("all")
    app._on_wg_route_change()
    out = tmp_path / "out.conf"
    app.wg_dst.set(str(out))
    app._execute(app._run_wireguard)
    assert "AllowedIPs = 0.0.0.0/0, ::/0" in out.read_text(encoding="utf-8")


def test_run_regenerates_when_preview_cleared(app, tmp_path, wg_conf, ips_file, dialogs):
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()
    app.preview_box.delete("1.0", "end")
    app.update()

    out = tmp_path / "out.conf"
    app.wg_dst.set(str(out))
    app._execute(app._run_wireguard)
    assert "AllowedIPs = 8.8.8.8, 1.1.1.0/24" in out.read_text(encoding="utf-8")


def test_flush_preview_saves_current_form(app, tmp_path, wg_conf, ips_file, dialogs):
    """Сохранение до срабатывания дебаунса берёт актуальные данные формы."""
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()

    other = tmp_path / "other.txt"
    other.write_text("9.9.9.9\n", encoding="utf-8")
    app.wg_files.clear()
    app.wg_files.add_paths([str(other)])
    app.schedule_preview()

    out = tmp_path / "out.conf"
    app.wg_dst.set(str(out))
    app._execute(app._run_wireguard)
    assert "AllowedIPs = 9.9.9.9" in out.read_text(encoding="utf-8")


def test_merge_route_run(app, tmp_path, ips_file, dialogs):
    app._select_page("merge")
    app.merge_files.add_paths([str(ips_file)])
    app.merge_format.set("route")
    app._refresh_preview()
    app.update()

    app.merge_dst.set(str(tmp_path / "routes"))
    app._execute(app._run_merge)
    data = (tmp_path / "routes.bat").read_bytes().decode("utf-8")
    assert "route ADD 8.8.8.8 MASK 255.255.255.255 0.0.0.0\r\n" in data


def test_merge_run_regenerates_when_preview_cleared(app, tmp_path, ips_file, dialogs):
    app._select_page("merge")
    app.merge_files.add_paths([str(ips_file)])
    app.merge_format.set("plaintext")
    app._refresh_preview()
    app.update()
    app.preview_box.delete("1.0", "end")
    app.update()

    out = tmp_path / "merged.txt"
    app.merge_dst.set(str(out))
    app._execute(app._run_merge)
    assert out.read_text(encoding="utf-8") == "8.8.8.8\n1.1.1.0/24\n"


def test_syntax_highlight_applied(app, wg_conf, ips_file):
    """Подсветка расставляет теги: секция, ключ, IP, комментарий."""
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    app._refresh_preview()
    app.update()

    box = app._preview_textbox()
    for tag in ("section", "key", "number"):
        assert box.tag_ranges(tag), f"нет подсветки для тега {tag}"


def test_syntax_highlight_skipped_on_huge_text(app):
    """На огромном списке подсветка пропускается, чтобы не тормозить ввод."""
    app._set_preview("\n".join(f"10.0.{i // 256}.{i % 256}" for i in range(vpn_gui.SYNTAX_MAX_LINES + 10)))
    app.update()
    assert not app._preview_textbox().tag_ranges("number")


def test_placeholder_restored_after_focus_without_input(app):
    assert app._preview_is_placeholder
    app._on_preview_focus(None)
    app.update()
    assert not app._preview_is_placeholder
    app._on_preview_focus_out(None)
    app.update()
    assert app._preview_is_placeholder


def test_cached_parse_failure_reraised_without_reparse(app, tmp_path, monkeypatch):
    """Битый набор кэшируется: повторное обращение бросает ту же ошибку, не перепарсивая файл."""
    bad = tmp_path / "bad.txt"
    bad.write_bytes("# список\n8.8.8.8\n".encode("cp1251"))
    with pytest.raises(vpn_gui.VpnConfiguratorError):
        app._collect_ips_cached([str(bad)])

    calls = []
    monkeypatch.setattr(vpn_gui, "collect_ips", lambda *a, **k: calls.append(1))
    with pytest.raises(vpn_gui.VpnConfiguratorError):
        app._collect_ips_cached([str(bad)])
    assert calls == []


def test_ips_cache_lru_eviction(app, tmp_path):
    """Обращение к набору обновляет его позицию: горячий набор не вытесняется раньше одноразовых."""
    files = []
    for i in range(vpn_gui.IPS_CACHE_MAX + 1):
        file = tmp_path / f"ips{i}.txt"
        file.write_text("8.8.8.8\n", encoding="utf-8")
        files.append(str(file))

    hot = files[0]
    app._collect_ips_cached([hot])
    for path in files[1:]:
        app._collect_ips_cached([path])
        app._collect_ips_cached([hot])

    assert (hot,) in app._ips_cache
    assert len(app._ips_cache) <= vpn_gui.IPS_CACHE_MAX


def test_ips_cache_invalidated_on_file_change(app, tmp_path):
    file = tmp_path / "ips.txt"
    file.write_text("8.8.8.8\n", encoding="utf-8")
    assert app._collect_ips_cached([str(file)]) == ["8.8.8.8"]

    import os as os_module

    file.write_text("1.1.1.1\n", encoding="utf-8")
    stat = os_module.stat(file)
    os_module.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert app._collect_ips_cached([str(file)]) == ["1.1.1.1"]


def test_quoted_path_stripped(app):
    """Windows «Копировать как путь» вставляет путь в кавычках — GUI их снимает."""
    app.wg_src.entry.insert(0, '"C:/some/wg.conf"')
    assert app.wg_src.get() == "C:/some/wg.conf"


def test_language_switch_in_place(app, wg_conf, ips_file):
    """Смена языка обновляет тексты без пересоздания виджетов и без потери ввода."""
    app.wg_src.set(str(wg_conf))
    app.wg_files.add_paths([str(ips_file)])
    widget_ids = (id(app.wg_src), id(app.merge_files), id(app.preview_box))

    app._on_language_change("English")
    app.update()
    assert language.code == "en"
    assert (id(app.wg_src), id(app.merge_files), id(app.preview_box)) == widget_ids
    assert app.nav_buttons["merge"].cget("text") == "Merge files"
    assert app.wg_src.get() == str(wg_conf)
    assert app.wg_files.paths == [str(ips_file)]
