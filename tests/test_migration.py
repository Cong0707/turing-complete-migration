from pathlib import Path
from contextlib import closing
import shutil
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch

from turing_complete_migration.legacy_v6 import (
    CurrentCircuit,
    CurrentComponent,
    parse_v15,
    write_v15,
)
from turing_complete_migration.migration import (
    ORIGINAL_CIRCUIT_NAME,
    install_prepared,
    postflight_check,
    prepare_migration,
    rollback_backup,
    verify_save,
)
from turing_complete_migration.snappy import compress_raw


def _string(value: str) -> bytes:
    data = value.encode("utf-8")
    return struct.pack("<H", len(data)) + data


def legacy_v6_circuit(
    *,
    component_count: int = 1,
    save_id: int = 0,
    custom_reference_id: int | None = None,
) -> bytes:
    raw = bytearray()
    raw.extend(struct.pack("<qIqqBIH", save_id, 0, 0, 0, 0, 10_000_000, 0))
    raw.extend(_string("test legacy circuit"))
    raw.extend(struct.pack("<hhBBH", 0, 0, 0, 0, 0))
    raw.extend(struct.pack("<H", 0))
    raw.extend(_string(""))
    raw.extend(struct.pack("<q", component_count))
    for index in range(component_count):
        kind = 92 if custom_reference_id is not None else 2
        raw.extend(struct.pack("<HhhBq", kind, index * 10, 0, 0, index + 1))
        raw.extend(_string("custom" if custom_reference_id is not None else "on"))
        raw.extend(struct.pack("<QQh", 0, 0, index))
        if custom_reference_id is not None:
            raw.extend(struct.pack("<qhh", custom_reference_id, 0, 0))
    raw.extend(struct.pack("<q", 0))
    return bytes([6]) + compress_raw(bytes(raw))


def current_v15_circuit(*, component_count: int = 1) -> bytes:
    components = [
        CurrentComponent(
            kind=2,
            position=(index * 10, 0),
            rotation=0,
            permanent_id=index + 1,
            user_label="on",
            custom_string="",
            settings=(),
            buffer_size=0,
            ui_order=index,
            word_size=1,
        )
        for index in range(component_count)
    ]
    return write_v15(
        CurrentCircuit(
            custom_id=0,
            hub_id=0,
            gate=0,
            delay=0,
            menu_visible=False,
            clock_speed=10_000_000,
            dependencies=[],
            description="test current circuit",
            sync_state=0,
            score=0,
            player_data=b"",
            hub_description="",
            design=b"",
            components=components,
            wires=[],
        )
    )


def create_legacy(root: Path) -> None:
    unit = root / "schematics" / "not_gate" / "Default"
    unit.mkdir(parents=True)
    (unit / "circuit.data").write_bytes(legacy_v6_circuit())
    (root / "settings.txt").write_text("legacy_setting = legacy-value\n", encoding="utf-8")
    with closing(sqlite3.connect(root / "progress.dat")) as connection:
        connection.execute(
            "CREATE TABLE levels (id TEXT, complete INTEGER, selected_schematic TEXT)"
        )
        connection.execute("INSERT INTO levels VALUES ('not_gate', 'true', 'Default')")
        connection.commit()


def create_current(root: Path) -> None:
    unit = root / "schematics" / "not_gate" / "Default"
    unit.mkdir(parents=True)
    (unit / "circuit.data").write_bytes(current_v15_circuit())
    (root / "settings.txt").write_text("current_setting = current-value\n", encoding="utf-8")
    (root / "levels.txt").write_text('"not_gate",false,"Default",\n', encoding="utf-8")
    with closing(sqlite3.connect(root / "_progress.dat")) as connection:
        connection.execute("CREATE TABLE progress (key TEXT, value TEXT)")
        connection.commit()


