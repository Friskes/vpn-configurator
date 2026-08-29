"""Локальная замена релизного CI на время блокировки GitHub Actions.

Повторяет шаги .github/workflows/build-pyinstaller.yml теми же командами, чтобы собранный
руками артефакт не отличался от собранного в CI. Windows и macOS собирают только сами себя:
PyInstaller не умеет кросс-компиляцию, чужую платформу здесь не получить.
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
MACOS_X86_PYTHON = "cpython-3.12-macos-x86_64"

PYINSTALLER_ARGS = [
    "pyinstaller",
    "-w",
    "-F",
    "--collect-all",
    "customtkinter",
    "--collect-all",
    "tkinterdnd2",
    "vpn_configurator.py",
]


def run(command: list[str]) -> None:
    """Шаг сборки с эхом команды; ненулевой код завершает скрипт, чтобы не собрать
    релиз поверх упавших тестов."""
    print("$ " + " ".join(command), flush=True)
    code = subprocess.run(command, cwd=ROOT).returncode
    if code != 0:
        sys.exit(code)


def build(python_id: str | None) -> None:
    command = ["uv", "run", "--frozen"]
    if python_id:
        command += ["--python", python_id]
    run(command + PYINSTALLER_ARGS)


def package_windows(version: str) -> Path:
    """Копия, а не переименование как в CI: dist/vpn_configurator.exe остаётся на месте —
    именно его открывают для ручной проверки после обычных правок."""
    target = DIST / f"vpn_configurator_v{version}.exe"
    shutil.copy2(DIST / "vpn_configurator.exe", target)
    return target


def package_macos(version: str, arch: str) -> Path:
    app = DIST / "vpn_configurator.app"
    run(["file", str(app / "Contents" / "MacOS" / "vpn_configurator")])
    target = DIST / f"vpn_configurator_v{version}.macos-{arch}.zip"
    target.unlink(missing_ok=True)
    run(["ditto", "-c", "-k", "--keepParent", str(app), str(target)])
    return target


def publish(version: str, artifact: Path, notes_file: str | None) -> None:
    """Дозаливает артефакт в релиз, создавая его при отсутствии. Именно upload, а не create
    со списком файлов: сборка второй платформы не должна затирать уже выложенное.
    Без --notes-file описание собирается GitHub-ом из влитых PR."""
    tag = f"v{version}"
    view = subprocess.run(["gh", "release", "view", tag], cwd=ROOT, capture_output=True)
    if view.returncode != 0:
        notes = ["--notes-file", notes_file] if notes_file else ["--generate-notes"]
        run(["gh", "release", "create", tag, "--title", f"Release {tag}", *notes])
    run(["gh", "release", "upload", tag, str(artifact), "--clobber"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="версия без префикса v, например 0.3.0")
    parser.add_argument("--skip-tests", action="store_true", help="не прогонять pytest перед сборкой")
    parser.add_argument(
        "--macos-x86_64",
        action="store_true",
        help="на Apple Silicon собрать x86_64 вместо нативной arm64; нужен установленный Rosetta 2 "
        "(softwareupdate --install-rosetta)",
    )
    parser.add_argument("--publish", action="store_true", help="выложить артефакт в релиз на GitHub")
    parser.add_argument("--notes-file", help="файл с описанием релиза; иначе описание сгенерит GitHub")
    args = parser.parse_args()

    if not args.skip_tests:
        run(["uv", "run", "--frozen", "pytest", "tests/", "-v"])

    system = platform.system()
    if system == "Windows":
        build(None)
        artifact = package_windows(args.version)
    elif system == "Darwin":
        python_id = MACOS_X86_PYTHON if args.macos_x86_64 else None
        if python_id:
            run(["uv", "python", "install", python_id])
        build(python_id)
        artifact = package_macos(args.version, "x86_64" if python_id else platform.machine())
    else:
        sys.exit(f"{system}: релиз собирается только на Windows и macOS")

    size = artifact.stat().st_size / 2**20
    print(f"\nГотово: {artifact.relative_to(ROOT)} ({size:.2f} MB)")

    if args.publish:
        publish(args.version, artifact, args.notes_file)


if __name__ == "__main__":
    main()
