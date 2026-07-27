from pathlib import Path
from contextlib import closing
from dataclasses import replace
import shutil
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch

from turing_complete_migration.legacy_v6 import (
    COM_LEVEL_INPUT_1_PIN,
    COM_LEVEL_OUTPUT_1_PIN,
    CurrentCircuit,
    CurrentComponent,
    CurrentWire,
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


def current_campaign_base(*, component_count: int, wire_count: int = 0) -> bytes:
    components = [
        CurrentComponent(
            kind=COM_LEVEL_INPUT_1_PIN if index == 0 else COM_LEVEL_OUTPUT_1_PIN,
            position=(index * 10, 0),
            rotation=0,
            permanent_id=10_000 + index,
            user_label=f"base {index}",
            custom_string="",
            settings=(),
            buffer_size=0,
            ui_order=-2,
            word_size=1,
            immutable=True,
        )
        for index in range(component_count)
    ]
    wires = [
        CurrentWire(
            color=index,
            comment=f"base wire {index}",
            start=(index, index),
            segments=((0, 1),),
        )
        for index in range(wire_count)
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
            description="campaign base",
            sync_state=0,
            score=0,
            player_data=b"",
            hub_description="",
            design=b"",
            components=components,
            wires=wires,
        )
    )


def legacy_v6_level_circuit(*, save_id: int = 0, campaign_bound: bool = False) -> bytes:
    raw = bytearray()
    raw.extend(struct.pack("<qIqqBIH", save_id, 0, 0, 0, 1, 10_000_000, 0))
    raw.extend(_string("level solution"))
    raw.extend(struct.pack("<hhBBH", 0, 0, 0, campaign_bound, 0))
    raw.extend(struct.pack("<H", 0))
    raw.extend(_string(""))
    raw.extend(struct.pack("<q", 3))
    for kind, x, permanent_id in ((240, -13, 1), (242, 13, 2), (7, 0, 3)):
        raw.extend(struct.pack("<HhhBq", kind, x, 0, 0, permanent_id))
        raw.extend(_string(""))
        raw.extend(struct.pack("<QQh", 0, 0, 0))
    raw.extend(struct.pack("<q", 0))
    return bytes([6]) + compress_raw(bytes(raw))


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
            with patch(
                "turing_complete_migration.migration.game_is_running",
                return_value=False,
            ):
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
            with patch(
                "turing_complete_migration.migration.game_is_running",
                return_value=False,
            ):
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

    def test_postflight_accepts_runtime_injected_campaign_interfaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output = root / "source", root / "target", root / "output"
            source.mkdir()
            create_legacy(source)
            unit = source / "schematics" / "not_gate" / "Default"
            (unit / "circuit.data").write_bytes(legacy_v6_level_circuit())

            report = prepare_migration(
                source,
                target,
                output,
                archive_source=False,
                preserve_original=False,
                include_circuit_backups=False,
            )
            imported = Path(report["schematics"]["imported_units"][0]["destination"])
            current = output / "save" / "schematics" / imported / "circuit.data"
            parsed = parse_v15(current.read_bytes())
            self.assertEqual(len(parsed.components), 1)

            runtime_interfaces = [
                CurrentComponent(
                    kind=COM_LEVEL_INPUT_1_PIN,
                    position=(-13, 0),
                    rotation=0,
                    permanent_id=101,
                    user_label="Input",
                    custom_string="",
                    settings=(),
                    buffer_size=0,
                    ui_order=-2,
                    word_size=1,
                    immutable=True,
                ),
                CurrentComponent(
                    kind=COM_LEVEL_OUTPUT_1_PIN,
                    position=(13, 0),
                    rotation=0,
                    permanent_id=102,
                    user_label="Output",
                    custom_string="",
                    settings=(),
                    buffer_size=0,
                    ui_order=-2,
                    word_size=1,
                    immutable=True,
                ),
            ]
            current.write_bytes(
                write_v15(replace(parsed, components=[*parsed.components, *runtime_interfaces]))
            )

            postflight = postflight_check(output / "save")
            self.assertTrue(postflight["ok"])
            record = postflight["imported_circuits"][0]
            self.assertEqual(record["actual_component_count"], 3)
            self.assertEqual(record["expected_component_count"], 1)
            self.assertEqual(record["expected_runtime_component_count"], 3)
            self.assertEqual(record["status"], "rewritten_with_matching_counts")

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
            ), patch(
                "turing_complete_migration.migration.game_is_running",
                return_value=False,
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

    def test_legacy_architecture_is_derived_for_current_overture_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target, output, game = (
                root / "source",
                root / "target",
                root / "output",
                root / "game",
            )
            source.mkdir()
            create_legacy(source)
            architecture = source / "schematics" / "architecture" / "OVERTURE"
            architecture.mkdir(parents=True)
            (architecture / "circuit.data").write_bytes(
                legacy_v6_level_circuit(save_id=1234, campaign_bound=True)
            )
            with closing(sqlite3.connect(source / "progress.dat")) as connection:
                connection.execute("INSERT INTO levels VALUES ('registers', 'true', 'OVERTURE')")
                connection.execute("INSERT INTO levels VALUES ('program', 'true', 'OVERTURE')")
                connection.execute("INSERT INTO levels VALUES ('maze', 'true', 'OVERTURE')")
                connection.commit()

            campaign = game / "campaign"
            for level_id in (
                "not_gate",
                "overture_1_registers",
                "overture_2_alu",
                "overture_3_immediates",
                "overture_4_program",
                "overture_5_conditionals",
            ):
                level = campaign / level_id
                level.mkdir(parents=True)
                (level / "meta.txt").write_text("kind = sequential\n", encoding="utf-8")
                if level_id.startswith("overture_"):
                    component_count = 11 if level_id in {
                        "overture_4_program",
                        "overture_5_conditionals",
                    } else 9
                    wire_count = 2 if level_id == "overture_4_program" else 0
                    (level / "circuit.data").write_bytes(
                        current_campaign_base(
                            component_count=component_count,
                            wire_count=wire_count,
                        )
                    )
            maze = campaign / "maze"
            maze.mkdir(parents=True)
            (maze / "meta.txt").write_text("kind = architecture\n", encoding="utf-8")

            report = prepare_migration(
                source,
                target,
                output,
                game_dir=game,
                archive_source=False,
                preserve_original=False,
                include_circuit_backups=False,
            )
            save = output / "save"
            standalone = parse_v15(
                (save / "schematics" / "architecture" / "OVERTURE" / "circuit.data").read_bytes()
            )
            self.assertEqual(len(standalone.components), 3)
            for level_id in (
                "overture_1_registers",
                "overture_2_alu",
                "overture_3_immediates",
                "overture_4_program",
                "overture_5_conditionals",
            ):
                derived = parse_v15(
                    (save / "schematics" / level_id / "OVERTURE" / "circuit.data").read_bytes()
                )
                self.assertEqual(len(derived.components), 1)
            self.assertFalse((save / "schematics" / "maze" / "OVERTURE").exists())
            levels = (save / "levels.txt").read_text("utf-8")
            self.assertIn('"overture_1_registers",true,"OVERTURE"', levels)
            self.assertIn('"overture_2_alu",true,"OVERTURE"', levels)
            self.assertIn('"overture_4_program",true,"OVERTURE"', levels)
            self.assertIn('"maze",true,"OVERTURE"', levels)
            derived_units = report["schematics"]["derived_architecture_units"]
            self.assertEqual(len(derived_units), 5)
            imported_by_destination = {
                item["destination"]: item
                for item in report["schematics"]["imported_units"]
            }
            stage_one = imported_by_destination["overture_1_registers/OVERTURE"]
            self.assertEqual(
                stage_one["conversion"]["runtime_injected_component_count"],
                9,
            )
            self.assertEqual(stage_one["conversion"]["runtime_component_count"], 10)
            stage_four = imported_by_destination["overture_4_program/OVERTURE"]
            self.assertEqual(
                stage_four["conversion"]["runtime_injected_component_count"],
                11,
            )
            self.assertEqual(
                stage_four["conversion"]["runtime_campaign_source_version"],
                15,
            )
            self.assertEqual(
                stage_four["conversion"]["runtime_campaign_component_count"],
                11,
            )
            self.assertEqual(
                stage_four["conversion"]["runtime_campaign_wire_count"],
                2,
            )
            self.assertEqual(stage_four["conversion"]["runtime_component_count"], 12)
            self.assertEqual(stage_four["conversion"]["runtime_injected_wire_count"], 2)
            self.assertEqual(stage_four["conversion"]["runtime_wire_count"], 2)

            stage_four_path = (
                save
                / "schematics"
                / "overture_4_program"
                / "OVERTURE"
                / "circuit.data"
            )
            stage_four_user = parse_v15(stage_four_path.read_bytes())
            stage_four_base = parse_v15(
                (campaign / "overture_4_program" / "circuit.data").read_bytes()
            )
            stage_four_path.write_bytes(
                write_v15(
                    replace(
                        stage_four_user,
                        components=[
                            *stage_four_user.components,
                            *stage_four_base.components,
                        ],
                        wires=[*stage_four_user.wires, *stage_four_base.wires],
                    )
                )
            )
            postflight = postflight_check(save)
            self.assertTrue(postflight["ok"])
            postflight_by_unit = {
                item["unit"]: item for item in postflight["imported_circuits"]
            }
            stage_four_runtime = postflight_by_unit["overture_4_program/OVERTURE"]
            self.assertEqual(stage_four_runtime["actual_component_count"], 12)
            self.assertEqual(stage_four_runtime["actual_wire_count"], 2)
            self.assertEqual(
                stage_four_runtime["status"],
                "rewritten_with_matching_counts",
            )
            self.assertEqual(
                report["schematics"]["skipped_architecture_derivations"],
                [],
            )


if __name__ == "__main__":
    unittest.main()
