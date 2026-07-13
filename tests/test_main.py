import builtins
import types

import pytest

import vpn_configurator as core


def test_main_runs_gui(monkeypatch):
    called = []
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "vpn_gui":
            module = types.ModuleType("vpn_gui")
            module.run_gui = lambda: called.append("gui")
            return module
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    core.main()
    assert called == ["gui"]


def test_main_reports_startup_error(monkeypatch):
    """Падение GUI: ошибка показывается окном (консоли у windowed-бинаря нет) и код возврата 1."""
    errors = []
    monkeypatch.setattr(core, "_show_startup_error", errors.append)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "vpn_gui":
            module = types.ModuleType("vpn_gui")
            module.run_gui = lambda: (_ for _ in ()).throw(RuntimeError("no display"))
            return module
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(SystemExit) as exc_info:
        core.main()
    assert exc_info.value.code == 1
    assert errors and "no display" in errors[0]


def test_show_startup_error_swallows_tk_failure(monkeypatch):
    """Если и tkinter недоступен, показ ошибки не должен ронять процесс вторым трейсбеком."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tkinter":
            raise ImportError("no tkinter")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    core._show_startup_error("boom")


def test_module_has_no_cli_surface():
    """CLI выпилен полностью: ни run_cli, ни input-хелперов в модуле быть не должно."""
    for name in ("run_cli", "cli_wireguard", "cli_merge", "input_choice", "show_console_window"):
        assert not hasattr(core, name)
