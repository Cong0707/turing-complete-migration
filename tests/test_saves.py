from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from unittest.mock import Mock, patch

from turing_complete_migration.saves import detect_generation, steam_is_running


def create_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE progress (key TEXT, value TEXT)")
        connection.commit()


class SaveDetectionTests(unittest.TestCase):
    def test_detects_alpha_by_six_column_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_database(root / "_progress.dat")
            (root / "levels.txt").write_text(
                "sandbox,true,0,0,0,RV64\n",
                encoding="utf-8",
            )
            generation, evidence = detect_generation(root)
            self.assertEqual(generation, "2.0.x alpha")
            self.assertIn("levels.txt first row has 6 columns", evidence)

    def test_detects_current_by_four_column_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_database(root / "_progress.dat")
            (root / "levels.txt").write_text(
                '"sandbox",true,"RV64",\n',
                encoding="utf-8",
            )
            generation, evidence = detect_generation(root)
            self.assertEqual(generation, "2.1+ current")
            self.assertIn("levels.txt first row has 4 columns", evidence)

    def test_detects_running_steam_from_tasklist(self):
        completed = Mock(stdout='"steam.exe","101","Console","1","100 K"\n')
        with patch("turing_complete_migration.saves.os.name", "nt"), patch(
            "turing_complete_migration.saves.subprocess.run",
            return_value=completed,
        ):
            self.assertTrue(steam_is_running())


if __name__ == "__main__":
    unittest.main()
