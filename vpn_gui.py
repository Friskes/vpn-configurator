"""Графический интерфейс VPN Configurator (CustomTkinter): две функции, ru/en,
drag & drop и редактируемый предпросмотр результата с подсветкой синтаксиса."""

import os
import re
import tkinter.font as tkfont
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from vpn_configurator import (
    ALL_TRAFFIC_IPS,
    DEFAULT_KEEPALIVE,
    LAN_EXCLUDE_IPS,
    MAX_KEEPALIVE,
    OUTPUT_FORMATS,
    VpnConfiguratorError,
    build_wireguard_conf,
    collect_app_names,
    collect_ips,
    exclude_ips,
    merge_unique,
    parse_app_names,
    read_allowed_ips,
    read_endpoint_ip,
    read_persistent_keepalive,
    validate_amnezia_text,
    validate_wireguard_text,
)
from vpn_i18n import LANGUAGE_NAMES, language, tr

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = TkinterDnD = None

MERGE_UI = {
    "plaintext": ("gui_fmt_plaintext", "merged.txt", "gui_filetype_txt"),
    "amnezia": ("gui_fmt_amnezia", "merged.json", "gui_filetype_json"),
    "route": ("gui_fmt_route", "routes.bat", "gui_filetype_bat"),
}

CLIENT_WIREGUARD = "wireguard"
CLIENT_WIRESOCK = "wiresock"
CLIENT_ANDROID = "android"
APP_MODE_DISALLOWED = "disallowed"
APP_MODE_ALLOWED = "allowed"
APP_MODE_EXCLUDED = "excluded"
APP_MODE_INCLUDED = "included"

IPS_CACHE_MAX = 16
SYNTAX_MAX_LINES = 3000

MONO_FONT_CANDIDATES = (
    "Cascadia Mono",
    "Cascadia Code",
    "Consolas",
    "JetBrains Mono",
    "SF Mono",
    "Menlo",
    "DejaVu Sans Mono",
    "Courier New",
)

SYNTAX_PATTERNS = (
    ("section", re.compile(r"^[ \t]*\[[^\]]+\]", re.MULTILINE)),
    ("key", re.compile(r"^[ \t]*[A-Za-z][A-Za-z0-9]*(?=[ \t]*=)", re.MULTILINE)),
    ("keyword", re.compile(r"\b(?:route|add|mask|delete)\b", re.IGNORECASE)),
    ("string", re.compile(r'"[^"\n]*"')),
    ("number", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b")),
    ("comment", re.compile(r"(?m)^[ \t]*(?:#|;|//).*$|(?<=\s)(?:#|//).*$")),
)

SYNTAX_COLORS = {
    "dark": {
        "section": "#4ec9b0",
        "key": "#9cdcfe",
        "keyword": "#569cd6",
        "string": "#ce9178",
        "number": "#b5cea8",
        "comment": "#6a9955",
    },
    "light": {
        "section": "#267f99",
        "key": "#0451a5",
        "keyword": "#0000ff",
        "string": "#a31515",
        "number": "#098658",
        "comment": "#008000",
    },
}


def _file_signature(path: str) -> tuple[str, int, int]:
    """Сигнатура файла для инвалидации кэша: путь, mtime и размер за один вызов os.stat."""
    st = os.stat(path)
    return (path, st.st_mtime_ns, st.st_size)


def _mono_family() -> str:
    """Первый доступный читаемый моноширинный шрифт (как в редакторах кода)."""
    families = set(tkfont.families())
    for name in MONO_FONT_CANDIDATES:
        if name in families:
            return name
    return tkfont.nametofont("TkFixedFont").actual("family")


class Tooltip:
    """Всплывающая подсказка по наведению; текст берётся через tr() в момент показа,
    поэтому смена языка подхватывается без перерегистрации."""

    def __init__(self, widget, text_key: str, delay_ms: int = 400) -> None:
        self.widget = widget
        self.text_key = text_key
        self.delay_ms = delay_ms
        self._job: str | None = None
        self._window = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event) -> None:
        self._cancel()
        self._job = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None

    def _show(self) -> None:
        import tkinter as tk

        self._job = None
        if self._window is not None:
            return
        self._window = tk.Toplevel(self.widget)
        self._window.wm_overrideredirect(True)
        self._window.wm_geometry(
            f"+{self.widget.winfo_rootx() + 16}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 6}"
        )
        dark = ctk.get_appearance_mode() == "Dark"
        label = tk.Label(
            self._window,
            text=tr(self.text_key),
            justify="left",
            font=(tkfont.nametofont("TkDefaultFont").actual("family"), 12),
            background="#2b2b2b" if dark else "#ffffe0",
            foreground="#e0e0e0" if dark else "#333333",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
        )
        label.pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None


