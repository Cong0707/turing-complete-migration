"""Preparation, verification, installation and rollback operations."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import shutil
import uuid

from .legacy_v6 import COM_CUSTOM, SaveFormatError, convert_circuit_bytes, parse_v15
from .progress import (
    LEVEL_ALIASES,
    campaign_level_kinds,
    merge_progress,
    read_legacy_levels,
)
from .saves import (
    game_is_running,
    hash_tree,
    inspect_save,
    iter_circuit_files,
    steam_is_running,
)
from .snappy import inspect_circuit


REPORT_NAME = "migration-report.json"
MARKER_NAME = ".turing-complete-migration.json"
ORIGINAL_CIRCUIT_NAME = "_tcm_original_circuit.data"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _json_write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _tree_digest(root: Path) -> str:
    digest = sha256()
    for record in hash_tree(root):
        digest.update(str(record["relative_path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, copy_function=shutil.copy2)


def _unit_digest(root: Path) -> str:
    return _tree_digest(root)


def _unique_sibling(path: Path, suffix: str) -> Path:
    candidate = path.with_name(f"{path.name} [{suffix}]")
    index = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name} [{suffix} {index}]")
        index += 1
    return candidate


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _validate_plain_tree(root: Path) -> None:
    for path in (root, *root.rglob("*")):
        is_junction = getattr(path, "is_junction", lambda: False)
        if path.is_symlink() or is_junction():
            raise ValueError(f"save tree contains a symbolic link or junction: {path}")


def _scheme_units(schematics: Path) -> list[Path]:
    if not schematics.is_dir():
        return []
    return sorted(
        {path.parent for path in schematics.rglob("circuit.data")},
        key=lambda path: (len(path.relative_to(schematics).parts), path.as_posix()),
    )


def _belongs_to_unit(path: Path, units: list[Path]) -> bool:
    for unit in units:
        try:
            path.relative_to(unit)
            return True
        except ValueError:
            continue
    return False


def _preserve_original_circuit(unit: Path) -> None:
    circuit = unit / "circuit.data"
    original = unit / ORIGINAL_CIRCUIT_NAME
    if circuit.is_file() and not original.exists():
        shutil.copy2(circuit, original)


def _current_unit_relative(relative: Path) -> Path:
    parts = list(relative.parts)
    if parts:
        parts[0] = LEVEL_ALIASES.get(parts[0], parts[0])
    return Path(*parts)


def _is_runtime_level_unit(
    relative: Path,
    campaign_kinds: dict[str, str] | None,
) -> bool:
    if not relative.parts:
        return False
    level_id = relative.parts[0]
    return (
        campaign_kinds is not None
        and level_id in campaign_kinds
        and campaign_kinds[level_id] != "architecture"
    )


OVERTURE_STAGE_LEVELS = (
    "overture_1_registers",
    "overture_2_alu",
    "overture_3_immediates",
    "overture_4_program",
    "overture_5_conditionals",
)


def _merge_schematics(
    source_root: Path,
    prepared_root: Path,
    label: str,
    *,
    preserve_original: bool,
    include_circuit_backups: bool,
    campaign_kinds: dict[str, str] | None,
) -> dict[str, object]:
    source = source_root / "schematics"
    destination = prepared_root / "schematics"
    destination.mkdir(parents=True, exist_ok=True)
    units = _scheme_units(source)
    imported_units: list[dict[str, object]] = []
    converted_backups = 0
    omitted_backups = 0
    conversion_versions: Counter[int] = Counter()
    conversion_quality: Counter[str] = Counter()
    teleport_approximations = 0
    custom_definitions: dict[int, list[str]] = {}
    custom_references: Counter[int] = Counter()
    custom_reference_units: dict[int, set[str]] = {}
    zero_design_definitions: list[str] = []

    for source_unit in units:
        source_relative = source_unit.relative_to(source)
        relative = _current_unit_relative(source_relative)
        destination_unit = destination / relative
        if not destination_unit.exists():
            destination_unit.parent.mkdir(parents=True, exist_ok=True)
            _copy_tree(source_unit, destination_unit)
            status = "converted_missing"
        else:
            destination_unit = _unique_sibling(destination_unit, f"legacy {label}")
            _copy_tree(source_unit, destination_unit)
            status = "converted_with_collision_rename"

        source_circuit = source_unit / "circuit.data"
        destination_circuit = destination_unit / "circuit.data"
        strip_level_interfaces = (
            True if _is_runtime_level_unit(relative, campaign_kinds) else None
        )
        source_info = inspect_circuit(
            source_circuit,
            display_path=(source_relative / "circuit.data").as_posix(),
        )
        if preserve_original:
            shutil.copy2(source_circuit, destination_unit / ORIGINAL_CIRCUIT_NAME)
        else:
            preserved = destination_unit / ORIGINAL_CIRCUIT_NAME
            if preserved.exists():
                preserved.unlink()
        try:
            converted, conversion = convert_circuit_bytes(
                source_circuit.read_bytes(),
                strip_level_interfaces=strip_level_interfaces,
            )
        except SaveFormatError as exc:
            raise SaveFormatError(
                f"cannot convert {source_circuit}: {exc}"
            ) from exc
        destination_circuit.write_bytes(converted)
        converted_info = inspect_circuit(
            destination_circuit,
            display_path=(relative / "circuit.data").as_posix(),
        )
        converted_circuit = parse_v15(converted)
        destination_relative = destination_unit.relative_to(destination).as_posix()
        if relative.parts and relative.parts[0] == "foundry" and converted_circuit.custom_id:
            custom_definitions.setdefault(converted_circuit.custom_id, []).append(
                destination_relative
            )
            if converted_circuit.design == bytes(512):
                zero_design_definitions.append(destination_relative)
        for component in converted_circuit.components:
            if component.kind != COM_CUSTOM or not component.custom_id:
                continue
            custom_references[component.custom_id] += 1
            custom_reference_units.setdefault(component.custom_id, set()).add(
                destination_relative
            )
        source_version = conversion.get("source_version")
        if isinstance(source_version, int):
            conversion_versions[source_version] += 1
        quality = conversion.get("mapping_quality_counts", {})
        if isinstance(quality, dict):
            for key, count in quality.items():
                if isinstance(key, str) and isinstance(count, int):
                    conversion_quality[key] += count
        teleport_count = conversion.get("teleport_wire_approximation_count", 0)
        if isinstance(teleport_count, int):
            teleport_approximations += teleport_count

        backup_reports: list[dict[str, object]] = []
        for backup in sorted(destination_unit.glob("circuit_backup_*.data")):
            if not include_circuit_backups:
                backup.unlink()
                omitted_backups += 1
                continue
            try:
                backup_converted, backup_report = convert_circuit_bytes(
                    backup.read_bytes(),
                    strip_level_interfaces=strip_level_interfaces,
                )
            except SaveFormatError as exc:
                raise SaveFormatError(f"cannot convert {backup}: {exc}") from exc
            backup.write_bytes(backup_converted)
            converted_backups += 1
            backup_reports.append({"file": backup.name, "conversion": backup_report})
        imported_units.append(
            {
                "source": source_relative.as_posix(),
                "destination": destination_relative,
                "status": status,
                "source_circuit": source_info.to_dict(),
                "converted_circuit": converted_info.to_dict(),
                "conversion": conversion,
                "original_preserved": preserve_original,
                "converted_backups": backup_reports,
            }
        )

    derived_architecture_units: list[dict[str, str]] = []
    skipped_architecture_derivations: list[dict[str, str]] = []
    derivation_requests: dict[tuple[str, str], str] = {}
    legacy_records = read_legacy_levels(source_root)
    stage_architectures: set[str] = set()
    for record in legacy_records:
        selected = record.selected_schematic
        if not selected:
            continue
        architecture_unit = source / "architecture" / selected
        if not (architecture_unit / "circuit.data").is_file():
            continue
        mapped_level = LEVEL_ALIASES.get(record.level_id, record.level_id)
        if record.level_id in {"registers", "constants", "program", "turing_complete"}:
            stage_architectures.add(selected)
        if campaign_kinds is None:
            needs_level_overlay = mapped_level in OVERTURE_STAGE_LEVELS or mapped_level == "binary_programming"
        else:
            needs_level_overlay = (
                mapped_level in campaign_kinds
                and campaign_kinds[mapped_level] != "architecture"
            )
        if needs_level_overlay:
            derivation_requests[(mapped_level, selected)] = record.level_id

    for selected in stage_architectures:
        for level_id in OVERTURE_STAGE_LEVELS:
            if campaign_kinds is None or level_id in campaign_kinds:
                derivation_requests.setdefault(
                    (level_id, selected),
                    "overture stage chain",
                )

    for (level_id, selected), source_level in sorted(derivation_requests.items()):
        architecture_unit = source / "architecture" / selected
        source_circuit = architecture_unit / "circuit.data"
        relative = Path(level_id) / selected
        destination_unit = destination / relative
        if destination_unit.exists():
            skipped_architecture_derivations.append({
                "level": level_id,
                "architecture": selected,
                "reason": "destination schematic already exists",
            })
            continue
        destination_unit.mkdir(parents=True)
        destination_circuit = destination_unit / "circuit.data"
        source_display = (
            Path("architecture") / selected / "circuit.data"
        ).as_posix()
        source_info = inspect_circuit(source_circuit, display_path=source_display)
        if preserve_original:
            shutil.copy2(source_circuit, destination_unit / ORIGINAL_CIRCUIT_NAME)
        try:
            converted, conversion = convert_circuit_bytes(
                source_circuit.read_bytes(),
                strip_level_interfaces=True,
            )
        except SaveFormatError as exc:
            raise SaveFormatError(
                f"cannot derive {level_id}/{selected} from {source_circuit}: {exc}"
            ) from exc
        destination_circuit.write_bytes(converted)
        converted_info = inspect_circuit(
            destination_circuit,
            display_path=(relative / "circuit.data").as_posix(),
        )
        converted_circuit = parse_v15(converted)
        for component in converted_circuit.components:
            if component.kind != COM_CUSTOM or not component.custom_id:
                continue
            custom_references[component.custom_id] += 1
            custom_reference_units.setdefault(component.custom_id, set()).add(
                relative.as_posix()
            )
        source_version = conversion.get("source_version")
        if isinstance(source_version, int):
            conversion_versions[source_version] += 1
        quality = conversion.get("mapping_quality_counts", {})
        if isinstance(quality, dict):
            for key, count in quality.items():
                if isinstance(key, str) and isinstance(count, int):
                    conversion_quality[key] += count
        teleport_count = conversion.get("teleport_wire_approximation_count", 0)
        if isinstance(teleport_count, int):
            teleport_approximations += teleport_count
        imported_units.append({
            "source": (Path("architecture") / selected).as_posix(),
            "destination": relative.as_posix(),
            "status": "derived_from_legacy_architecture_selection",
            "source_level": source_level,
            "source_circuit": source_info.to_dict(),
            "converted_circuit": converted_info.to_dict(),
            "conversion": conversion,
            "original_preserved": preserve_original,
            "converted_backups": [],
        })
        derived_architecture_units.append({
            "level": level_id,
            "architecture": selected,
            "destination": relative.as_posix(),
        })

    copied_loose: list[str] = []
    skipped_conflicts: list[str] = []
    if source.is_dir():
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            if _belongs_to_unit(path, units):
                continue
            relative = path.relative_to(source)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(path, target)
                copied_loose.append(relative.as_posix())
            elif path.read_bytes() != target.read_bytes():
                skipped_conflicts.append(relative.as_posix())

    missing_custom_ids = sorted(set(custom_references) - set(custom_definitions))
    duplicate_custom_ids = sorted(
        custom_id for custom_id, paths in custom_definitions.items() if len(paths) > 1
    )

    return {
        "imported_units": imported_units,
        "converted_unit_count": len(imported_units),
        "source_version_counts": dict(sorted(conversion_versions.items())),
        "mapping_quality_counts": dict(sorted(conversion_quality.items())),
        "teleport_wire_approximation_count": teleport_approximations,
        "converted_circuit_backup_count": converted_backups,
        "omitted_circuit_backup_count": omitted_backups,
        "copied_loose_files": copied_loose,
        "loose_file_conflicts_skipped": skipped_conflicts,
        "derived_architecture_units": derived_architecture_units,
        "skipped_architecture_derivations": skipped_architecture_derivations,
        "custom_dependency_audit": {
            "definition_count": len(custom_definitions),
            "referenced_id_count": len(custom_references),
            "reference_instance_count": sum(custom_references.values()),
            "missing_definitions": [
                {
                    "custom_id": custom_id,
                    "reference_count": custom_references[custom_id],
                    "units": sorted(custom_reference_units[custom_id]),
                }
                for custom_id in missing_custom_ids
            ],
            "duplicate_definitions": [
                {
                    "custom_id": custom_id,
                    "units": sorted(custom_definitions[custom_id]),
                }
                for custom_id in duplicate_custom_ids
            ],
            "zero_design_definition_count": len(zero_design_definitions),
            "zero_design_definitions": sorted(zero_design_definitions),
            "definition_directory": "schematics/foundry",
        },
    }


def prepare_migration(
    source_root: Path,
    target_root: Path,
    output_root: Path,
    *,
    game_dir: Path | None = None,
    source_label: str | None = None,
    archive_source: bool = True,
    preserve_original: bool = True,
    include_circuit_backups: bool = True,
) -> dict[str, object]:
    source_root = source_root.expanduser().resolve()
    target_root = target_root.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    resolved_game_dir = game_dir.expanduser().resolve() if game_dir else None
    if not source_root.is_dir():
        raise FileNotFoundError(f"source save does not exist: {source_root}")
    target_exists = target_root.exists()
    if target_exists and not target_root.is_dir():
        raise NotADirectoryError(f"target save is not a directory: {target_root}")
    if source_root == target_root:
        raise ValueError("source and target save roots must be different")
    if _paths_overlap(source_root, target_root):
        raise ValueError("source and target save roots must not contain one another")
    if _paths_overlap(output_root, source_root) or _paths_overlap(output_root, target_root):
        raise ValueError("output directory must be outside both source and target save trees")
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_root}")
    if resolved_game_dir is not None and not (resolved_game_dir / "campaign").is_dir():
        raise FileNotFoundError(
            f"game directory does not contain a campaign folder: {resolved_game_dir}"
        )
    _validate_plain_tree(source_root)
    if target_exists:
        _validate_plain_tree(target_root)

    source_inspection = inspect_save(source_root)
    target_inspection = inspect_save(target_root) if target_exists else None
    if source_inspection.generation not in {"0.x legacy", "2.0.x alpha"}:
        raise ValueError(
            f"source save must be a recognized 0.x or 2.0.x save, got: "
            f"{source_inspection.generation}"
        )
    if target_inspection is not None and target_inspection.generation != "2.1+ current":
        raise ValueError(
            f"target save must be a recognized 2.1+ save, got: "
            f"{target_inspection.generation}"
        )
    label = source_label or source_inspection.generation.replace(" ", "-")
    campaign_kinds = campaign_level_kinds(resolved_game_dir)

    output_root.mkdir(parents=True, exist_ok=True)
    prepared = output_root / "save"
    archive = output_root / "archive" / "source"
    if target_exists:
        _copy_tree(target_root, prepared)
    else:
        prepared.mkdir(parents=True)
    if archive_source:
        archive.parent.mkdir(parents=True, exist_ok=True)
        _copy_tree(source_root, archive)
        (output_root / "archive" / "SENSITIVE_DO_NOT_SHARE.txt").write_text(
            "This archive may contain settings.txt tokens and other private save data.\n",
            encoding="utf-8",
        )

    schematic_result = _merge_schematics(
        source_root,
        prepared,
        label,
        preserve_original=preserve_original,
        include_circuit_backups=include_circuit_backups,
        campaign_kinds=campaign_kinds,
    )
    custom_audit = schematic_result["custom_dependency_audit"]
    if custom_audit["missing_definitions"]:
        missing = ", ".join(
            str(item["custom_id"])
            for item in custom_audit["missing_definitions"]
        )
        raise ValueError(f"custom component definitions are missing for ID(s): {missing}")
    if custom_audit["duplicate_definitions"]:
        duplicates = ", ".join(
            str(item["custom_id"])
            for item in custom_audit["duplicate_definitions"]
        )
        raise ValueError(f"custom component IDs have duplicate definitions: {duplicates}")
    _, progress_result = merge_progress(
        source_root,
        prepared,
        game_dir=resolved_game_dir,
    )

    report: dict[str, object] = {
        "tool_format": 2,
        "created_utc": _utc_now(),
        "operation_id": str(uuid.uuid4()),
        "source": source_inspection.to_dict(),
        "target_before": target_inspection.to_dict() if target_inspection else None,
        "target_existed": target_exists,
        "prepared_save": str(prepared),
        "private_source_archive": str(archive) if archive_source else None,
        "source_archive_tree_sha256": _tree_digest(archive) if archive_source else None,
        "schematics": schematic_result,
        "progress": progress_result,
        "campaign_filter": str(resolved_game_dir / "campaign") if resolved_game_dir else None,
        "settings_policy": (
            "target settings.txt is retained; source settings values are never merged"
            if target_exists
            else "no settings.txt is created; the current game will create its own settings"
        ),
        "binary_policy": (
            "supported legacy circuit versions are parsed and written directly as version 15; "
            + (
                f"the source bytes are also kept as {ORIGINAL_CIRCUIT_NAME}"
                if preserve_original
                else "source circuit bytes are not copied into the prepared save"
            )
        ),
        "archive_source": archive_source,
        "preserve_original": preserve_original,
        "include_circuit_backups": include_circuit_backups,
    }
    marker = {
        "tool_format": 2,
        "created_utc": report["created_utc"],
        "operation_id": report["operation_id"],
        "source_generation": source_inspection.generation,
        "report_relative_path_while_prepared": f"../{REPORT_NAME}",
        "imported_units": [
            {
                "unit": item["destination"],
                "source_circuit": item["source_circuit"],
                "converted_circuit": item["converted_circuit"],
                "conversion": item["conversion"],
                "original_preserved": item["original_preserved"],
            }
            for item in schematic_result["imported_units"]
        ],
    }
    _json_write(prepared / MARKER_NAME, marker)
    if archive_source:
        _json_write(output_root / "archive" / "manifest.json", hash_tree(archive))
    _json_write(output_root / REPORT_NAME, report)

    verification = verify_save(prepared)
    report["verification"] = verification
    _json_write(output_root / REPORT_NAME, report)
    return report


def verify_save(save_root: Path) -> dict[str, object]:
    save_root = save_root.expanduser().resolve()
    inspection = inspect_save(save_root)
    schematics_root = save_root / "schematics"
    marker_path = save_root / MARKER_NAME
    marker: dict[str, object] | None = None
    imported_circuits: list[dict[str, object]] = []
    original_pairs: list[dict[str, object]] = []
    seen_units: set[str] = set()
    if marker_path.is_file():
        try:
            loaded = json.loads(marker_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read migration marker {marker_path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"migration marker must contain a JSON object: {marker_path}")
        marker = loaded
        entries = marker.get("imported_units", [])
        if not isinstance(entries, list):
            raise ValueError(f"migration marker imported_units must be a list: {marker_path}")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("unit"), str):
                raise ValueError(f"migration marker contains an invalid imported unit: {marker_path}")
            relative = Path(entry["unit"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"migration marker contains an unsafe unit path: {entry['unit']}")
            unit = relative.as_posix()
            if unit in seen_units:
                raise ValueError(f"migration marker contains a duplicate unit: {unit}")
            seen_units.add(unit)

            source_metadata = entry.get("source_circuit", entry.get("original"))
            converted_metadata = entry.get("converted_circuit")
            conversion = entry.get("conversion")
            if not isinstance(source_metadata, dict):
                raise ValueError(f"migration marker unit is missing source metadata: {unit}")
            if converted_metadata is not None and not isinstance(converted_metadata, dict):
                raise ValueError(f"migration marker unit has invalid converted metadata: {unit}")
            if conversion is not None and not isinstance(conversion, dict):
                raise ValueError(f"migration marker unit has invalid conversion metadata: {unit}")

            current = schematics_root / relative / "circuit.data"
            circuit_record: dict[str, object] = {
                "unit": unit,
                "expected_converted": converted_metadata,
                "conversion": conversion,
            }
            if not current.is_file():
                circuit_record["status"] = "missing current circuit.data"
            else:
                current_info = inspect_circuit(current)
                circuit_record["current"] = current_info.to_dict()
                if not current_info.valid:
                    circuit_record["status"] = "invalid current circuit.data container"
                elif current_info.version != 15:
                    circuit_record["status"] = (
                        f"current circuit.data is version {current_info.version}, expected 15"
                    )
                else:
                    try:
                        parsed = parse_v15(current.read_bytes())
                    except SaveFormatError as exc:
                        circuit_record["status"] = f"invalid version-15 payload: {exc}"
                    else:
                        actual_components = len(parsed.components)
                        actual_wires = len(parsed.wires)
                        expected_components = (
                            conversion.get("output_component_count")
                            if isinstance(conversion, dict)
                            else None
                        )
                        expected_runtime_components = (
                            conversion.get("runtime_component_count")
                            if isinstance(conversion, dict)
                            else None
                        )
                        expected_wires = (
                            conversion.get("output_wire_count")
                            if isinstance(conversion, dict)
                            else None
                        )
                        circuit_record["actual_component_count"] = actual_components
                        circuit_record["actual_wire_count"] = actual_wires
                        circuit_record["expected_component_count"] = expected_components
                        circuit_record["expected_runtime_component_count"] = (
                            expected_runtime_components
                        )
                        circuit_record["expected_wire_count"] = expected_wires
                        allowed_component_counts = {
                            count
                            for count in (expected_components, expected_runtime_components)
                            if isinstance(count, int)
                        }
                        counts_match = (
                            (
                                not allowed_component_counts
                                or actual_components in allowed_component_counts
                            )
                            and (not isinstance(expected_wires, int) or actual_wires == expected_wires)
                        )
                        expected_hash = (
                            converted_metadata.get("sha256")
                            if isinstance(converted_metadata, dict)
                            else None
                        )
                        if not counts_match:
                            circuit_record["status"] = "component or wire count mismatch"
                        elif isinstance(expected_hash, str) and current_info.sha256 == expected_hash:
                            circuit_record["status"] = "unchanged_v15"
                        else:
                            circuit_record["status"] = "rewritten_with_matching_counts"
            imported_circuits.append(circuit_record)

            original_preserved = bool(
                entry.get("original_preserved", "original" in entry)
            )
            if original_preserved:
                original = schematics_root / relative / ORIGINAL_CIRCUIT_NAME
                original_record: dict[str, object] = {
                    "unit": unit,
                    "expected_original": source_metadata,
                }
                if not original.is_file():
                    original_record["status"] = f"missing {ORIGINAL_CIRCUIT_NAME}"
                else:
                    old_info = inspect_circuit(original)
                    original_record["original"] = old_info.to_dict()
                    expected_hash = source_metadata.get("sha256")
                    if not old_info.valid:
                        original_record["status"] = f"invalid {ORIGINAL_CIRCUIT_NAME}"
                    elif isinstance(expected_hash, str) and old_info.sha256 != expected_hash:
                        original_record["status"] = f"{ORIGINAL_CIRCUIT_NAME} hash mismatch"
                    else:
                        original_record["status"] = "preserved"
                original_pairs.append(original_record)

    circuit_errors = [
        item
        for item in imported_circuits
        if item.get("status") not in {"unchanged_v15", "rewritten_with_matching_counts"}
    ]
    original_errors = [
        item for item in original_pairs if item.get("status") != "preserved"
    ]
    return {
        "checked_utc": _utc_now(),
        "inspection": inspection.to_dict(),
        "migration_marker": marker,
        "imported_circuits": imported_circuits,
        "preserved_original_pairs": original_pairs,
        "ok": (
            inspection.progress_integrity in {None, "ok"}
            and not inspection.invalid_circuits
            and not circuit_errors
            and not original_errors
        ),
    }


def install_prepared(
    prepared_save: Path,
    target_root: Path,
    *,
    create_backup: bool = True,
    steam_cloud_disabled: bool = False,
) -> dict[str, object]:
    prepared_save = prepared_save.expanduser().resolve()
    target_root = target_root.expanduser().resolve()
    if game_is_running():
        raise RuntimeError("Turing Complete is running; close the game before installation")
    if not prepared_save.is_dir():
        raise FileNotFoundError(f"prepared save does not exist: {prepared_save}")
    if not (prepared_save / MARKER_NAME).is_file():
        raise ValueError(f"prepared save is missing {MARKER_NAME}")
    target_exists = target_root.exists()
    if target_exists and not target_root.is_dir():
        raise NotADirectoryError(f"target save is not a directory: {target_root}")
    if (
        target_exists
        and not steam_cloud_disabled
        and steam_is_running()
        and (target_root / "steam_autocloud.vdf").is_file()
    ):
        raise RuntimeError(
            "Steam is running and the target contains steam_autocloud.vdf; "
            "exit Steam or disable Steam Cloud for Turing Complete before installation"
        )
    if _paths_overlap(prepared_save, target_root):
        raise ValueError("prepared save and target save must not contain one another")
    _validate_plain_tree(prepared_save)
    if target_exists:
        _validate_plain_tree(target_root)
    verification = verify_save(prepared_save)
    if not verification["ok"]:
        raise ValueError("prepared save failed verification; refusing installation")

    stamp = _stamp()
    backup = (
        target_root.with_name(f"{target_root.name}.tcm-backup-{stamp}")
        if target_exists and create_backup
        else None
    )
    displaced = (
        target_root.with_name(f".{target_root.name}.tcm-replaced-{stamp}")
        if target_exists and not create_backup
        else None
    )
    temporary = target_root.with_name(f".{target_root.name}.tcm-install-{stamp}")
    reserved = [path for path in (backup, displaced, temporary) if path is not None]
    if any(path.exists() for path in reserved):
        raise FileExistsError("backup or temporary installation path already exists")

    target_root.parent.mkdir(parents=True, exist_ok=True)
    _copy_tree(prepared_save, temporary)
    target_digest = _tree_digest(target_root) if target_exists else None
    prepared_digest = _tree_digest(temporary)
    moved_target = False
    installed_new = False
    old_location = backup or displaced
    try:
        if target_exists and old_location is not None:
            target_root.rename(old_location)
            moved_target = True
        temporary.rename(target_root)
        installed_new = True
    except Exception:
        if installed_new and target_root.exists() and old_location is not None and old_location.exists():
            shutil.rmtree(target_root)
            installed_new = False
        if moved_target and not target_root.exists() and old_location is not None and old_location.exists():
            old_location.rename(target_root)
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    if displaced is not None:
        try:
            shutil.rmtree(displaced)
        except Exception as exc:
            raise RuntimeError(
                "installation succeeded, but the previous target could not be deleted: "
                f"{displaced}"
            ) from exc

    return {
        "installed_utc": _utc_now(),
        "target": str(target_root),
        "target_existed": target_exists,
        "backup_created": backup is not None,
        "backup": str(backup) if backup is not None else None,
        "steam_cloud_disabled_confirmed": steam_cloud_disabled,
        "target_before_tree_sha256": target_digest,
        "installed_tree_sha256": prepared_digest,
        "prepared_verification": verification,
    }


def rollback_backup(backup_root: Path, target_root: Path) -> dict[str, object]:
    backup_root = backup_root.expanduser().resolve()
    target_root = target_root.expanduser().resolve()
    if game_is_running():
        raise RuntimeError("Turing Complete is running; close the game before rollback")
    if not backup_root.is_dir():
        raise FileNotFoundError(f"backup does not exist: {backup_root}")
    if not target_root.is_dir():
        raise FileNotFoundError(f"target save does not exist: {target_root}")
    if steam_is_running() and (target_root / "steam_autocloud.vdf").is_file():
        raise RuntimeError(
            "Steam is running and the target contains steam_autocloud.vdf; "
            "exit Steam before rollback"
        )
    if _paths_overlap(backup_root, target_root):
        raise ValueError("backup and target save must not contain one another")
    _validate_plain_tree(backup_root)
    _validate_plain_tree(target_root)

    stamp = _stamp()
    pre_rollback = target_root.with_name(f"{target_root.name}.tcm-pre-rollback-{stamp}")
    temporary = target_root.with_name(f".{target_root.name}.tcm-rollback-{stamp}")
    if pre_rollback.exists() or temporary.exists():
        raise FileExistsError("pre-rollback backup or temporary path already exists")
    _copy_tree(backup_root, temporary)
    moved_target = False
    try:
        target_root.rename(pre_rollback)
        moved_target = True
        temporary.rename(target_root)
    except Exception:
        if moved_target and not target_root.exists() and pre_rollback.exists():
            pre_rollback.rename(target_root)
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "rolled_back_utc": _utc_now(),
        "restored_from": str(backup_root),
        "target": str(target_root),
        "pre_rollback_backup": str(pre_rollback),
    }


def postflight_check(save_root: Path) -> dict[str, object]:
    save_root = save_root.expanduser().resolve()
    result = verify_save(save_root)
    warnings: list[dict[str, object]] = []
    warned_units: set[str] = set()
    for item in result["imported_circuits"]:
        if item.get("status") in {"unchanged_v15", "rewritten_with_matching_counts"}:
            continue
        warnings.append(
            {
                "unit": item["unit"],
                "reason": item.get("status", "unknown imported-circuit error"),
                "expected_component_count": item.get("expected_component_count"),
                "actual_component_count": item.get("actual_component_count"),
                "expected_wire_count": item.get("expected_wire_count"),
                "actual_wire_count": item.get("actual_wire_count"),
                "recovery": "regenerate the prepared save from the read-only legacy source",
            }
        )
        warned_units.add(str(item["unit"]))
    for item in result["preserved_original_pairs"]:
        if item.get("status") == "preserved" or str(item["unit"]) in warned_units:
            continue
        warnings.append(
            {
                "unit": item["unit"],
                "reason": item.get("status", "unknown preserved-original error"),
                "recovery": "regenerate the prepared save from the read-only legacy source",
            }
        )
    result["migration_warnings"] = warnings
    result["ok"] = bool(result["ok"] and not warnings)
    return result