class MigrationTests(unittest.TestCase):
    def test_prepare_preserves_target_settings_and_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            report = prepare_migration(source, target, output)
            self.assertEqual(
                (output / "save" / "settings.txt").read_text("utf-8"),
                "current_setting = current-value\n",
            )
            imported = report["schematics"]["imported_units"][0]["destination"]
            imported_dir = output / "save" / "schematics" / Path(imported)
            self.assertTrue((imported_dir / ORIGINAL_CIRCUIT_NAME).is_file())
            converted = parse_v15((imported_dir / "circuit.data").read_bytes())
            self.assertEqual(len(converted.components), 1)
            self.assertTrue((output / "archive" / "source" / "settings.txt").is_file())
            self.assertIn('"not_gate",true', (output / "save" / "levels.txt").read_text("utf-8"))

    def test_install_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            prepare_migration(source, target, output)
            receipt = install_prepared(output / "save", target)
            backup = Path(receipt["backup"])
            self.assertTrue(backup.is_dir())
            self.assertTrue((target / ".turing-complete-migration.json").is_file())
            rollback_backup(backup, target)
            self.assertEqual(
                (target / "settings.txt").read_text("utf-8"),
                "current_setting = current-value\n",
            )

    def test_prepare_rejects_output_inside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "source", root / "target"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            with self.assertRaisesRegex(ValueError, "outside both source and target"):
                prepare_migration(source, target, source / "output")

    def test_prepare_rejects_invalid_game_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            with self.assertRaisesRegex(FileNotFoundError, "campaign folder"):
                prepare_migration(source, target, output, game_dir=root / "not-a-game")

    def test_marker_detects_deleted_imported_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            report = prepare_migration(source, target, output)
            imported = Path(report["schematics"]["imported_units"][0]["destination"])
            shutil.rmtree(output / "save" / "schematics" / imported)

            verification = verify_save(output / "save")
            postflight = postflight_check(output / "save")
            self.assertFalse(verification["ok"])
            self.assertIn("missing", verification["imported_circuits"][0]["status"])
            self.assertFalse(postflight["ok"])
            self.assertEqual(len(postflight["migration_warnings"]), 1)

    def test_install_rejects_missing_current_circuit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            report = prepare_migration(source, target, output)
            imported = Path(report["schematics"]["imported_units"][0]["destination"])
            (output / "save" / "schematics" / imported / "circuit.data").unlink()
            with self.assertRaisesRegex(ValueError, "failed verification"):
                install_prepared(output / "save", target)

    def test_postflight_detects_probable_blank_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            report = prepare_migration(source, target, output)
            imported = Path(report["schematics"]["imported_units"][0]["destination"])
            current = output / "save" / "schematics" / imported / "circuit.data"
            current.write_bytes(current_v15_circuit(component_count=0))

            postflight = postflight_check(output / "save")
            self.assertFalse(postflight["ok"])
            self.assertEqual(len(postflight["migration_warnings"]), 1)
            self.assertEqual(
                postflight["migration_warnings"][0]["reason"],
                "component or wire count mismatch",
            )

    def test_install_rejects_running_steam_for_autocloud_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            (target / "steam_autocloud.vdf").write_text("autocloud", encoding="utf-8")
            prepare_migration(source, target, output)
            with patch(
                "turing_complete_migration.migration.steam_is_running",
                return_value=True,
            ):
                with self.assertRaisesRegex(RuntimeError, "Steam is running"):
                    install_prepared(output / "save", target)

    def test_install_allows_running_steam_when_cloud_is_explicitly_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            (target / "steam_autocloud.vdf").write_text("autocloud", encoding="utf-8")
            prepare_migration(source, target, output)
            with patch(
                "turing_complete_migration.migration.steam_is_running",
                return_value=True,
            ), patch(
                "turing_complete_migration.migration.game_is_running",
                return_value=False,
            ):
                receipt = install_prepared(
                    output / "save",
                    target,
                    steam_cloud_disabled=True,
                )
            self.assertTrue(receipt["steam_cloud_disabled_confirmed"])

    def test_verify_detects_preserved_original_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            report = prepare_migration(source, target, output)
            imported = Path(report["schematics"]["imported_units"][0]["destination"])
            original = output / "save" / "schematics" / imported / ORIGINAL_CIRCUIT_NAME
            original.write_bytes(legacy_v6_circuit(component_count=2))

            verification = verify_save(output / "save")
            self.assertFalse(verification["ok"])
            self.assertIn("hash mismatch", verification["preserved_original_pairs"][0]["status"])

    def test_prepare_and_install_into_missing_target_without_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            create_legacy(source)
            unit = source / "schematics" / "not_gate" / "Default"
            (unit / "circuit_backup_1.data").write_bytes(legacy_v6_circuit())

            report = prepare_migration(
                source,
                target,
                output,
                archive_source=False,
                preserve_original=False,
                include_circuit_backups=False,
            )
            imported = Path(report["schematics"]["imported_units"][0]["destination"])
            imported_dir = output / "save" / "schematics" / imported
            self.assertFalse(target.exists())
            self.assertFalse((output / "archive").exists())
            self.assertFalse((imported_dir / ORIGINAL_CIRCUIT_NAME).exists())
            self.assertEqual(list(imported_dir.glob("circuit_backup_*.data")), [])
            self.assertTrue(report["verification"]["ok"])

            with patch(
                "turing_complete_migration.migration.game_is_running",
                return_value=False,
            ):
                receipt = install_prepared(
                    output / "save",
                    target,
                    create_backup=False,
                )
            self.assertTrue(target.is_dir())
            self.assertFalse(receipt["backup_created"])
            self.assertIsNone(receipt["backup"])
            self.assertEqual(list(root.glob("*.tcm-backup-*")), [])
            self.assertEqual(list(root.glob(".*.tcm-replaced-*")), [])
            parsed = parse_v15(
                (target / "schematics" / imported / "circuit.data").read_bytes()
            )
            self.assertEqual(len(parsed.components), 1)

    def test_install_over_existing_target_without_leaving_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            target.mkdir()
            create_legacy(source)
            create_current(target)
            prepare_migration(
                source,
                target,
                output,
                archive_source=False,
                preserve_original=False,
                include_circuit_backups=False,
            )
            (target / "created-after-prepare.txt").write_text("remove me", encoding="utf-8")

            with patch(
                "turing_complete_migration.migration.game_is_running",
                return_value=False,
            ):
                receipt = install_prepared(
                    output / "save",
                    target,
                    create_backup=False,
                )

            self.assertFalse(receipt["backup_created"])
            self.assertFalse((target / "created-after-prepare.txt").exists())
            self.assertTrue((target / ".turing-complete-migration.json").is_file())
            self.assertEqual(list(root.glob("*.tcm-backup-*")), [])
            self.assertEqual(list(root.glob(".*.tcm-replaced-*")), [])

    def test_component_factory_is_mapped_to_current_foundry_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            create_legacy(source)
            definition = source / "schematics" / "component_factory" / "CPU" / "ALU"
            definition.mkdir(parents=True)
            (definition / "circuit.data").write_bytes(
                legacy_v6_circuit(save_id=1234)
            )
            architecture = source / "schematics" / "architecture" / "CPU"
            architecture.mkdir(parents=True)
            (architecture / "circuit.data").write_bytes(
                legacy_v6_circuit(custom_reference_id=1234)
            )

            report = prepare_migration(
                source,
                target,
                output,
                archive_source=False,
                preserve_original=False,
                include_circuit_backups=False,
            )

            save = output / "save" / "schematics"
            self.assertTrue((save / "foundry" / "CPU" / "ALU" / "circuit.data").is_file())
            self.assertFalse((save / "component_factory").exists())
            audit = report["schematics"]["custom_dependency_audit"]
            self.assertEqual(audit["definition_count"], 1)
            self.assertEqual(audit["reference_instance_count"], 1)
            self.assertEqual(audit["missing_definitions"], [])
            self.assertEqual(audit["definition_directory"], "schematics/foundry")


if __name__ == "__main__":
    unittest.main()