class FilePickerRow(ctk.CTkFrame):
    """Подпись, поле пути и кнопка выбора файла; drag & drop опционален.

    dialog_options — callable, отдающий параметры файлового диалога в момент клика
    (filetypes, defaultextension, initialfile), т.к. они зависят от текущего состояния формы."""

    def __init__(
        self,
        master: ctk.CTkFrame,
        app: "VpnConfiguratorApp",
        label_key: str,
        mode: str,
        dialog_options: Callable[[], dict],
        dnd: bool = True,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.mode = mode
        self.dialog_options = dialog_options
        self.dialog_confirmed_path: str | None = None

        if mode == "open":
            placeholder_key, button_key = "gui_placeholder_file", "gui_choose_file"
        else:
            placeholder_key = "gui_placeholder_save_dnd" if dnd else "gui_placeholder_save"
            button_key = "gui_save_as"

        self.grid_columnconfigure(0, weight=1)
        label = ctk.CTkLabel(self, anchor="w")
        label.grid(row=0, column=0, columnspan=2, sticky="w")
        app.register_i18n(label, label_key)

        self.entry = ctk.CTkEntry(self)
        self.entry.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(2, 0))
        app.register_i18n(self.entry, placeholder_key, "placeholder_text")
        self.entry.bind("<KeyRelease>", self._on_manual_edit)

        button = ctk.CTkButton(self, width=130, command=self.browse)
        button.grid(row=1, column=1, pady=(2, 0))
        app.register_i18n(button, button_key)

        if app.dnd_enabled and dnd:
            self.entry.drop_target_register(DND_FILES)
            self.entry.dnd_bind("<<Drop>>", self._on_drop)

    def _on_manual_edit(self, _event) -> None:
        self.dialog_confirmed_path = None
        if self.mode == "open":
            self.app.schedule_preview()

    def _on_drop(self, event) -> None:
        paths = self.tk.splitlist(event.data)
        if paths:
            self.set(paths[0])

    def browse(self) -> None:
        options = self.dialog_options()
        if self.mode == "open":
            path = filedialog.askopenfilename(filetypes=options.get("filetypes", []))
        else:
            path = filedialog.asksaveasfilename(**options)
        if path:
            self.set(path)
            if self.mode == "save":
                self.dialog_confirmed_path = path

    def set(self, path: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, path)
        self.dialog_confirmed_path = None
        if self.mode == "open":
            self.app.schedule_preview()

    def get(self) -> str:
        return self.entry.get().strip().strip('"')


