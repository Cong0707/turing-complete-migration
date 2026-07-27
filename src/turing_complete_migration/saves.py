"""Save-root discovery and passive inspection."""

from __future__ import annotations

from collections import Counter
from contextlib import closing
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import csv
import os
import sqlite3
import subprocess

from .snappy import CircuitInfo, inspect_circuit


DEFAULT_SAVE_ROOTS = {
    "0.1059": Path.home()
    / "AppData/Roaming/Godot/app_userdata/Turing Complete_backup",
    "2.0.16": Path.home() / "AppData/Roaming/Godot/app_userdata/Turing Complete",
    "2.1.276": Path.home() / "AppData/Roaming/Turing Complete",
}

DEFAULT_GAME_DIR = Path(r"D:\Game\Steam\steamapps\common\Turing Complete")


@dataclass(frozen=True)
class SaveInspection:
    root: str
    generation: str
    evidence: list[str]
    file_count: int
    byte_count: int
    circuit_count: int
    circuit_versions: dict[str, int]
    invalid_circuits: list[dict[str, object]]
    suspicious_circuits: list[dict[str, object]]
    progress_database: str | None
    progress_integrity: str | None
    level_line_count: int
    setting_keys: list[str]
    steam_autocloud_marker: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_generation(root: Path) -> tuple[str, list[str]]:
    evidence: list[str] = []
    progress = root / "progress.dat"
    underscored = root / "_progress.dat"
    levels = root / "levels.txt"
    settings = root / "settings.txt"

    if progress.is_file():
        evidence.append("found progress.dat")
    if underscored.is_file():
        evidence.append("found _progress.dat")
    if levels.is_file():
        evidence.append("found levels.txt")
    if settings.is_file():
        evidence.append("found settings.txt")

    if progress.is_file():
        return "0.x legacy", evidence
    if underscored.is_file() and levels.is_file():
        column_count = 0
        with levels.open("r", encoding="utf-8", errors="replace", newline="") as stream:
            column_count = len(next((row for row in csv.reader(stream) if row), []))
        if column_count:
            evidence.append(f"levels.txt first row has {column_count} columns")
        if column_count >= 6:
            return "2.0.x alpha", evidence
        if column_count == 4:
            return "2.1+ current", evidence
        setting_text = settings.read_text("utf-8", errors="replace") if settings.is_file() else ""
        if "setting_loaded_architecture" in setting_text:
            return "2.1+ current", evidence
        return "2.0.x alpha", evidence
    if (root / "schematics").is_dir():
        evidence.append("found schematics directory but no recognized progress index")
        return "schematics-only or unknown", evidence
    return "not a recognized save root", evidence


def _settings_keys(path: Path) -> list[str]:
    if not path.is_file():
        return []
    keys: list[str] = []
    for line in path.read_text("utf-8", errors="replace").splitlines():
        if "=" in line:
            key = line.split("=", 1)[0].strip()
            if key:
                keys.append(key)
    return sorted(set(keys))


def _sqlite_integrity(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    except sqlite3.Error as exc:
        return f"error: {exc}"


def iter_circuit_files(root: Path):
    schematics = root / "schematics"
    if schematics.is_dir():
        yield from schematics.rglob("circuit.data")


def inspect_save(root: Path) -> SaveInspection:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"save root does not exist: {root}")

    generation, evidence = detect_generation(root)
    files = [path for path in root.rglob("*") if path.is_file()]
    circuit_infos: list[CircuitInfo] = []
    for path in iter_circuit_files(root):
        circuit_infos.append(
            inspect_circuit(path, display_path=path.relative_to(root).as_posix())
        )
    versions = Counter(
        "unknown" if info.version is None else str(info.version) for info in circuit_infos
    )
    invalid = [info.to_dict() for info in circuit_infos if not info.valid]

    suspicious: list[dict[str, object]] = []
    for info in circuit_infos:
        if not info.valid or info.raw_size is None:
            continue
        current = root / Path(info.path)
        backups = sorted(current.parent.glob("circuit_backup_*.data"))
        backup_infos = [inspect_circuit(path) for path in backups]
        largest = max((item.raw_size or 0 for item in backup_infos if item.valid), default=0)
        if largest >= 256 and info.raw_size <= 64 and info.raw_size * 4 < largest:
            suspicious.append(
                {
                    "path": info.path,
                    "current_raw_size": info.raw_size,
                    "largest_backup_raw_size": largest,
                    "reason": "current circuit is much smaller than a valid backup",
                }
            )

    progress_path = root / "progress.dat"
    if not progress_path.is_file():
        progress_path = root / "_progress.dat"
    progress_name = progress_path.name if progress_path.is_file() else None
    levels = root / "levels.txt"
    level_count = (
        sum(1 for line in levels.read_text("utf-8", errors="replace").splitlines() if line.strip())
        if levels.is_file()
        else 0
    )
    return SaveInspection(
        root=str(root),
        generation=generation,
        evidence=evidence,
        file_count=len(files),
        byte_count=sum(path.stat().st_size for path in files),
        circuit_count=len(circuit_infos),
        circuit_versions=dict(sorted(versions.items())),
        invalid_circuits=invalid,
        suspicious_circuits=suspicious,
        progress_database=progress_name,
        progress_integrity=_sqlite_integrity(progress_path),
        level_line_count=level_count,
        setting_keys=_settings_keys(root / "settings.txt"),
        steam_autocloud_marker=(root / "steam_autocloud.vdf").is_file(),
    )


def hash_tree(root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted((item for item in root.rglob("*") if item.is_file())):
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        records.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    return records


def _tasklist_text() -> str:
    if os.name != "nt":
        return ""
    try:
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return ""
    return completed.stdout.casefold()


def game_is_running() -> bool:
    return "turing complete.exe" in _tasklist_text()


def steam_is_running() -> bool:
    return '"steam.exe"' in _tasklist_text()
