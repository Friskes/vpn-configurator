import ipaddress
import json
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import suppress
from pathlib import Path
from typing import NamedTuple

from vpn_i18n import tr


class VpnConfiguratorError(Exception):
    """Ошибка бизнес-логики: GUI показывает её пользователю отдельным окном."""


ALL_TRAFFIC_IPS = ("0.0.0.0/0", "::/0")
COMMENT_PREFIXES = ("#", ";", "//")
MAX_INVALID_IN_A_ROW = 30
OBFUSCATE_KEY = "12345678901234567890123456789012"
DEFAULT_DISALLOWED_APPS = ("rustdesk",)
LAN_EXCLUDE_IPS = (
    "192.168.0.0/16",
    "172.16.0.0/12",
    "169.254.0.0/16",
    "224.0.0.0/4",
    "255.255.255.255/32",
)

ROUTE_LINE_RE = re.compile(r"^route\b", re.IGNORECASE)
ROUTE_ADD_RE = re.compile(r"^route\s+(?:[-/]\S+\s+)*add\s+(\S+)(?:\s+mask\s+(\S+))?", re.IGNORECASE)
SEPARATORS_RE = re.compile(r"[,;\s]+")
APP_SEPARATORS_RE = re.compile(r"[,;]+")
INLINE_COMMENT_RE = re.compile(r"\s(?:#|//).*$")

SECTION_LINE_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
KEY_LINE_RE = re.compile(r"^\s*(?P<key>[A-Za-z][A-Za-z0-9]*)\s*=\s*(?P<value>.*?)\s*$")

NETMASKS = [str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask) for prefix in range(33)]


def _read_text(path: Path) -> str:
    """Читает файл, снимая UTF-8 BOM и распознавая UTF-16/UTF-32 по BOM (частый результат
    PowerShell-редиректа); прочие кодировки — понятная ошибка вместо трейсбека."""
    data = path.read_bytes()
    try:
        if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
            return data.decode("utf-32")
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return data.decode("utf-16")
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise VpnConfiguratorError(tr("msg_bad_encoding").format(path=path)) from exc


def merge_unique(existing: Sequence[str], new_items: Iterable[str]) -> list[str]:
    """Дополняет список новыми элементами без дубликатов (без учёта регистра), сохраняя порядок."""
    result = list(existing)
    seen = {item.lower() for item in result}
    for item in new_items:
        lowered = item.lower()
        if lowered not in seen:
            seen.add(lowered)
            result.append(item)
    return result


def _iter_json_items(data: list) -> Iterator[str]:
    for obj in data:
        if isinstance(obj, dict):
            hostname = obj.get("hostname")
            yield hostname if isinstance(hostname, str) else ""
        elif isinstance(obj, str):
            yield obj
        else:
            yield str(obj)


