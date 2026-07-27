from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest

from turing_complete_migration.progress import (
    merge_progress,
    read_alpha_levels,
    read_current_levels,
    read_legacy_levels,
)


class ProgressTests(unittest.TestCase):
    def test_merge_filters_and_maps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            prepared = root / "prepared"
            game = root / "game"
            source.mkdir()
            prepared.mkdir()
            (game / "campaign" / "decoder_1").mkdir(parents=True)
            (game / "campaign" / "not_gate").mkdir(parents=True)
            (prepared / "schematics" / "not_gate" / "Default").mkdir(parents=True)
            (prepared / "schematics" / "not_gate" / "Default" / "circuit.data").write_bytes(b"x")
            (prepared / "levels.txt").write_text('"not_gate",false,"Default",\n', encoding="utf-8")

            database = source / "progress.dat"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE levels (id TEXT, complete INTEGER, selected_schematic TEXT)"
                )
                connection.executemany(
                    "INSERT INTO levels VALUES (?, ?, ?)",
                    [("not_gate", "true", "Default"), ("decoder1", "true", "Default"), ("removed", "true", "Default")],
                )
                connection.commit()

            records, report = merge_progress(source, prepared, game_dir=game)
            by_id = {record.level_id: record for record in records}
            self.assertTrue(by_id["not_gate"].complete)
            self.assertIn("decoder_1", by_id)
            self.assertEqual(report["skipped_levels"][0]["source"], "removed")
            reloaded = read_current_levels(prepared / "levels.txt")
            self.assertEqual(len(reloaded), len(records))

    def test_reads_alpha_six_column_progress_before_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "levels.txt").write_text(
                "component_factory,true,11,22,33,RISCV/ALU\n",
                encoding="utf-8",
            )
            database = root / "_progress.dat"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE levels (id TEXT, complete INTEGER, selected_schematic TEXT)"
                )
                connection.execute(
                    "INSERT INTO levels VALUES ('component_factory', 'false', 'stale')"
                )
                connection.commit()

            direct = read_alpha_levels(root / "levels.txt")
            preferred = read_legacy_levels(root)
            self.assertTrue(direct[0].complete)
            self.assertEqual(preferred[0].selected_schematic, "RISCV/ALU")

    def test_foundry_mapping_accepts_legacy_component_factory_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            prepared = root / "prepared"
            game = root / "game"
            source.mkdir()
            prepared.mkdir()
            (game / "campaign" / "foundry").mkdir(parents=True)
            unit = prepared / "schematics" / "component_factory" / "RISCV" / "ALU"
            unit.mkdir(parents=True)
            (unit / "circuit.data").write_bytes(b"x")
            (source / "levels.txt").write_text(
                "component_factory,true,0,0,0,RISCV/ALU\n",
                encoding="utf-8",
            )
            (prepared / "levels.txt").write_text("", encoding="utf-8")

            records, _ = merge_progress(source, prepared, game_dir=game)
            foundry = next(record for record in records if record.level_id == "foundry")
            self.assertTrue(foundry.complete)
            self.assertEqual(foundry.selected_schematic, "RISCV/ALU")


if __name__ == "__main__":
    unittest.main()
