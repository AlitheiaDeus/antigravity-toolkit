#!/usr/bin/env python3
"""
test_deslop_ctl.py - Unittest Suite for Antigravity Code De-Slop Engine

Tests detection of AI enterprise foam, chat debris, meme variables,
AST patterns, sacred StackOverflow fences, safety fork, and stripping.
"""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import deslop_ctl


class TestSlopDetection(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="deslop_test_"))

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_chat_debris_detection(self):
        code = (
            "# Normal comment explaining domain logic\n"
            "x = 10\n"
            "# Fixed this portion for you as requested\n"
            "y = 20\n"
            "# I turned this image 30 degrees as requested\n"
            "z = 30\n"
            "# Look here: temporary fix\n"
        )
        sample = self.test_dir / "sample.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir)
        chat_findings = [f for f in findings if f.category == "AI_CHAT_DEBRIS"]

        self.assertEqual(len(chat_findings), 3)
        self.assertTrue(any("Fixed this portion" in f.snippet for f in chat_findings))
        self.assertTrue(any("turned this image" in f.snippet for f in chat_findings))
        self.assertTrue(any("Look here" in f.snippet for f in chat_findings))

    def test_sacred_fence_detection(self):
        code = (
            "# See https://stackoverflow.com/a/12345678 for why this mask is needed\n"
            "mask = 0xFF & offset\n"
            "# workaround for win32 console freeze\n"
            "import ctypes\n"
            "handle = ctypes.windll.kernel32.GetStdHandle(-11)\n"
        )
        sample = self.test_dir / "platform_fix.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir)
        fences = [f for f in findings if f.category == "SACRED_FENCE"]

        self.assertGreaterEqual(len(fences), 2)
        self.assertTrue(any("KEEP_UNTOUCHED" in f.recommendation for f in fences))

    def test_meme_and_brainrot_detection(self):
        code = (
            "yeet_counter = 5\n"
            "cursed_blob_val = compute()\n"
            "if is_sus_flag:\n"
            "    pass\n"
        )
        sample = self.test_dir / "memes.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir)
        memes = [f for f in findings if f.category == "HUMAN_MEME"]

        self.assertGreaterEqual(len(memes), 2)
        self.assertTrue(any("yeet" in f.snippet for f in memes))

    def test_ast_empty_custom_exception(self):
        code = (
            "class ConfigNotFoundError(Exception):\n"
            "    pass\n"
            "\n"
            "class ValidError(Exception):\n"
            "    def __init__(self, code):\n"
            "        self.code = code\n"
        )
        sample = self.test_dir / "exceptions.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir)
        exc_findings = [f for f in findings if f.category == "AI_EMPTY_EXCEPTION"]

        self.assertEqual(len(exc_findings), 1)
        self.assertIn("ConfigNotFoundError", exc_findings[0].explanation)

    def test_ast_single_method_class(self):
        code = (
            "class DataSanitizer:\n"
            "    def __init__(self, prefix):\n"
            "        self.prefix = prefix\n"
            "    def sanitize(self, raw):\n"
            "        return self.prefix + str(raw)\n"
        )
        sample = self.test_dir / "service.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir)
        class_findings = [f for f in findings if f.category == "AI_SINGLE_METHOD_CLASS"]

        self.assertEqual(len(class_findings), 1)
        self.assertIn("DataSanitizer", class_findings[0].explanation)
        self.assertIn("COLLAPSE", class_findings[0].recommendation)

    def test_ast_tautological_docstring(self):
        code = (
            "def calculate_total():\n"
            "    '''Calculate total.'''\n"
            "    return 42\n"
        )
        sample = self.test_dir / "taut.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir)
        taut_findings = [f for f in findings if f.category == "AI_TAUTOLOGY"]

        self.assertEqual(len(taut_findings), 1)
        self.assertIn("tautological", taut_findings[0].explanation.lower())

    def test_ast_panic_block(self):
        code = (
            "try:\n"
            "    dangerous_call()\n"
            "except Exception:\n"
            "    pass\n"
        )
        sample = self.test_dir / "panic.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir)
        panic_findings = [f for f in findings if f.category == "AI_PANIC_BLOCK"]

        self.assertEqual(len(panic_findings), 1)
        self.assertIn("FAIL_LOUD", panic_findings[0].recommendation)

    def test_ast_verbose_identifier(self):
        code = (
            "user_authenticated_session_state_boolean_flag = True\n"
        )
        sample = self.test_dir / "verbose.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir)
        verbose_findings = [f for f in findings if f.category == "AI_VERBOSE_NAME"]

        self.assertEqual(len(verbose_findings), 1)
        self.assertIn("user_authenticated_session_state_boolean_flag", verbose_findings[0].snippet)

    def test_strip_chat_debris(self):
        code = (
            "# Real logic comment\n"
            "a = 1\n"
            "# Fixed this portion for you\n"
            "b = 2\n"
            "# Look here\n"
            "c = 3\n"
        )
        sample = self.test_dir / "strip_sample.py"
        sample.write_text(code, encoding="utf-8")

        removed, msg = deslop_ctl.strip_chat_debris(sample)
        self.assertEqual(removed, 2)

        new_content = sample.read_text(encoding="utf-8")
        self.assertNotIn("Fixed this portion", new_content)
        self.assertNotIn("Look here", new_content)
        self.assertIn("Real logic comment", new_content)
        self.assertIn("b = 2", new_content)

        # Ensure syntax is valid
        ast.parse(new_content)

    def test_safety_fork_fs_fallback(self):
        file1 = self.test_dir / "test1.py"
        file1.write_text("print('hello')", encoding="utf-8")

        res = deslop_ctl.run_safety_fork(self.test_dir)
        self.assertEqual(res["mode"], "fs_copy")
        self.assertGreaterEqual(res["files_copied"], 1)
        self.assertTrue(Path(res["backup_dir"]).exists())

    def test_markdown_report_generation(self):
        code = (
            "# Fixed this for you as requested\n"
            "# https://stackoverflow.com/a/99999\n"
            "yeet_val = 1\n"
        )
        sample = self.test_dir / "report_test.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_path(self.test_dir)
        md = deslop_ctl.generate_markdown_report(findings, str(self.test_dir))

        self.assertIn("Code De-Slop & Grounding Audit Report", md)
        self.assertIn("Sacred Fences & Battle-Tested Hacks (KEEP)", md)
        self.assertIn("High-Confidence AI Slop Checklist", md)
        self.assertIn("Semantic Grounding & Variable Renaming Table", md)

    def test_unique_ids_across_multiple_files(self):
        f1 = self.test_dir / "mod1.py"
        f1.write_text("def w1(): return len('a')\n", encoding="utf-8")
        f2 = self.test_dir / "mod2.py"
        f2.write_text("def w2(): return len('b')\n", encoding="utf-8")

        findings = deslop_ctl.scan_path(self.test_dir)
        wrappers = [f for f in findings if f.category == "AI_ONE_SHOT_WRAPPER"]
        self.assertEqual(len(wrappers), 2)
        # Ensure IDs are unique across files
        self.assertEqual(wrappers[0].finding_id, "[AI-WRAP-01]")
        self.assertEqual(wrappers[1].finding_id, "[AI-WRAP-02]")

    def test_test_suite_slop_mock_theatre(self):
        code = (
            "def test_service_call():\n"
            "    mock_api.call.assert_called_once()\n"
        )
        sample = self.test_dir / "test_mock.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir, is_test_file=True)
        theatre = [f for f in findings if f.category == "AI_TEST_MOCK_THEATRE"]
        self.assertEqual(len(theatre), 1)
        self.assertIn("only asserts mock calls", theatre[0].explanation)

    def test_test_suite_slop_hollow_and_zero_assertions(self):
        code = (
            "def test_zero():\n"
            "    x = 10\n"
            "def test_hollow():\n"
            "    assert x is not None\n"
        )
        sample = self.test_dir / "test_hollow.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir, is_test_file=True)
        zero = [f for f in findings if f.category == "AI_TEST_ZERO_ASSERTION"]
        hollow = [f for f in findings if f.category == "AI_TEST_HOLLOW_ASSERTION"]
        self.assertEqual(len(zero), 1)
        self.assertEqual(len(hollow), 1)

    def test_test_suite_slop_suppressed_failure_and_sleep(self):
        code = (
            "import time\n"
            "def test_panic():\n"
            "    try:\n"
            "        assert False\n"
            "    except Exception:\n"
            "        pass\n"
            "def test_sleep():\n"
            "    time.sleep(2)\n"
            "    assert True\n"
        )
        sample = self.test_dir / "test_panic_sleep.py"
        sample.write_text(code, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir, is_test_file=True)
        panic = [f for f in findings if f.category == "AI_TEST_SUPPRESSED_FAILURE"]
        sleep = [f for f in findings if f.category == "AI_TEST_FLAKY_SLEEP"]
        self.assertEqual(len(panic), 1)
        self.assertEqual(len(sleep), 1)

    def test_markdown_doc_slop(self):
        doc = (
            "# My Guide\n\n"
            "Certainly! Below is the documentation as requested.\n"
            "In this comprehensive section, we delve deep into the logic.\n"
        )
        sample = self.test_dir / "GUIDE.md"
        sample.write_text(doc, encoding="utf-8")

        findings = deslop_ctl.scan_file(sample, self.test_dir)
        doc_slop = [f for f in findings if f.category == "AI_DOC_FOAM"]
        self.assertGreaterEqual(len(doc_slop), 1)

    def test_filename_slop(self):
        jawbreaker = "user_account_profile_management_controller_service.py"
        versioned = "billing_service_v2.py"
        self.assertIsNotNone(deslop_ctl.scan_filename_slop(jawbreaker))
        self.assertIsNotNone(deslop_ctl.scan_filename_slop(versioned))
        self.assertIsNone(deslop_ctl.scan_filename_slop("normal_file.py"))

    def test_unified_sweep_report(self):
        findings = [
            deslop_ctl.SlopFinding("[AI-CHAT-01]", "AI_CHAT_DEBRIS", "app.py", 1, "# fixed for you", "test", "test"),
            deslop_ctl.SlopFinding("[TEST-MOCK-01]", "AI_TEST_MOCK_THEATRE", "test_app.py", 10, "mock.called", "test", "test")
        ]
        scorecard = deslop_ctl.generate_unified_sweep_report(findings, str(self.test_dir))
        self.assertIn("Full Repository De-Slop Scorecard", scorecard)
        self.assertIn("Code Logic", scorecard)
        self.assertIn("Test Suites", scorecard)



if __name__ == "__main__":
    unittest.main()