class FileListPicker(ctk.CTkFrame):
    """Список выбранных файлов: строка на файл с кнопкой удаления, drag & drop,
    «Добавить файлы…» и «Очистить всё». Значения из путей извлекает вызывающий код."""

    def __init__(
        self,
        master: ctk.CTkFrame,
        app: "VpnConfiguratorApp",
        label_key: str,
        hint_key: str,
        filetypes: Callable[[], list[tuple[str, str]]],
        list_height: int = 120,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.paths: list[str] = []
        self.filetypes = filetypes

        self.grid_columnconfigure(0, weight=1)
        label = ctk.CTkLabel(self, anchor="w")
        label.grid(row=0, column=0, columnspan=2, sticky="w")
        app.register_i18n(label, label_key)

        hint = ctk.CTkLabel(
            self,
            anchor="w",
            justify="left",
            wraplength=580,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 2))
        app.register_i18n(hint, hint_key)

        self.list_frame = ctk.CTkScrollableFrame(self, height=list_height, fg_color=("gray92", "gray17"))
        self.list_frame.grid(row=2, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.add_button = ctk.CTkButton(self, width=150, command=self.add_files)
        self.add_button.grid(row=2, column=1, sticky="n")
        app.register_i18n(self.add_button, "gui_add_files")

        self.clear_button = ctk.CTkButton(
            self,
            width=150,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray80"),
            command=self.clear,
        )
        self.clear_button.grid(row=3, column=1, sticky="n", pady=(6, 0))
        app.register_i18n(self.clear_button, "gui_clear")

        if app.dnd_enabled:
            target = getattr(self.list_frame, "_parent_canvas", self.list_frame)
            target.drop_target_register(DND_FILES)
            target.dnd_bind("<<Drop>>", self._on_drop)

        self._refresh()

    def _on_drop(self, event) -> None:
        self.add_paths(self.tk.splitlist(event.data))

    def add_files(self) -> None:
        self.add_paths(filedialog.askopenfilenames(filetypes=self.filetypes()))

    def add_paths(self, paths) -> None:
        for path in paths:
            if path not in self.paths:
                self.paths.append(path)
        self._refresh()
        self.app.schedule_preview()

    def remove(self, path: str) -> None:
        if path in self.paths:
            self.paths.remove(path)
            self._refresh()
            self.app.schedule_preview()

    def clear(self) -> None:
        self.paths = []
        self._refresh()
        self.app.schedule_preview()

    def refresh_texts(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()

        if not self.paths:
            hint = ctk.CTkLabel(
                self.list_frame, anchor="w", text_color=("gray50", "gray55"), text=tr("gui_drop_hint")
            )
            hint.grid(row=0, column=0, sticky="w", padx=6, pady=4)
            return

        for row, path in enumerate(self.paths):
            name = ctk.CTkLabel(self.list_frame, anchor="w", text=path)
            name.grid(row=row, column=0, sticky="ew", padx=(6, 4), pady=1)

            remove_button = ctk.CTkButton(
                self.list_frame,
                text="✕",
                width=26,
                height=22,
                fg_color="transparent",
                hover_color=("gray80", "gray30"),
                text_color=("gray30", "gray70"),
                command=lambda p=path: self.remove(p),
            )
            remove_button.grid(row=row, column=1, sticky="e", padx=(0, 4), pady=1)


class TextListBox(ctk.CTkFrame):
    """Подпись, подсказка и многострочное поле для списка, который печатают руками:
    имя Android-пакета неоткуда взять перетаскиванием файла, как имя .exe."""

    def __init__(
        self,
        master: ctk.CTkFrame,
        app: "VpnConfiguratorApp",
        label_key: str,
        hint_key: str,
        height: int = 90,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(self, anchor="w")
        label.grid(row=0, column=0, sticky="w")
        app.register_i18n(label, label_key)

        hint = ctk.CTkLabel(
            self,
            anchor="w",
            justify="left",
            wraplength=580,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        hint.grid(row=1, column=0, sticky="w", pady=(0, 2))
        app.register_i18n(hint, hint_key)

        self.textbox = ctk.CTkTextbox(self, height=height, wrap="none")
        self.textbox.grid(row=2, column=0, sticky="ew")
        self.textbox.bind("<KeyRelease>", lambda _event: app.schedule_preview())

    def get(self) -> str:
        return self.textbox.get("1.0", "end-1c")

    def set(self, text: str) -> None:
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)


class VpnConfiguratorApp(ctk.CTk):
    """Главное окно: вкладки и переключатели в верхней полосе, настройки страницы,
    ниже — редактируемый предпросмотр результата с подсветкой синтаксиса."""

    def __init__(self) -> None:
        super().__init__()
        self.dnd_enabled = False
        if TkinterDnD is not None:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_enabled = True
            except RuntimeError:
                pass

        self.geometry("1000x700")
        self.minsize(820, 620)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.appearance = "system"
        self.current_page = "wireguard"
        self._i18n_registry: list[tuple[object, str, str]] = []
        self._file_lists: list[FileListPicker] = []
        self._preview_job: str | None = None
        self._preview_dirty = False
        self._preview_is_placeholder = True
        self._ips_cache: dict[tuple, tuple] = {}
        self._keepalive_source: str | None = None

        self.title(tr("app_title"))
        self.pages: dict[str, ctk.CTkFrame] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self._mono_font = ctk.CTkFont(family=_mono_family(), size=13)

        self._build_topbar()
        self.content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        # CTkScrollableFrame на Windows ставит yscrollincrement=1px — колесо скроллит еле-еле
        self.content._parent_canvas.configure(yscrollincrement=6)
        self._build_wireguard_page()
        self._build_merge_page()
        self._build_preview_area()
        self._select_page(self.current_page, initial=True)

        if not self.dnd_enabled:
            messagebox.showwarning(tr("app_title"), tr("gui_dnd_unavailable"))

    def report_callback_exception(self, exc_type, exc_value, _exc_tb) -> None:
        """Ловит исключения из Tk-колбэков (after, drag & drop, события) в окно ошибки:
        у windowed-бинаря нет stderr, и дефолтный обработчик Tkinter упал бы на записи в None."""
        messagebox.showerror(tr("gui_error_title"), self._error_message(exc_value))

    def _error_message(self, exc: BaseException) -> str:
        """Единая классификация исключения в текст для всех точек обработки ошибок."""
        if isinstance(exc, VpnConfiguratorError):
            return str(exc)
        if isinstance(exc, OSError):
            return tr("msg_file_op_error").format(error=exc)
        return tr("msg_unexpected_error").format(error=f"{type(exc).__name__}: {exc}")

    def register_i18n(self, widget, key: str, option: str = "text") -> None:
        """Регистрирует виджет для обновления текста при смене языка (без пересоздания UI)."""
        self._i18n_registry.append((widget, key, option))
        widget.configure(**{option: tr(key)})

    def _build_topbar(self) -> None:
        topbar = ctk.CTkFrame(self, corner_radius=0)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(2, weight=1)

        nav_items = [("wireguard", "gui_nav_wireguard"), ("merge", "gui_nav_merge")]
        for column, (page_name, title_key) in enumerate(nav_items):
            button = ctk.CTkButton(
                topbar,
                corner_radius=6,
                height=32,
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray75", "gray28"),
                command=lambda name=page_name: self._select_page(name),
            )
            button.grid(row=0, column=column, padx=(12 if column == 0 else 4, 4), pady=8)
            self.register_i18n(button, title_key)
            self.nav_buttons[page_name] = button

        self.language_menu = ctk.CTkOptionMenu(
            topbar, width=110, values=list(LANGUAGE_NAMES.values()), command=self._on_language_change
        )
        self.language_menu.set(LANGUAGE_NAMES[language.code])
        self.language_menu.grid(row=0, column=3, padx=4, pady=8)

        self.theme_menu = ctk.CTkOptionMenu(topbar, width=120, command=self._on_theme_change)
        self.theme_menu.grid(row=0, column=4, padx=(4, 12), pady=8)
        self._refresh_theme_menu()

    def _theme_names(self) -> dict[str, str]:
        return {
            tr("gui_theme_system"): "system",
            tr("gui_theme_light"): "light",
            tr("gui_theme_dark"): "dark",
        }

    def _refresh_theme_menu(self) -> None:
        names = self._theme_names()
        self.theme_menu.configure(values=list(names))
        self.theme_menu.set(next(name for name, mode in names.items() if mode == self.appearance))

    def _on_theme_change(self, value: str) -> None:
        self.appearance = self._theme_names()[value]
        ctk.set_appearance_mode(self.appearance)
        self._apply_syntax_colors()
        self._highlight_preview()

    def _on_language_change(self, value: str) -> None:
        new_code = next((code for code, name in LANGUAGE_NAMES.items() if name == value), None)
        if new_code and new_code != language.code:
            language.code = new_code
            self._apply_language()

    def _apply_language(self) -> None:
        """Обновляет тексты на месте: виджеты не пересоздаются, ввод не трогается."""
        self.title(tr("app_title"))
        for widget, key, option in self._i18n_registry:
            widget.configure(**{option: tr(key)})
        self._refresh_theme_menu()
        self._update_preview_label()
        for file_list in self._file_lists:
            file_list.refresh_texts()
        if self._preview_is_placeholder:
            self._refresh_preview()

    def _select_page(self, name: str, initial: bool = False) -> None:
        if not initial and name == self.current_page:
            return
        if self._preview_dirty:
            self._cancel_preview_job()
            if not messagebox.askyesno(
                tr("gui_preview_discard_title"), tr("gui_preview_discard_question")
            ):
                return
            self._reset_preview_dirty()
        self.current_page = name
        for page_name, button in self.nav_buttons.items():
            active = page_name == name
            button.configure(fg_color=("gray75", "gray28") if active else "transparent")
        for page_name, page in self.pages.items():
            if page_name == name:
                page.grid(row=0, column=0, sticky="nsew", padx=24, pady=(16, 0))
            else:
                page.grid_forget()
        self._refresh_preview()

    def _build_preview_area(self) -> None:
        separator = ctk.CTkFrame(
            self.content, height=2, corner_radius=0, fg_color=("gray70", "gray30")
        )
        separator.grid(row=1, column=0, sticky="ew", padx=24, pady=(10, 0))

        self.preview_label = ctk.CTkLabel(
            self.content, font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        )
        self.preview_label.grid(row=2, column=0, sticky="w", padx=24, pady=(6, 0))

        self.preview_box = ctk.CTkTextbox(self.content, height=360, wrap="none", font=self._mono_font)
        self.preview_box.grid(row=3, column=0, sticky="nsew", padx=24, pady=(4, 12))
        self.preview_box.tag_config("placeholder", foreground="#808080")
        self.preview_box.bind("<<Modified>>", self._on_preview_modified)
        self.preview_box.bind("<FocusIn>", self._on_preview_focus)
        self.preview_box.bind("<FocusOut>", self._on_preview_focus_out)
        self._preview_textbox().bind("<MouseWheel>", self._on_preview_wheel)

        self._apply_syntax_colors()
        self._update_preview_label()

    def _apply_syntax_colors(self) -> None:
        mode = ctk.get_appearance_mode().lower()
        colors = SYNTAX_COLORS.get(mode, SYNTAX_COLORS["dark"])
        box = self._preview_textbox()
        for tag, color in colors.items():
            box.tag_config(tag, foreground=color)
        box.tag_raise("comment")

    def _highlight_preview(self) -> None:
        """Подсветка синтаксиса собственными regex-тегами: без внешних зависимостей,
        на огромных списках пропускается, чтобы не тормозить ввод."""
        box = self._preview_textbox()
        for tag, _pattern in SYNTAX_PATTERNS:
            box.tag_remove(tag, "1.0", "end")
        if self._preview_is_placeholder:
            return
        text = box.get("1.0", "end-1c")
        if text.count("\n") > SYNTAX_MAX_LINES:
            return
        for tag, pattern in SYNTAX_PATTERNS:
            for match in pattern.finditer(text):
                box.tag_add(tag, f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def _create_page(self, name: str, title_key: str, subtitle_key: str) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(page, font=ctk.CTkFont(size=20, weight="bold"), anchor="w")
        title.grid(row=0, column=0, sticky="w")
        self.register_i18n(title, title_key)

        subtitle = ctk.CTkLabel(
            page, anchor="w", justify="left", wraplength=640, text_color=("gray30", "gray70")
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(2, 10))
        self.register_i18n(subtitle, subtitle_key)

        self.pages[name] = page
        return page

    def _create_run_button(
        self, page: ctk.CTkFrame, row: int, text_key: str, command: Callable[[], str | None]
    ) -> None:
        button = ctk.CTkButton(page, height=38, width=200, command=lambda: self._execute(command))
        button.grid(row=row, column=0, pady=(10, 6))
        self.register_i18n(button, text_key)

    def _ip_filetypes(self) -> list[tuple[str, str]]:
        return [
            (tr("gui_filetype_all"), "*.*"),
            (tr("gui_filetype_txt"), "*.txt"),
            (tr("gui_filetype_json"), "*.json"),
        ]

    def _app_filetypes(self) -> list[tuple[str, str]]:
        return [(tr("gui_filetype_exe"), "*.*"), (tr("gui_filetype_txt"), "*.txt")]

    def _build_wireguard_page(self) -> None:
        page = self._create_page("wireguard", "gui_wg_title", "gui_wg_subtitle")

        self.wg_src = FilePickerRow(page, self, "gui_source_conf", "open", self._conf_open_options)
        self.wg_src.grid(row=2, column=0, sticky="ew", pady=3)

        self.wg_route = ctk.StringVar(value="listed")
        route_frame = ctk.CTkFrame(page, fg_color="transparent")
        route_frame.grid(row=3, column=0, sticky="w", pady=(4, 2))
        route_keys = [
            ("listed", "gui_route_listed"),
            ("all", "gui_route_all"),
            ("keep", "gui_route_keep"),
        ]
        for row, (value, key) in enumerate(route_keys):
            radio = ctk.CTkRadioButton(
                route_frame, variable=self.wg_route, value=value, command=self._on_wg_route_change
            )
            radio.grid(row=row, column=0, sticky="w", pady=2)
            self.register_i18n(radio, key)

        self.wg_files = FileListPicker(
            page, self, "gui_allowed_ips_label", "gui_hint_ip_files", self._ip_filetypes
        )
        self.wg_files.grid(row=4, column=0, sticky="ew", pady=3)
        self._file_lists.append(self.wg_files)

        client_frame = ctk.CTkFrame(page, fg_color="transparent")
        client_frame.grid(row=5, column=0, sticky="w", pady=(4, 0))
        client_label = ctk.CTkLabel(client_frame)
        client_label.grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.register_i18n(client_label, "gui_client_label")

        self.wg_client = ctk.StringVar(value=CLIENT_WIREGUARD)
        client_keys = [
            (CLIENT_WIREGUARD, "gui_client_wireguard"),
            (CLIENT_WIRESOCK, "gui_client_wiresock"),
            (CLIENT_ANDROID, "gui_client_android"),
        ]
        for row, (value, key) in enumerate(client_keys, start=1):
            radio = ctk.CTkRadioButton(
                client_frame, variable=self.wg_client, value=value, command=self._on_wg_client_change
            )
            radio.grid(row=row, column=0, sticky="w", pady=2)
            self.register_i18n(radio, key)

        self.wiresock_frame = self._build_client_frame(
            page, 6, "gui_wiresock_settings", "gui_wiresock_priority"
        )

        self.wg_exclude_lan = ctk.BooleanVar(value=False)
        exclude_lan_box = ctk.CTkCheckBox(
            self.wiresock_frame, variable=self.wg_exclude_lan, command=self.schedule_preview
        )
        exclude_lan_box.grid(row=2, column=0, sticky="w", padx=12, pady=(4, 0))
        self.register_i18n(exclude_lan_box, "gui_exclude_lan")
        Tooltip(exclude_lan_box, "gui_exclude_lan_tooltip")

        self.wg_bypass_lan = ctk.BooleanVar(value=False)
        bypass_lan_box = ctk.CTkCheckBox(
            self.wiresock_frame, variable=self.wg_bypass_lan, command=self.schedule_preview
        )
        bypass_lan_box.grid(row=3, column=0, sticky="w", padx=12, pady=(4, 0))
        self.register_i18n(bypass_lan_box, "gui_bypass_lan")
        Tooltip(bypass_lan_box, "gui_bypass_lan_tooltip")

        self.wg_disallowed_ips = FileListPicker(
            self.wiresock_frame, self, "gui_disallowed_ips_label", "gui_hint_ip_files", self._ip_filetypes
        )
        self.wg_disallowed_ips.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 2))
        self._file_lists.append(self.wg_disallowed_ips)

        self.wg_cut_ips = ctk.BooleanVar(value=False)
        cut_ips_box = ctk.CTkCheckBox(
            self.wiresock_frame, variable=self.wg_cut_ips, command=self.schedule_preview
        )
        cut_ips_box.grid(row=5, column=0, sticky="w", padx=12, pady=(2, 0))
        self.register_i18n(cut_ips_box, "gui_cut_ips")
        Tooltip(cut_ips_box, "gui_cut_ips_tooltip")

        self.wg_app_mode = ctk.StringVar(value=APP_MODE_DISALLOWED)
        self._build_mode_radios(
            self.wiresock_frame,
            6,
            self.wg_app_mode,
            "gui_apps_mode_note",
            [(APP_MODE_DISALLOWED, "gui_apps_mode_disallowed"), (APP_MODE_ALLOWED, "gui_apps_mode_allowed")],
        )

        self.wg_apps = FileListPicker(
            self.wiresock_frame, self, "gui_apps_label", "gui_hint_app_files", self._app_filetypes
        )
        self.wg_apps.grid(row=7, column=0, sticky="ew", padx=12, pady=(4, 10))
        self._file_lists.append(self.wg_apps)

        self.android_frame = self._build_client_frame(
            page, 7, "gui_android_settings", "gui_android_warning"
        )

        self.wg_package_mode = ctk.StringVar(value=APP_MODE_EXCLUDED)
        self._build_mode_radios(
            self.android_frame,
            2,
            self.wg_package_mode,
            "gui_packages_mode_note",
            [(APP_MODE_EXCLUDED, "gui_apps_mode_excluded"), (APP_MODE_INCLUDED, "gui_apps_mode_included")],
        )

        self.wg_packages = TextListBox(
            self.android_frame, self, "gui_packages_label", "gui_hint_packages"
        )
        self.wg_packages.grid(row=3, column=0, sticky="ew", padx=12, pady=(6, 10))

        self.wg_neighbour_conf = FilePickerRow(
            page, self, "gui_neighbour_conf", "open", self._conf_open_options
        )
        self.wg_neighbour_conf.grid(row=8, column=0, sticky="ew", pady=3)

        keepalive_frame = ctk.CTkFrame(page, fg_color="transparent")
        keepalive_frame.grid(row=9, column=0, sticky="w", pady=(6, 0))
        keepalive_label = ctk.CTkLabel(keepalive_frame)
        keepalive_label.grid(row=0, column=0, padx=(0, 10))
        self.register_i18n(keepalive_label, "gui_keepalive_label")

        self.wg_keepalive = ctk.CTkEntry(keepalive_frame, width=70)
        self.wg_keepalive.grid(row=0, column=1)
        self.wg_keepalive.insert(0, str(DEFAULT_KEEPALIVE))
        self.wg_keepalive.bind("<KeyRelease>", lambda _event: self.schedule_preview())
        Tooltip(keepalive_label, "gui_keepalive_tooltip")
        Tooltip(self.wg_keepalive, "gui_keepalive_tooltip")

        self.wg_dst = FilePickerRow(
            page, self, "gui_new_conf", "save", self._wg_save_options, dnd=False
        )
        self.wg_dst.grid(row=10, column=0, sticky="ew", pady=3)

        self._create_run_button(page, 11, "gui_run_wg", self._run_wireguard)

        self._on_wg_route_change()
        self._on_wg_client_change()

    def _build_client_frame(
        self, page: ctk.CTkFrame, row: int, title_key: str, note_key: str
    ) -> ctk.CTkFrame:
        """Рамка настроек одного VPN-клиента: заголовок и пояснение занимают строки 0-1,
        виджеты вызывающего кода размещаются начиная со строки 2."""
        frame = ctk.CTkFrame(
            page,
            corner_radius=8,
            border_width=1,
            border_color=("gray65", "gray35"),
            fg_color=("gray90", "gray13"),
        )
        frame.grid(row=row, column=0, sticky="ew", pady=(6, 3))
        frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(frame, anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
        title.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
        self.register_i18n(title, title_key)

        note = ctk.CTkLabel(
            frame,
            anchor="w",
            justify="left",
            wraplength=600,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        note.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))
        self.register_i18n(note, note_key)
        return frame

    def _build_mode_radios(
        self,
        parent: ctk.CTkFrame,
        row: int,
        variable: ctk.StringVar,
        note_key: str,
        items: list[tuple[str, str]],
    ) -> None:
        """Переключатель взаимоисключающих режимов вместе с пояснением к нему: текст стоит
        вплотную к своим радиокнопкам, а не в общей шапке рамки клиента."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="w", padx=12, pady=(6, 0))

        note = ctk.CTkLabel(
            frame,
            anchor="w",
            justify="left",
            wraplength=600,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        note.grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.register_i18n(note, note_key)

        for index, (value, key) in enumerate(items, start=1):
            radio = ctk.CTkRadioButton(
                frame, variable=variable, value=value, command=self.schedule_preview
            )
            radio.grid(row=index, column=0, sticky="w", pady=2)
            self.register_i18n(radio, key)

    def _conf_open_options(self) -> dict:
        return {"filetypes": [(tr("gui_filetype_conf"), "*.conf"), (tr("gui_filetype_all"), "*.*")]}

    def _wg_save_options(self) -> dict:
        src = self.wg_src.get()
        stem = Path(src).stem if src else "wireguard"
        return {
            "filetypes": [(tr("gui_filetype_conf"), "*.conf"), (tr("gui_filetype_all"), "*.*")],
            "defaultextension": ".conf",
            "initialfile": f"{stem}_split.conf",
        }

    def _on_wg_route_change(self) -> None:
        if self.wg_route.get() == "listed":
            self.wg_files.grid()
        else:
            self.wg_files.grid_remove()
        self.schedule_preview()

    def _on_wg_client_change(self) -> None:
        client = self.wg_client.get()
        for name, frame in ((CLIENT_WIRESOCK, self.wiresock_frame), (CLIENT_ANDROID, self.android_frame)):
            if name == client:
                frame.grid()
            else:
                frame.grid_remove()
        if client == CLIENT_WIREGUARD:
            self.wg_neighbour_conf.grid_remove()
        else:
            self.wg_neighbour_conf.grid()
        self.schedule_preview()

    def _wg_client_kwargs(self) -> dict:
        """Собирает аргументы build_wireguard_conf из состояния формы: PersistentKeepalive общий
        для всех клиентов, остальные ключи добавляет только выбранная рамка настроек."""
        kwargs: dict = {"keepalive": self._keepalive_value()}
        client = self.wg_client.get()

        if client == CLIENT_WIRESOCK:
            disallowed_ips = (
                self._collect_ips_cached(self.wg_disallowed_ips.paths)
                if self.wg_disallowed_ips.paths and not self.wg_cut_ips.get()
                else []
            )
            apps = collect_app_names(self.wg_apps.paths) if self.wg_apps.paths else []
            allowed_mode = self.wg_app_mode.get() == APP_MODE_ALLOWED
            kwargs.update(
                disallowed_ips=disallowed_ips,
                disallowed_apps=[] if allowed_mode else apps,
                allowed_apps=apps if allowed_mode else [],
                bypass_lan=self.wg_bypass_lan.get(),
                bypass_endpoint=self.wg_route.get() == "all",
            )
        elif client == CLIENT_ANDROID:
            packages = parse_app_names(self.wg_packages.get())
            included_mode = self.wg_package_mode.get() == APP_MODE_INCLUDED
            kwargs.update(
                excluded_apps=[] if included_mode else packages,
                included_apps=packages if included_mode else [],
            )
        return kwargs

    def _allowed_ips_for_client(self, ips: list[str], source: str) -> list[str]:
        """Исключения, выразимые только самим списком AllowedIPs, — такой конфиг без правок
        понимают Amnezia и другие клиенты без ключа DisallowedIPs. Для классического WireGuard
        список не дробится: killswitch работает только при ровно 0.0.0.0/0."""
        client = self.wg_client.get()
        if client == CLIENT_WIRESOCK:
            if self.wg_exclude_lan.get():
                ips = exclude_ips(ips, LAN_EXCLUDE_IPS)
            if self.wg_cut_ips.get() and self.wg_disallowed_ips.paths:
                ips = exclude_ips(ips, self._collect_ips_cached(self.wg_disallowed_ips.paths))
        if client != CLIENT_WIREGUARD:
            neighbour = self.wg_neighbour_conf.get()
            if neighbour:
                holes = read_allowed_ips(neighbour)
                endpoint = read_endpoint_ip(neighbour)
                if endpoint:
                    holes = merge_unique(holes, [endpoint])
                if holes:
                    ips = exclude_ips(ips, holes)
        if client != CLIENT_ANDROID or self.wg_route.get() != "all":
            return ips
        endpoint = read_endpoint_ip(source)
        return exclude_ips(ips, [endpoint]) if endpoint else ips

    def _keepalive_value(self) -> int | None:
        """Число из поля PersistentKeepalive; пустое или неподходящее значение означает
        «не трогать ключ», а не ошибку: предпросмотр должен строиться и во время набора."""
        text = self.wg_keepalive.get().strip()
        if not text.isdigit() or int(text) > MAX_KEEPALIVE:
            return None
        return int(text)

    def _sync_keepalive_field(self, source: str) -> None:
        """Подставляет в поле значение из выбранного конфига, а если ключа нет или он нулевой —
        рекомендованные 25. Срабатывает только на смену файла, чтобы не затирать правку руками."""
        if source == self._keepalive_source:
            return
        self._keepalive_source = source
        self.wg_keepalive.delete(0, "end")
        self.wg_keepalive.insert(0, str(read_persistent_keepalive(source) or DEFAULT_KEEPALIVE))

    def _collect_ips_cached(self, paths: list[str]) -> list[str]:
        """Читает и валидирует файлы с кэшем по (путь, mtime, размер), чтобы предпросмотр не
        перечитывал их на каждое событие формы; кэш — ограниченный LRU, хранит и неуспех."""
        try:
            stats = tuple(_file_signature(path) for path in paths)
        except OSError:
            stats = None
        key = tuple(paths)
        cached = self._ips_cache.get(key)
        if cached is not None and cached[0] == stats:
            self._ips_cache[key] = self._ips_cache.pop(key)
            if isinstance(cached[1], Exception):
                raise cached[1]
            return list(cached[1])

        try:
            ips = collect_ips(paths)
        except (VpnConfiguratorError, OSError) as exc:
            self._store_ips_cache(key, (stats, exc))
            raise
        self._store_ips_cache(key, (stats, ips))
        return list(ips)

    def _store_ips_cache(self, key: tuple, value: tuple) -> None:
        self._ips_cache.pop(key, None)
        self._ips_cache[key] = value
        while len(self._ips_cache) > IPS_CACHE_MAX:
            self._ips_cache.pop(next(iter(self._ips_cache)))

    def _generate_wg_conf(self) -> tuple[str, int]:
        """Единый конвейер генерации WG-конфига для предпросмотра и сохранения."""
        src = self.wg_src.get()
        self._require(src, "gui_err_need_conf")
        self._sync_keepalive_field(src)
        if self.wg_route.get() == "all":
            ips = list(ALL_TRAFFIC_IPS)
        elif self.wg_route.get() == "keep":
            ips = read_allowed_ips(src)
            self._require(ips, "gui_err_no_keep_ips")
        else:
            self._require(self.wg_files.paths, "gui_err_need_files")
            ips = self._collect_ips_cached(self.wg_files.paths)
        text = build_wireguard_conf(
            self._allowed_ips_for_client(ips, src),
            src,
            self.wg_client.get() == CLIENT_WIRESOCK,
            **self._wg_client_kwargs(),
        )
        return text, len(ips)

    def _generate_merge_text(self) -> tuple[str, int]:
        self._require(self.merge_files.paths, "gui_err_need_files")
        ips = self._collect_ips_cached(self.merge_files.paths)
        output_format = OUTPUT_FORMATS[self.merge_format.get()]
        return output_format.formatter(ips), len(ips)

    def _run_page(
        self,
        dst: str,
        ext: str,
        newline: str | None,
        generate: Callable[[], tuple[str, int]],
        picker: FilePickerRow,
        success_key: str,
        validator: Callable[[str], list[str]] | None = None,
    ) -> str | None:
        """Общий конвейер сохранения: ручной текст предпросмотра пишется как есть (после мягкой
        валидации), иначе результат генерируется из формы."""
        self._require(dst, "gui_err_need_output")
        dst = self._ensure_ext(dst, ext)

        self._flush_preview()
        text = self._current_preview_text()
        if text is not None:
            if not self._confirm_valid(text, validator):
                return None
            if not self._confirm_overwrite(dst, picker):
                return None
            self._write_output(dst, text, newline)
            self._reset_preview_dirty()
            return tr("msg_file_saved").format(path=dst)

        text, count = generate()
        if not self._confirm_overwrite(dst, picker):
            return None
        self._write_output(dst, text, newline)
        return tr(success_key).format(path=dst, count=count)

    def _confirm_valid(self, text: str, validator: Callable[[str], list[str]] | None) -> bool:
        """Мягкая проверка отредактированного текста: проблемы показываются пользователю,
        но решение сохранять остаётся за ним — предпросмотр может содержать что угодно намеренно."""
        problems = validator(text) if validator else []
        if not problems:
            return True
        shown = "\n".join(problems[:5])
        return messagebox.askyesno(
            tr("gui_invalid_config_title"),
            tr("gui_invalid_config_question").format(problems=shown),
        )

    def _run_wireguard(self) -> str | None:
        return self._run_page(
            self.wg_dst.get(),
            ".conf",
            None,
            self._generate_wg_conf,
            self.wg_dst,
            "msg_conf_created",
            validator=validate_wireguard_text,
        )

    def _build_merge_page(self) -> None:
        page = self._create_page("merge", "gui_merge_title", "gui_merge_subtitle")

        self.merge_files = FileListPicker(
            page, self, "gui_files_label", "gui_hint_ip_files", self._ip_filetypes, list_height=210
        )
        self.merge_files.grid(row=2, column=0, sticky="ew", pady=3)
        self._file_lists.append(self.merge_files)

        self.merge_format = ctk.StringVar(value="plaintext")
        format_frame = ctk.CTkFrame(page, fg_color="transparent")
        format_frame.grid(row=3, column=0, sticky="w", pady=(6, 2))
        format_label = ctk.CTkLabel(format_frame)
        format_label.grid(row=0, column=0, padx=(0, 12))
        self.register_i18n(format_label, "gui_out_format")

        for column, (value, (label_key, _initial, _filetype)) in enumerate(MERGE_UI.items(), start=1):
            radio = ctk.CTkRadioButton(
                format_frame, variable=self.merge_format, value=value, command=self.schedule_preview
            )
            radio.grid(row=0, column=column, padx=(0, 12))
            self.register_i18n(radio, label_key)

        self.merge_dst = FilePickerRow(page, self, "gui_new_file", "save", self._merge_save_options)
        self.merge_dst.grid(row=4, column=0, sticky="ew", pady=3)

        self._create_run_button(page, 5, "gui_run_merge", self._run_merge)

    def _merge_save_options(self) -> dict:
        format_key = self.merge_format.get()
        _label_key, initial_file, filetype_key = MERGE_UI[format_key]
        ext = OUTPUT_FORMATS[format_key].ext
        return {
            "filetypes": [(tr(filetype_key), f"*{ext}"), (tr("gui_filetype_all"), "*.*")],
            "defaultextension": ext,
            "initialfile": initial_file,
        }

    def _run_merge(self) -> str | None:
        format_key = self.merge_format.get()
        output_format = OUTPUT_FORMATS[format_key]
        return self._run_page(
            self.merge_dst.get(),
            output_format.ext,
            output_format.newline,
            self._generate_merge_text,
            self.merge_dst,
            "msg_file_created",
            validator=validate_amnezia_text if format_key == "amnezia" else None,
        )

    def schedule_preview(self) -> None:
        """Откладывает обновление предпросмотра, схлопывая частые события (ввод, клики)."""
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(300, self._refresh_preview)

    def _reset_preview_dirty(self) -> None:
        self._preview_dirty = False
        self._update_preview_label()

    def _update_preview_label(self) -> None:
        key = "gui_preview_label_dirty" if self._preview_dirty else "gui_preview_label"
        self.preview_label.configure(text=tr(key))

    def _flush_preview(self) -> None:
        """Применяет отложенное обновление предпросмотра, чтобы сохранение не взяло старый текст."""
        if self._preview_job is not None:
            self._refresh_preview()

    def _current_preview_text(self) -> str | None:
        if self._preview_is_placeholder:
            return None
        text = self.preview_box.get("1.0", "end-1c")
        if not text.strip():
            if self._preview_dirty:
                self._reset_preview_dirty()
            return None
        return text

    def _write_output(self, dst: str, text: str, newline: str | None) -> None:
        if not text.endswith("\n"):
            text += "\n"
        with open(dst, "w", encoding="utf-8", newline=newline) as file:
            file.write(text)

    def _preview_textbox(self):
        return getattr(self.preview_box, "_textbox", self.preview_box)

    def _on_preview_wheel(self, event) -> str:
        """Колесо над предпросмотром скроллит только его: 'break' обрывает цепочку биндингов
        до bind_all-обработчика CTkScrollableFrame, который иначе скроллил бы и страницу."""
        direction = -1 if event.delta > 0 else 1
        self._preview_textbox().yview_scroll(direction * max(1, abs(event.delta) // 40), "units")
        return "break"

    def _on_preview_focus(self, _event) -> None:
        if self._preview_is_placeholder:
            self.preview_box.delete("1.0", "end")
            self._preview_textbox().edit_modified(False)
            self._preview_is_placeholder = False

    def _on_preview_focus_out(self, _event) -> None:
        """Возвращает подсказку, если пользователь кликнул в пустой предпросмотр и ушёл без ввода."""
        if not self._preview_dirty and not self.preview_box.get("1.0", "end-1c").strip():
            self._refresh_preview()

    def _on_preview_modified(self, _event) -> None:
        """<<Modified>> приходит асинхронно, поэтому программные изменения не гейтятся флагом
        на момент вставки: они сбрасывают modified сразу, и сюда долетают с уже чистым флагом."""
        textbox = self._preview_textbox()
        if not textbox.edit_modified():
            return
        textbox.edit_modified(False)
        if self._preview_is_placeholder:
            return
        if not self._preview_dirty:
            self._preview_dirty = True
            self._update_preview_label()
            self._cancel_preview_job()
        self._highlight_preview()

    def _cancel_preview_job(self) -> None:
        """Снимает отложенную перегенерацию: ручная правка/уход со страницы — последнее
        изменение, устаревший after-колбэк не должен затереть его позже."""
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
            self._preview_job = None

    def _refresh_preview(self) -> None:
        """Перестраивает предпросмотр из полей формы: последнее изменение выигрывает —
        правка формы обновляет текст, ручная правка текста живёт до следующей правки формы."""
        self._cancel_preview_job()
        if self.current_page == "wireguard":
            text = self._safe_preview(self._generate_wg_conf)
        else:
            text = self._safe_preview(self._generate_merge_text)
        self._set_preview(text)

    def _safe_preview(self, generate: Callable[[], tuple[str, int]]) -> str | None:
        """Незаполненная форма и битые входные файлы дают placeholder без модальных окон —
        причина всплывёт понятной ошибкой при нажатии кнопки сохранения."""
        try:
            return generate()[0]
        except Exception:
            return None

    def _set_preview(self, text: str | None) -> None:
        self.preview_box.delete("1.0", "end")
        if text is None:
            self.preview_box.insert("1.0", tr("gui_preview_placeholder"), "placeholder")
            self._preview_is_placeholder = True
        else:
            self.preview_box.insert("1.0", text)
            self._preview_is_placeholder = False
        self._preview_textbox().edit_modified(False)
        if self._preview_dirty:
            self._reset_preview_dirty()
        self._highlight_preview()

    def _require(self, value: object, error_key: str) -> None:
        if not value:
            raise VpnConfiguratorError(tr(error_key))

    def _ensure_ext(self, path: str, ext: str) -> str:
        return path if path.lower().endswith(ext) else path + ext

    def _confirm_overwrite(self, path: str, picker: FilePickerRow | None = None) -> bool:
        """Подтверждение перезаписи; пропускается, если путь только что подтверждён
        системным диалогом «Сохранить как…» и с тех пор не редактировался."""
        if not Path(path).exists():
            return True
        if picker is not None and picker.dialog_confirmed_path == path:
            return True
        return messagebox.askyesno(
            tr("gui_overwrite_title"), tr("gui_overwrite_question").format(path=path)
        )

    def _execute(self, action: Callable[[], str | None]) -> None:
        """Выполняет операцию страницы: успех и ошибку показывает отдельным окном.
        None означает отмену — пользователь сам отказался в диалоге перезаписи."""
        try:
            success_message = action()
        except Exception as exc:
            messagebox.showerror(tr("gui_error_title"), self._error_message(exc))
        else:
            if success_message:
                messagebox.showinfo(tr("gui_success_title"), success_message)


def run_gui() -> None:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    app = VpnConfiguratorApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
