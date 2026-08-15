import tempfile
import unittest
from pathlib import Path

from desktop_selection import DesktopSelection, resolve_desktop_item


class DesktopSelectionTests(unittest.TestCase):
    def test_resolves_exact_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "爆破目标.txt"
            target.write_text("demo", encoding="utf-8")
            self.assertEqual(resolve_desktop_item(target.name, [Path(directory)]), target)

    def test_resolves_hidden_extension_label(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "爆破目标.png"
            target.write_bytes(b"demo")
            self.assertEqual(resolve_desktop_item(target.stem, [Path(directory)]), target)

    def test_rejects_ambiguous_hidden_extension_label(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "目标.png").write_bytes(b"one")
            (root / "目标.txt").write_bytes(b"two")
            self.assertIsNone(resolve_desktop_item("目标", [root]))

    def test_does_not_resolve_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "文件夹"
            folder.mkdir()
            self.assertIsNone(resolve_desktop_item(folder.name, [Path(directory)]))

    def test_selection_center(self):
        selection = DesktopSelection(Path("demo.txt"), 10, 20, 50, 80)
        self.assertEqual(selection.center, (30, 50))


if __name__ == "__main__":
    unittest.main()
