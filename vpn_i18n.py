"""Переводы интерфейса и держатель текущего языка."""

import locale


def detect_system_language() -> str:
    try:
        code = (locale.getlocale()[0] or "").lower()
    except ValueError:
        code = ""
    return "ru" if code.startswith(("ru", "russian")) else "en"


class _LanguageHolder:
    def __init__(self) -> None:
        self.code = detect_system_language()


language = _LanguageHolder()

LANGUAGE_NAMES = {"en": "English", "ru": "Русский"}


def tr(key: str) -> str:
    return TRANSLATIONS[language.code][key]


TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "VPN Configurator",
        "msg_too_many_invalid": (
            "More than {count} invalid addresses in a row — the file does not look like an IP list."
        ),
        "msg_no_ips": "No valid IP addresses found in the selected files.",
        "msg_no_section": "The .conf file does not contain the [{section}] section.",
        "msg_bad_json": "Invalid JSON file format: {path}",
        "msg_bad_encoding": "Unsupported file encoding (UTF-8 expected): {path}",
        "msg_multi_peer": "Configs with multiple [Peer] sections are not supported.",
        "msg_file_not_found": "File not found: {path}",
        "msg_file_op_error": "File operation error: {error}",
        "msg_unexpected_error": "Unexpected error: {error}",
        "msg_gui_failed": "Failed to start the application: {error}",
        "msg_conf_created": "Config created:\n{path}\n\nAddresses: {count}",
        "msg_file_created": "File created:\n{path}\n\nAddresses: {count}",
        "msg_file_saved": "File saved:\n{path}",
        "msg_line_outside_section": "Line {num} is outside of any section: {line}",
        "msg_line_not_kv": "Line {num} does not look like 'Key = value': {line}",
        "msg_missing_allowed_ips": "The [Peer] section has no AllowedIPs key.",
        "msg_invalid_ip_in_key": "Invalid address in {key}: {value}",
        "msg_bad_amnezia_json": "The text is not valid JSON.",
        "gui_invalid_config_title": "Pre-save check",
        "gui_invalid_config_question": (
            "The preview text has possible issues:\n\n{problems}\n\nSave anyway?"
        ),
        "gui_error_title": "Error",
        "gui_success_title": "Done",
        "gui_nav_wireguard": "WireGuard config",
        "gui_nav_merge": "Merge files",
        "gui_wg_title": "WireGuard config",
        "gui_wg_subtitle": (
            "Adds IP addresses for split tunneling to an existing .conf file "
            "(WireGuard, Amnezia, WireSock and other compatible clients)."
        ),
        "gui_merge_title": "Merge / convert files",
        "gui_merge_subtitle": (
            "Merges IP address files into one without duplicates; the output format is your choice. "
            "One input file plus a different output format works as a conversion."
        ),
        "gui_source_conf": "Existing .conf file:",
        "gui_new_conf": "New .conf file:",
        "gui_route_listed": "Tunnel only the listed IP addresses",
        "gui_route_all": "Tunnel all traffic (0.0.0.0/0)",
        "gui_client_label": "VPN client:",
        "gui_client_wireguard": "Classic WireGuard (WireGuard, Amnezia, ...)",
        "gui_client_wiresock": "WireSock (obfuscation + extra filters)",
        "gui_wiresock_settings": "WireSock settings",
        "gui_wiresock_priority": (
            "Filter DisallowedIPs complements AllowedIPs:\nThe app filter has two mutually "
            "exclusive modes: a blacklist (DisallowedApps) or a whitelist (AllowedApps)."
        ),
        "gui_disallowed_ips_label": "Excluded IPs (DisallowedIPs):",
        "gui_apps_label": "Applications:",
        "gui_apps_mode_disallowed": "Exclude these apps from the tunnel (DisallowedApps)",
        "gui_apps_mode_allowed": "Tunnel ONLY these apps (AllowedApps)",
        "gui_exclude_lan": "Keep RustDesk and the local network outside the tunnel",
        "gui_exclude_lan_tooltip": (
            "Adds to the config:\n"
            "DisallowedApps = rustdesk — remote access keeps working outside the VPN\n"
            "(skipped in the whitelist mode);\n"
            "DisallowedIPs:\n"
            "192.168.0.0/16 — home LAN (wider than /24: survives a router subnet change);\n"
            "172.16.0.0/12 — the second private zone (Docker, corporate networks);\n"
            "169.254.0.0/16 — link-local (APIPA);\n"
            "224.0.0.0/4 — multicast: mDNS name resolution (name.local) and discovery scans;\n"
            "255.255.255.255/32 — broadcast (DHCP, discovery).\n"
            "10.0.0.0/8 is deliberately NOT excluded: the tunnel itself usually lives there."
        ),
        "gui_bypass_lan": "Add BypassLanTraffic = true",
        "gui_bypass_lan_tooltip": (
            "Native WireSock parameter: LAN traffic goes outside the tunnel at the client level.\n"
            "Complements the DisallowedIPs ranges from the checkbox above."
        ),
        "gui_allowed_ips_label": "Allowed IPs (AllowedIPs):",
        "gui_hint_ip_files": (
            "Files with IP addresses (the extension does not matter): plain text (one per line, "
            "comma, space or semicolon separated), Windows route ADD commands, amnezia .json."
        ),
        "gui_hint_app_files": (
            "Executables of any OS (.exe, macOS/Linux binaries, .app) — the file name becomes the "
            "app name — or a text file listing app names (one per line, comma or semicolon separated)."
        ),
        "gui_preview_label": "Result preview (editable):",
        "gui_preview_label_dirty": "Result preview (edited manually):",
        "gui_preview_placeholder": (
            "Fill in the fields above — the content of the resulting file will appear here. "
            "You can edit the text before saving."
        ),
        "gui_preview_discard_title": "Unsaved edits",
        "gui_preview_discard_question": (
            "The preview was edited manually. Switch the page and lose the edits?"
        ),
        "gui_filetype_exe": "Applications and lists",
        "gui_files_label": "IP address files:",
        "gui_add_files": "Add files...",
        "gui_clear": "Clear all",
        "gui_run_wg": "Create config",
        "gui_run_merge": "Merge files",
        "gui_out_format": "Output format:",
        "gui_fmt_plaintext": "Plaintext (.txt)",
        "gui_fmt_amnezia": "Amnezia (.json)",
        "gui_fmt_route": "Windows route (.bat)",
        "gui_new_file": "New file:",
        "gui_choose_file": "Choose file...",
        "gui_save_as": "Save as...",
        "gui_placeholder_file": "File path, or drag & drop a file here",
        "gui_placeholder_save": 'Click "Save as..." and choose where to save the file',
        "gui_placeholder_save_dnd": "Choose where to save, or drop an existing file to overwrite",
        "gui_drop_hint": "Drag files here or use the button",
        "gui_theme_system": "System",
        "gui_theme_light": "Light",
        "gui_theme_dark": "Dark",
        "gui_err_need_conf": "Select the existing .conf file.",
        "gui_err_need_files": "Add at least one file with IP addresses.",
        "gui_err_need_output": "Specify the output file name.",
        "gui_overwrite_title": "File exists",
        "gui_overwrite_question": "The file already exists:\n{path}\n\nOverwrite it?",
        "gui_dnd_unavailable": "Drag & drop is unavailable (the tkinterdnd2 library failed to load).",
        "gui_filetype_conf": "WireGuard config",
        "gui_filetype_txt": "Text file",
        "gui_filetype_json": "Amnezia JSON",
        "gui_filetype_bat": "Batch file",
        "gui_filetype_all": "All files",
    },
    "ru": {
        "app_title": "VPN Configurator",
        "msg_too_many_invalid": (
            "Более {count} некорректных адресов подряд — файл не похож на список IP."
        ),
        "msg_no_ips": "В выбранных файлах не найдено ни одного корректного IP-адреса.",
        "msg_no_section": "В .conf файле отсутствует секция [{section}].",
        "msg_bad_json": "Некорректный формат JSON-файла: {path}",
        "msg_bad_encoding": "Неподдерживаемая кодировка файла (ожидается UTF-8): {path}",
        "msg_multi_peer": "Конфиги с несколькими секциями [Peer] не поддерживаются.",
        "msg_file_not_found": "Файл не найден: {path}",
        "msg_file_op_error": "Ошибка файловой операции: {error}",
        "msg_unexpected_error": "Непредвиденная ошибка: {error}",
        "msg_gui_failed": "Не удалось запустить приложение: {error}",
        "msg_conf_created": "Конфиг создан:\n{path}\n\nАдресов: {count}",
        "msg_file_created": "Файл создан:\n{path}\n\nАдресов: {count}",
        "msg_file_saved": "Файл сохранён:\n{path}",
        "msg_line_outside_section": "Строка {num} вне секций: {line}",
        "msg_line_not_kv": "Строка {num} не похожа на «Ключ = значение»: {line}",
        "msg_missing_allowed_ips": "В секции [Peer] нет ключа AllowedIPs.",
        "msg_invalid_ip_in_key": "Некорректный адрес в {key}: {value}",
        "msg_bad_amnezia_json": "Текст не является корректным JSON.",
        "gui_invalid_config_title": "Проверка перед сохранением",
        "gui_invalid_config_question": (
            "В тексте предпросмотра есть возможные проблемы:\n\n{problems}\n\nСохранить всё равно?"
        ),
        "gui_error_title": "Ошибка",
        "gui_success_title": "Готово",
        "gui_nav_wireguard": "WireGuard конфиг",
        "gui_nav_merge": "Объединение файлов",
        "gui_wg_title": "WireGuard конфиг",
        "gui_wg_subtitle": (
            "Добавляет IP-адреса для раздельного туннелирования в существующий .conf файл "
            "(WireGuard, Amnezia, WireSock и другие совместимые клиенты)."
        ),
        "gui_merge_title": "Объединение / конвертация файлов",
        "gui_merge_subtitle": (
            "Объединяет файлы с IP-адресами в один без дубликатов; формат результата на выбор. "
            "Один файл на входе и другой формат на выходе — это конвертация."
        ),
        "gui_source_conf": "Существующий .conf файл:",
        "gui_new_conf": "Новый .conf файл:",
        "gui_route_listed": "Туннелировать только указанные IP-адреса",
        "gui_route_all": "Туннелировать весь трафик (0.0.0.0/0)",
        "gui_client_label": "VPN-клиент:",
        "gui_client_wireguard": "Классический WireGuard (WireGuard, Amnezia, ...)",
        "gui_client_wiresock": "WireSock (обфускация + доп. фильтры)",
        "gui_wiresock_settings": "Параметры WireSock",
        "gui_wiresock_priority": (
            "Фильтр DisallowedIPs дополняет AllowedIPs\nФильтр приложений имеет два взаимоисключающих "
            "режима: чёрный список (DisallowedApps) или белый список (AllowedApps)."
        ),
        "gui_disallowed_ips_label": "Исключённые IP (DisallowedIPs):",
        "gui_apps_label": "Приложения:",
        "gui_apps_mode_disallowed": "Исключить эти приложения из туннеля (DisallowedApps)",
        "gui_apps_mode_allowed": "В туннель ТОЛЬКО эти приложения (AllowedApps)",
        "gui_exclude_lan": "Не пускать RustDesk и локальную сеть в туннель",
        "gui_exclude_lan_tooltip": (
            "Добавляет в конфиг:\n"
            "DisallowedApps = rustdesk — удалённый доступ продолжит работать мимо VPN\n"
            "(в режиме белого списка не добавляется);\n"
            "DisallowedIPs:\n"
            "192.168.0.0/16 — домашняя LAN (шире /24: переживёт смену подсети роутера);\n"
            "172.16.0.0/12 — вторая приватная зона (Docker, корпоративные сети);\n"
            "169.254.0.0/16 — link-local (APIPA);\n"
            "224.0.0.0/4 — multicast: mDNS-резолв имён (имя.local) и discovery-сканы;\n"
            "255.255.255.255/32 — broadcast (DHCP, discovery).\n"
            "10.0.0.0/8 намеренно НЕ исключается: туннель сам обычно живёт в этой зоне."
        ),
        "gui_bypass_lan": "Добавить BypassLanTraffic = true",
        "gui_bypass_lan_tooltip": (
            "Нативный параметр WireSock: трафик локальной сети идёт мимо туннеля на уровне клиента.\n"
            "Дополняет диапазоны DisallowedIPs из чекбокса выше."
        ),
        "gui_allowed_ips_label": "Разрешённые IP (AllowedIPs):",
        "gui_hint_ip_files": (
            "Файлы с IP-адресами (расширение не важно): обычный текст (построчно, через запятую, "
            "пробел или точку с запятой), команды Windows route ADD, amnezia .json."
        ),
        "gui_hint_app_files": (
            "Исполняемые файлы любой ОС (.exe, бинари macOS/Linux, .app) — именем приложения станет "
            "имя файла — либо текстовый файл со списком имён (построчно, через запятую или ;)."
        ),
        "gui_preview_label": "Предпросмотр результата (можно редактировать):",
        "gui_preview_label_dirty": "Предпросмотр результата (изменён вручную):",
        "gui_preview_placeholder": (
            "Заполните поля выше — здесь появится содержимое итогового файла. "
            "Текст можно поправить перед сохранением."
        ),
        "gui_preview_discard_title": "Несохранённые правки",
        "gui_preview_discard_question": (
            "Предпросмотр изменён вручную. Переключить страницу и потерять правки?"
        ),
        "gui_filetype_exe": "Приложения и списки",
        "gui_files_label": "Файлы с IP-адресами:",
        "gui_add_files": "Добавить файлы...",
        "gui_clear": "Очистить всё",
        "gui_run_wg": "Создать конфиг",
        "gui_run_merge": "Объединить файлы",
        "gui_out_format": "Формат результата:",
        "gui_fmt_plaintext": "Plaintext (.txt)",
        "gui_fmt_amnezia": "Amnezia (.json)",
        "gui_fmt_route": "Windows route (.bat)",
        "gui_new_file": "Новый файл:",
        "gui_choose_file": "Выбрать файл...",
        "gui_save_as": "Сохранить как...",
        "gui_placeholder_file": "Путь к файлу, либо перетащите файл сюда",
        "gui_placeholder_save": "Нажмите «Сохранить как...» и выберите, куда сохранить файл",
        "gui_placeholder_save_dnd": (
            "Выберите, куда сохранить, либо перетащите существующий файл для перезаписи"
        ),
        "gui_drop_hint": "Перетащите файлы сюда или используйте кнопку",
        "gui_theme_system": "Системная",
        "gui_theme_light": "Светлая",
        "gui_theme_dark": "Тёмная",
        "gui_err_need_conf": "Укажите существующий .conf файл.",
        "gui_err_need_files": "Добавьте хотя бы один файл с IP-адресами.",
        "gui_err_need_output": "Укажите имя итогового файла.",
        "gui_overwrite_title": "Файл существует",
        "gui_overwrite_question": "Файл уже существует:\n{path}\n\nПерезаписать его?",
        "gui_dnd_unavailable": "Drag & drop недоступен (не удалось загрузить библиотеку tkinterdnd2).",
        "gui_filetype_conf": "Конфигурация WireGuard",
        "gui_filetype_txt": "Текстовый файл",
        "gui_filetype_json": "Amnezia JSON",
        "gui_filetype_bat": "Batch-файл",
        "gui_filetype_all": "Все файлы",
    },
}
