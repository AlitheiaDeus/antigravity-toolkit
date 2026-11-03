#!/usr/bin/env python3
"""
test_scan_landmarks.py - Unit tests for scan_landmarks.py
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
import sys
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from scan_landmarks import LandmarkScanner, scan_directory


class TestScanLandmarks(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="landmarks_test_")
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_python_ast_parsing(self):
        """Test AST parsing extracts classes, methods, functions, and main guards."""
        code = '''"""Sample module docstring."""

import os

CONSTANT = 42

def helper_function(x):
    return x * 2

class WorkerEngine:
    def __init__(self, name):
        self.name = name

    def execute(self):
        # [LANDMARK: inner_execution_loop] Core dispatch loop
        return True

if __name__ == "__main__":
    w = WorkerEngine("test")
    w.execute()
'''
        py_file = self.root / "sample.py"
        py_file.write_text(code, encoding="utf-8")

        scanner = LandmarkScanner(py_file)
        self.assertTrue(scanner.load())
        nodes = scanner.scan()

        # Check DOC
        doc_nodes = [n for n in nodes if n.kind == "DOC"]
        self.assertEqual(len(doc_nodes), 1)
        self.assertEqual(doc_nodes[0].start_line, 1)

        # Check FUNC
        fn_nodes = [n for n in nodes if n.kind == "FUNC"]
        self.assertEqual(len(fn_nodes), 1)
        self.assertEqual(fn_nodes[0].name, "helper_function")

        # Check CLASS & METHOD
        cls_nodes = [n for n in nodes if n.kind == "CLASS"]
        self.assertEqual(len(cls_nodes), 1)
        self.assertEqual(cls_nodes[0].name, "WorkerEngine")
        self.assertEqual(len(cls_nodes[0].children), 2)
        self.assertEqual(cls_nodes[0].children[0].name, "WorkerEngine.__init__")
        self.assertEqual(cls_nodes[0].children[1].name, "WorkerEngine.execute")

        # Check manual landmark inside execute method
        lm_nodes = [n for n in nodes if n.kind == "LANDMARK"]
        self.assertEqual(len(lm_nodes), 1)
        self.assertEqual(lm_nodes[0].name, "inner_execution_loop")
        self.assertEqual(lm_nodes[0].detail, "Core dispatch loop")

        # Check ENTRY
        entry_nodes = [n for n in nodes if n.kind == "ENTRY"]
        self.assertEqual(len(entry_nodes), 1)

    def test_markdown_heading_spans(self):
        """Test markdown headings are mapped with correct span boundaries."""
        doc = """# Document Title

Introductory paragraph.

## Section 1: Overview
Content for section 1.
More content.

### Subsection 1.1: Details
Specific technical details.

## Section 2: Conclusion
Wrap-up notes.
"""
        md_file = self.root / "doc.md"
        md_file.write_text(doc, encoding="utf-8")

        scanner = LandmarkScanner(md_file)
        self.assertTrue(scanner.load())
        nodes = scanner.scan()

        self.assertEqual(len(nodes), 4)
        h1 = nodes[0]
        self.assertEqual(h1.kind, "H1")
        self.assertEqual(h1.name, "Document Title")

        sec1 = nodes[1]
        self.assertEqual(sec1.kind, "H2")
        self.assertEqual(sec1.name, "Section 1: Overview")
        # sec1 starts at line 5 and ends before sec2 at line 12
        self.assertEqual(sec1.start_line, 5)
        self.assertEqual(sec1.end_line, 11)

    def test_find_and_slice(self):
        """Test finding symbols and slicing code lines."""
        code = """line 1
line 2
# [LANDMARK: target_anchor] This is the target
line 4
line 5
"""
        target_file = self.root / "test_slice.py"
        target_file.write_text(code, encoding="utf-8")

        scanner = LandmarkScanner(target_file)
        scanner.load()
        scanner.scan()

        matches = scanner.find("target_anchor")
        self.assertEqual(len(matches), 1)
        node, _ = matches[0]
        self.assertEqual(node.start_line, 3)

        sliced = scanner.slice_lines(node.start_line, node.end_line, context=1)
        self.assertIn("line 2", sliced)
        self.assertIn("3 > # [LANDMARK: target_anchor]", sliced)
        self.assertIn("line 4", sliced)

    def test_directory_scan(self):
        """Test directory scanning finds landmarks across multiple files."""
        sub1 = self.root / "sub1"
        sub2 = self.root / "sub2"
        sub1.mkdir()
        sub2.mkdir()

        (sub1 / "a.py").write_text("# [LANDMARK: tag_a] In python\ndef a(): pass", encoding="utf-8")
        (sub2 / "b.js").write_text("// [BM: tag_b] In javascript\nconst b = 1;", encoding="utf-8")

        results = scan_directory(self.root)
        self.assertEqual(len(results), 2)
        tags = [n.name for _, nodes in results for n in nodes]
        self.assertIn("tag_a", tags)
        self.assertIn("tag_b", tags)


if __name__ == "__main__":
    unittest.main()