def _iter_ip_entries(path: Path) -> Iterator[str]:
    """Отдаёт кандидатов в IP-адреса, сам определяя формат файла: JSON (amnezia или массив строк),
    команды Windows route ADD или произвольный текст с разделителями. Расширение файла не важно."""
    text = _read_text(path)
    head = text.lstrip()[:2]

    if head[:1] in ("[", "{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            if head[:1] == "{" or head == "[{":
                raise VpnConfiguratorError(tr("msg_bad_json").format(path=path)) from exc
        else:
            if not isinstance(data, list):
                raise VpnConfiguratorError(tr("msg_bad_json").format(path=path))
            yield from _iter_json_items(data)
            return

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(COMMENT_PREFIXES):
            continue

        stripped = INLINE_COMMENT_RE.sub("", stripped).strip()
        if not stripped:
            continue

        if ROUTE_LINE_RE.match(stripped):
            route_match = ROUTE_ADD_RE.match(stripped)
            if route_match:
                ip, mask = route_match.group(1), route_match.group(2)
                yield f"{ip}/{mask}" if mask else ip
            continue

        yield from SEPARATORS_RE.split(stripped)


def _normalize_ip(value: str) -> str | None:
    """Каноничный адрес или CIDR, либо None для некорректного значения.
    Маска в виде 255.255.255.0 сводится к длине префикса, /32 — к одиночному адресу."""
    try:
        if "/" in value:
            network = ipaddress.IPv4Network(value, strict=True)
            if network.prefixlen == 32:
                return str(network.network_address)
            return str(network)
        return str(ipaddress.IPv4Address(value))
    except ValueError:
        return None


def collect_ips(paths: Sequence[Path | str]) -> list[str]:
    """Читает файлы любого поддерживаемого формата, валидирует адреса
    и убирает дубликаты с сохранением порядка."""
    ips: list[str] = []
    seen: set[str] = set()

    for path in paths:
        invalid_in_a_row = 0
        for raw_value in _iter_ip_entries(Path(path)):
            value = raw_value.strip()
            if not value:
                continue

            normalized = _normalize_ip(value)
            if normalized is None:
                invalid_in_a_row += 1
                if invalid_in_a_row >= MAX_INVALID_IN_A_ROW:
                    raise VpnConfiguratorError(
                        tr("msg_too_many_invalid").format(count=MAX_INVALID_IN_A_ROW)
                    )
                continue

            invalid_in_a_row = 0
            if normalized not in seen:
                seen.add(normalized)
                ips.append(normalized)

    if not ips:
        raise VpnConfiguratorError(tr("msg_no_ips"))

    return ips


def parse_app_names(text: str) -> list[str]:
    """Имена приложений из текстового списка. Комментарии отсекаются построчно (иначе `;`
    был бы одновременно комментарием и разделителем), затем строка делится по запятой и `;`,
    а пробелы разделяют только токены без слэшей — полный путь может их содержать."""
    names: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(COMMENT_PREFIXES):
            continue
        line = INLINE_COMMENT_RE.sub("", line).strip()
        if not line:
            continue
        for chunk in APP_SEPARATORS_RE.split(line):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = [chunk] if ("/" in chunk or "\\" in chunk) else chunk.split()
            names = merge_unique(names, parts)
    return names


def collect_app_names(paths: Sequence[Path | str]) -> list[str]:
    """Имена приложений из перетащенных файлов: исполняемый файл (любой ОС) даёт своё имя,
    текстовый список — своё содержимое. Нечитаемый как текст файл считается бинарником."""
    names: list[str] = []
    for path in paths:
        file_path = Path(path)
        if file_path.suffix.lower() == ".exe":
            names = merge_unique(names, [file_path.stem])
            continue
        try:
            text = _read_text(file_path)
        except (VpnConfiguratorError, OSError):
            names = merge_unique(names, [file_path.stem])
            continue
        names = merge_unique(names, parse_app_names(text) or [file_path.stem])
    return names


def _find_sections(lines: Sequence[str]) -> dict[str, list[tuple[int, int]]]:
    """Возвращает диапазоны секций {имя_lower: [(индекс_заголовка, конец_не_включительно)]}."""
    sections: dict[str, list[tuple[int, int]]] = {}
    current_name: str | None = None
    current_start = 0
    for index, line in enumerate(lines):
        match = SECTION_LINE_RE.match(line)
        if match:
            if current_name is not None:
                sections.setdefault(current_name, []).append((current_start, index))
            current_name = match.group("name").strip().lower()
            current_start = index
    if current_name is not None:
        sections.setdefault(current_name, []).append((current_start, len(lines)))
    return sections


def _section_key_indices(lines: Sequence[str], section: str, key: str) -> list[int]:
    start, end = _find_sections(lines)[section][0]
    indices = []
    for index in range(start + 1, end):
        match = KEY_LINE_RE.match(lines[index])
        if match and match.group("key").lower() == key.lower():
            indices.append(index)
    return indices


def _get_values(lines: Sequence[str], section: str, key: str) -> list[str]:
    values: list[str] = []
    for index in _section_key_indices(lines, section, key):
        raw = KEY_LINE_RE.match(lines[index]).group("value")
        values.extend(item.strip() for item in raw.split(",") if item.strip())
    return values


def _set_key(lines: list[str], section: str, key: str, value: str) -> None:
    """Заменяет все строки ключа (без учёта регистра) одной канонично именованной строкой;
    отсутствующий ключ вставляется в конец секции перед хвостовыми пустыми строками."""
    indices = _section_key_indices(lines, section, key)
    new_line = f"{key} = {value}"
    if indices:
        lines[indices[0]] = new_line
        for index in reversed(indices[1:]):
            del lines[index]
        return
    start, end = _find_sections(lines)[section][0]
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, new_line)


def _remove_key(lines: list[str], section: str, key: str) -> None:
    for index in reversed(_section_key_indices(lines, section, key)):
        del lines[index]


def build_wireguard_conf(
    source_ips: Sequence[str],
    conf_path: Path | str,
    obfuscate: bool,
    *,
    disallowed_ips: Sequence[str] = (),
    disallowed_apps: Sequence[str] = (),
    allowed_apps: Sequence[str] = (),
    auto_disallowed_apps: Sequence[str] = (),
    bypass_lan: bool = False,
) -> str:
    """Возвращает текст нового WireGuard-конфига. Правки построчные — комментарии, повторяющиеся
    ключи и регистр исходника сохраняются, ключи/секции ищутся без учёта регистра.
    allowed_apps и disallowed_apps взаимоисключающие: выбор одного удаляет другой ключ;
    auto_disallowed_apps дописываются в чёрный список, только если белого нет нигде."""
    if allowed_apps and disallowed_apps:
        raise ValueError("allowed_apps and disallowed_apps are mutually exclusive")

    conf_path = Path(conf_path)
    if not conf_path.is_file():
        raise VpnConfiguratorError(tr("msg_file_not_found").format(path=conf_path))

    lines = _read_text(conf_path).splitlines()
    sections = _find_sections(lines)

    if len(sections.get("peer", [])) > 1:
        raise VpnConfiguratorError(tr("msg_multi_peer"))
    for section in ("Interface", "Peer"):
        if section.lower() not in sections:
            raise VpnConfiguratorError(tr("msg_no_section").format(section=section))

    _set_key(lines, "peer", "AllowedIPs", ", ".join(source_ips))

    if disallowed_ips:
        merged = merge_unique(_get_values(lines, "peer", "DisallowedIPs"), disallowed_ips)
        _set_key(lines, "peer", "DisallowedIPs", ", ".join(merged))

    if allowed_apps:
        merged = merge_unique(_get_values(lines, "peer", "AllowedApps"), allowed_apps)
        _set_key(lines, "peer", "AllowedApps", ", ".join(merged))
        _remove_key(lines, "peer", "DisallowedApps")
    elif disallowed_apps:
        merged = merge_unique(_get_values(lines, "peer", "DisallowedApps"), disallowed_apps)
        _set_key(lines, "peer", "DisallowedApps", ", ".join(merged))
        _remove_key(lines, "peer", "AllowedApps")

    if obfuscate:
        _set_key(lines, "interface", "ObfuscateKey", OBFUSCATE_KEY)
        _set_key(lines, "interface", "ObfuscateMethod", "xor")

    if bypass_lan:
        _set_key(lines, "interface", "BypassLanTraffic", "true")

    if auto_disallowed_apps and not allowed_apps and not _get_values(lines, "peer", "AllowedApps"):
        merged = merge_unique(_get_values(lines, "peer", "DisallowedApps"), auto_disallowed_apps)
        _set_key(lines, "peer", "DisallowedApps", ", ".join(merged))

    return "\n".join(lines) + "\n"


def _is_valid_ip_value(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False


def validate_wireguard_text(text: str) -> list[str]:
    """Мягкая проверка конфига перед сохранением (пользователь мог криво отредактировать
    предпросмотр): возвращает список найденных проблем, пустой — если текст выглядит корректно."""
    problems: list[str] = []
    lines = text.splitlines()
    sections = _find_sections(lines)

    if "interface" not in sections:
        problems.append(tr("msg_no_section").format(section="Interface"))
    if "peer" not in sections:
        problems.append(tr("msg_no_section").format(section="Peer"))
    elif len(sections["peer"]) > 1:
        problems.append(tr("msg_multi_peer"))

    first_section = min(
        (start for ranges in sections.values() for start, _end in ranges), default=len(lines)
    )
    for num, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(COMMENT_PREFIXES) or SECTION_LINE_RE.match(line):
            continue
        if num - 1 < first_section:
            problems.append(tr("msg_line_outside_section").format(num=num, line=stripped))
        elif not KEY_LINE_RE.match(line):
            problems.append(tr("msg_line_not_kv").format(num=num, line=stripped))

    if len(sections.get("peer", [])) == 1:
        if not _get_values(lines, "peer", "AllowedIPs"):
            problems.append(tr("msg_missing_allowed_ips"))
        for key in ("AllowedIPs", "DisallowedIPs"):
            for value in _get_values(lines, "peer", key):
                if not _is_valid_ip_value(value):
                    problems.append(tr("msg_invalid_ip_in_key").format(key=key, value=value))

    return problems


def validate_amnezia_text(text: str) -> list[str]:
    """Проверяет, что отредактированный amnezia-результат остался корректным JSON."""
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return [tr("msg_bad_amnezia_json")]
    return []


def format_plaintext(ips: Sequence[str]) -> str:
    return "".join(f"{ip}\n" for ip in ips)


def format_amnezia(ips: Sequence[str]) -> str:
    return json.dumps([{"hostname": ip, "ip": ""} for ip in ips], indent=2) + "\n"


def format_route(ips: Sequence[str]) -> str:
    """Команды Windows `route ADD <ip> MASK <mask> 0.0.0.0`; адреса уже нормализованы
    collect_ips, поэтому маска берётся из длины префикса без повторной валидации."""
    lines = []
    for ip in ips:
        address, _, prefix = ip.partition("/")
        netmask = NETMASKS[int(prefix)] if prefix else NETMASKS[32]
        lines.append(f"route ADD {address} MASK {netmask} 0.0.0.0\n")
    return "".join(lines)


class OutputFormat(NamedTuple):
    ext: str
    formatter: Callable[[Sequence[str]], str]
    newline: str | None


OUTPUT_FORMATS: dict[str, OutputFormat] = {
    "plaintext": OutputFormat(".txt", format_plaintext, None),
    "amnezia": OutputFormat(".json", format_amnezia, None),
    "route": OutputFormat(".bat", format_route, "\r\n"),
}


def _show_startup_error(error: str) -> None:
    """Показывает ошибку старта отдельным окном: у windowed-бинаря нет консоли,
    и без этого падение GUI было бы полностью молчаливым."""
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(tr("app_title"), tr("msg_gui_failed").format(error=error))
        root.destroy()
    except Exception:
        pass


def main() -> None:
    try:
        from vpn_gui import run_gui

        run_gui()
    except Exception as exc:
        _show_startup_error(f"{type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        main()
