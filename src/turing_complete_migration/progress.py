"""Conversion of legacy SQLite progress into the current levels.txt index."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from contextlib import closing
import csv
import sqlite3


LEVEL_ALIASES = {
    "ai_showdown": "nim",
    "alu_1": "overture_alu_1",
    "alu_2": "overture_alu_2",
    "crude_awakening": "introduction",
    "component_factory": "foundry",
    "conditions": "overture_conditions",
    "constants": "overture_3_immediates",
    "decoder": "overture_decoder",
    "decoder1": "decoder_1",
    "decoder3": "decoder_3",
    "byte_less": "byte_less_u",
    "byte_less_i": "byte_less_s",
    "byte_shift": "byte_lsr",
    "program": "overture_4_program",
    "registers": "overture_1_registers",
    "sorter": "sort",
    "turing_complete": "overture_5_conditionals",
}


@dataclass(frozen=True)
class LevelRecord:
    level_id: str
    complete: bool
    selected_schematic: str
    score_history: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _as_bool(value: object) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def find_legacy_database(root: Path) -> Path | None:
    for name in ("progress.dat", "_progress.dat"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def read_alpha_levels(path: Path) -> list[LevelRecord]:
    """Read the six-column levels.txt used by the 2.0.x alpha branch."""

    if not path.is_file():
        return []
    records: list[LevelRecord] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
        for line_number, row in enumerate(csv.reader(stream), 1):
            if not row:
                continue
            if len(row) < 6:
                raise ValueError(
                    f"alpha progress row {line_number} in {path} has {len(row)} columns; expected 6"
                )
            records.append(LevelRecord(row[0], _as_bool(row[1]), row[5], ""))
    return records


def read_legacy_levels(root: Path) -> list[LevelRecord]:
    alpha_path = root / "levels.txt"
    if alpha_path.is_file():
        with alpha_path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
            first = next((row for row in csv.reader(stream) if row), [])
        if len(first) >= 6:
            return read_alpha_levels(alpha_path)

    database = find_legacy_database(root)
    if database is None:
        return []
    uri = database.resolve().as_uri() + "?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "levels" not in names:
                return []
            rows = connection.execute(
                "SELECT id, complete, selected_schematic FROM levels ORDER BY rowid"
            ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(f"cannot read legacy progress database {database}: {exc}") from exc
    return [
        LevelRecord(str(level), _as_bool(complete), str(selected or ""), "")
        for level, complete, selected in rows
    ]


def read_current_levels(path: Path) -> list[LevelRecord]:
    if not path.is_file():
        return []
    records: list[LevelRecord] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream):
            if not row:
                continue
            padded = row + [""] * (4 - len(row))
            records.append(
                LevelRecord(
                    padded[0],
                    _as_bool(padded[1]),
                    padded[2],
                    padded[3],
                )
            )
    return records


def _quote(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


def write_current_levels(path: Path, records: list[LevelRecord]) -> None:
    lines = [
        f"{_quote(record.level_id)},{str(record.complete).lower()},"
        f"{_quote(record.selected_schematic)},{record.score_history}"
        for record in records
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def campaign_level_ids(game_dir: Path | None) -> set[str] | None:
    kinds = campaign_level_kinds(game_dir)
    return set(kinds) if kinds is not None else None


def campaign_level_kinds(game_dir: Path | None) -> dict[str, str] | None:
    if game_dir is None:
        return None
    campaign = game_dir / "campaign"
    if not campaign.is_dir():
        return None
    result: dict[str, str] = {}
    for path in campaign.iterdir():
        if not path.is_dir():
            continue
        kind = ""
        meta = path / "meta.txt"
        if meta.is_file():
            with meta.open("r", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    key, separator, value = line.partition("=")
                    if separator and key.strip() == "kind":
                        kind = value.strip()
                        break
        result[path.name] = kind
    return result


def _selection_exists(
    save_root: Path,
    level_id: str,
    selected: str,
    architecture_level_ids: set[str] | None = None,
) -> bool:
    if not selected:
        return False
    if level_id == "sandbox" or (
        architecture_level_ids is not None and level_id in architecture_level_ids
    ):
        return (save_root / "schematics" / "architecture" / selected / "circuit.data").is_file()
    if level_id in {"foundry", "component_factory"}:
        return any(
            (save_root / "schematics" / folder / selected / "circuit.data").is_file()
            for folder in ("foundry", "component_factory")
        )
    return (save_root / "schematics" / level_id / selected / "circuit.data").is_file()


def merge_progress(
    source_root: Path,
    prepared_save_root: Path,
    *,
    game_dir: Path | None = None,
) -> tuple[list[LevelRecord], dict[str, object]]:
    current_path = prepared_save_root / "levels.txt"
    current = read_current_levels(current_path)
    legacy = read_legacy_levels(source_root)
    level_kinds = campaign_level_kinds(game_dir)
    valid_ids = set(level_kinds) if level_kinds is not None else None
    architecture_level_ids = (
        {level_id for level_id, kind in level_kinds.items() if kind == "architecture"}
        if level_kinds is not None
        else None
    )

    merged = list(current)
    index = {record.level_id: position for position, record in enumerate(merged)}
    imported: list[str] = []
    upgraded: list[str] = []
    skipped: list[dict[str, str]] = []

    for record in legacy:
        mapped = LEVEL_ALIASES.get(record.level_id, record.level_id)
        if valid_ids is not None and mapped not in valid_ids:
            skipped.append({"source": record.level_id, "mapped": mapped, "reason": "not in current campaign"})
            continue
        selected = record.selected_schematic
        if not _selection_exists(
            prepared_save_root,
            mapped,
            selected,
            architecture_level_ids,
        ):
            selected = (
                "Default"
                if _selection_exists(
                    prepared_save_root,
                    mapped,
                    "Default",
                    architecture_level_ids,
                )
                else ""
            )

        if mapped in index:
            old = merged[index[mapped]]
            complete = old.complete or record.complete
            if complete != old.complete:
                upgraded.append(mapped)
            merged[index[mapped]] = LevelRecord(
                mapped,
                complete,
                old.selected_schematic or selected,
                old.score_history,
            )
        else:
            merged.append(LevelRecord(mapped, record.complete, selected, ""))
            index[mapped] = len(merged) - 1
            imported.append(mapped)

    stage_sources = {
        record.level_id: record
        for record in legacy
        if record.level_id in {"registers", "constants", "program", "turing_complete"}
        and record.selected_schematic
    }
    selected_architecture = next(
        (
            stage_sources[level_id].selected_schematic
            for level_id in ("turing_complete", "program", "constants", "registers")
            if level_id in stage_sources
        ),
        "",
    )
    stage_two = "overture_2_alu"
    if (
        selected_architecture
        and (valid_ids is None or stage_two in valid_ids)
        and _selection_exists(
            prepared_save_root,
            stage_two,
            selected_architecture,
            architecture_level_ids,
        )
    ):
        complete = any(
            stage_sources[level_id].complete
            for level_id in ("constants", "program", "turing_complete")
            if level_id in stage_sources
        )
        if stage_two in index:
            old = merged[index[stage_two]]
            merged[index[stage_two]] = LevelRecord(
                stage_two,
                old.complete or complete,
                old.selected_schematic or selected_architecture,
                old.score_history,
            )
        else:
            merged.append(LevelRecord(stage_two, complete, selected_architecture, ""))
            index[stage_two] = len(merged) - 1
            imported.append(stage_two)

    write_current_levels(current_path, merged)
    return merged, {
        "legacy_rows": len(legacy),
        "current_rows_before": len(current),
        "rows_after": len(merged),
        "imported_levels": imported,
        "upgraded_levels": upgraded,
        "skipped_levels": skipped,
        "score_policy": "legacy scores are intentionally not copied because scoring semantics changed",
    }
