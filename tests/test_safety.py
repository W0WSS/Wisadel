import os
import tempfile
import unittest
from pathlib import Path

from safety import assert_unchanged, validate_target


class SafetyTests(unittest.TestCase):
    def test_accepts_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.txt"
            target.write_text("before", encoding="utf-8")
            path, saved = validate_target(target, __file__)
            self.assertEqual(path, target.absolute())
            assert_unchanged(path, saved)

    def test_rejects_missing_file(self):
        with self.assertRaisesRegex(ValueError, "不存在"):
            validate_target("definitely-missing.file", __file__)

    def test_detects_replaced_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.txt"
            target.write_text("before", encoding="utf-8")
            path, saved = validate_target(target, __file__)
            target.unlink()
            target.write_text("after and different", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "发生了变化"):
                assert_unchanged(path, saved)

    def test_does_not_follow_final_symlink(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "real.txt"
            destination.write_text("content", encoding="utf-8")
            link = Path(directory) / "link.txt"
            try:
                link.symlink_to(destination)
            except OSError:
                self.skipTest("symlink creation unavailable")
            path, _ = validate_target(link, __file__)
            self.assertEqual(path, link.absolute())


if __name__ == "__main__":
    unittest.main()
