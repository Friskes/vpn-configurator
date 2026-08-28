import pytest


def test_gui_module_imports():
    """Ловит поломку импортов vpn_gui: у windowed-бинаря нет консоли, и битый GUI
    без этого теста дошёл бы до релиза молчаливым крэшем."""
    pytest.importorskip("tkinter")
    import vpn_gui  # noqa: F401

    assert callable(vpn_gui.run_gui)
