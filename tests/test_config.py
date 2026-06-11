"""Tests for config.py — path resolution and constants."""
import os
import sys
import unittest


class TestGetBaseDir(unittest.TestCase):
    def test_returns_string(self):
        import config
        result = config.get_base_dir()
        self.assertIsInstance(result, str)

    def test_returns_existing_directory(self):
        import config
        result = config.get_base_dir()
        self.assertTrue(os.path.isdir(result), f"BASE_DIR does not exist: {result}")

    def test_not_frozen_returns_file_dir(self):
        """In dev (non-frozen) mode, BASE_DIR should be the project root."""
        import config
        # sys.frozen is not set in test environment
        self.assertFalse(getattr(sys, 'frozen', False))
        expected = os.path.dirname(os.path.abspath(config.__file__))
        self.assertEqual(config.BASE_DIR, expected)

    def test_derived_paths_are_absolute(self):
        import config
        for path in [config.DATA_DIR, config.DB_PATH, config.DB_BACKUP_DIR,
                     config.CASES_DIR, config.EVAL_DIR, config.INTERVIEW_BANKS_DIR]:
            self.assertTrue(os.path.isabs(path), f"Expected absolute path: {path}")

    def test_db_path_ends_with_db(self):
        import config
        self.assertTrue(config.DB_PATH.endswith(".db"))

    def test_case_systems_list(self):
        import config
        self.assertIn("foundations", config.CASE_SYSTEMS)
        self.assertIn("drills", config.CASE_SYSTEMS)
        self.assertIn("cardio", config.CASE_SYSTEMS)
        self.assertIn("gi", config.CASE_SYSTEMS)
        self.assertIn("pulm", config.CASE_SYSTEMS)
        self.assertIn("neuro", config.CASE_SYSTEMS)
        self.assertEqual(len(config.CASE_SYSTEMS), 6)

    def test_window_size_format(self):
        import config
        parts = config.WINDOW_SIZE.split("x")
        self.assertEqual(len(parts), 2)
        width, height = int(parts[0]), int(parts[1])
        self.assertGreater(width, 600)
        self.assertGreater(height, 400)

    def test_max_backups_positive_int(self):
        import config
        self.assertIsInstance(config.MAX_DB_BACKUPS, int)
        self.assertGreater(config.MAX_DB_BACKUPS, 0)


if __name__ == "__main__":
    unittest.main()
