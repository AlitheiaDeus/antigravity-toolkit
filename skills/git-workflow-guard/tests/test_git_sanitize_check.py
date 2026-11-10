#!/usr/bin/env python3
"""
test_git_sanitize_check.py - Unit tests for git_sanitize_check.py
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
import sys
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from git_sanitize_check import (
    audit_gitignore,
    fix_gitignore,
    scan_for_path_leaks,
    scan_for_secrets
)


class TestGitSanitizeCheck(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="git_sanitize_test_")
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_audit_and_fix_gitignore(self):
        """Test detecting missing gitignore rules and auto-fixing them."""
        # Initially empty gitignore
        gi_file = self.root / ".gitignore"
        gi_file.write_text("# Initial\nbuild/\n", encoding="utf-8")

        clean, missing = audit_gitignore(self.root)
        self.assertFalse(clean)
        self.assertGreater(len(missing), 0)

        # Fix it
        fix_gitignore(self.root)

        # Audit again
        clean_after, missing_after = audit_gitignore(self.root)
        self.assertTrue(clean_after)
        self.assertEqual(len(missing_after), 0)

        content = gi_file.read_text(encoding="utf-8")
        self.assertIn("internal/", content)
        self.assertIn("scratch/", content)
        self.assertIn(".env", content)

    def test_detect_path_leaks(self):
        """Test detecting hardcoded user machine paths."""
        leaky_content = (
            "# Config\n"
            + 'path = "C:\\\\' + 'Users\\\\JohnDoe\\\\Documents\\\\secret"\n'
            + 'portable_path = os.environ.get("HOME")\n'
            + 'linux_path = "/' + 'home/developer/workspace/app"\n'
        )
        p = self.root / "config.py"
        files = [(p, leaky_content)]

        issues = scan_for_path_leaks(files, current_user="JohnDoe")
        self.assertEqual(len(issues), 2)
        descs = [iss[2] for iss in issues]
        self.assertIn("Windows user profile path", descs)
        self.assertIn("Unix/macOS home directory path", descs)

    def test_detect_secrets(self):
        """Test detecting API keys and staged .env files."""
        secret_content = (
            '\nGOOGLE_KEY = "' + "AIza" + 'SyD-1234567890abcdefghijklmnopqrst"\n'
            + 'GITHUB_TOKEN = "' + "ghp_" + '123456789012345678901234567890123456"\n'
        )
        p = self.root / "secrets.py"
        files = [(p, secret_content)]

        issues = scan_for_secrets(files)
        self.assertEqual(len(issues), 2)

        # Test .env file detection
        env_file = self.root / ".env"
        env_files = [(env_file, "DATABASE_URL=postgres://...")]
        env_issues = scan_for_secrets(env_files)
        self.assertEqual(len(env_issues), 1)
        self.assertEqual(env_issues[0][2], "Staged Environment Secret File")

    def test_suppression_comments(self):
        """Test that # noqa: path-leak and # noqa: secret suppress false positives."""
        suppressed_content = (
            'path = "C:\\\\' + 'Users\\\\JohnDoe\\\\Documents"  # noqa: path-leak\n'
            + 'key = "' + "AIza" + 'SyD-1234567890abcdefghijklmnopqrst"  # noqa: secret\n'
        )
        p = self.root / "suppressed.py"
        files = [(p, suppressed_content)]
        path_issues = scan_for_path_leaks(files, current_user="JohnDoe")
        secret_issues = scan_for_secrets(files)
        self.assertEqual(len(path_issues), 0)
        self.assertEqual(len(secret_issues), 0)


if __name__ == "__main__":
    unittest.main()
