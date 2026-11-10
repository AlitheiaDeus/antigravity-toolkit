#!/usr/bin/env python3
"""
Unit tests for code_starmap_ctl.py
"""

import json
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

# Add scripts directory to sys.path
import sys
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import code_starmap_ctl as cs


class TestCodeStarmapCtl(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="starmap_test_")
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_symbol_discovery_and_docstrings(self):
        py_file = self.root / "math_lib.py"
        py_file.write_text(
            '"""\nMath utility library.\n"""\n\n'
            'def add(a, b):\n'
            '    """Returns sum of two numbers."""\n'
            '    return a + b\n\n'
            'class Vector:\n'
            '    def magnitude(self):\n'
            '        """Computes Euclidean magnitude."""\n'
            '        return 1.0\n',
            encoding="utf-8"
        )

        scout = cs.ASTCallScout(self.root)
        scout.scan()

        self.assertIn("math_lib.py:add", scout.nodes)
        self.assertIn("math_lib.py:Vector.magnitude", scout.nodes)

        add_node = scout.nodes["math_lib.py:add"]
        self.assertEqual(add_node.label, "add")
        self.assertEqual(add_node.doc, "Returns sum of two numbers.")
        self.assertEqual(add_node.line_start, 5)

        mag_node = scout.nodes["math_lib.py:Vector.magnitude"]
        self.assertEqual(mag_node.label, "Vector.magnitude")
        self.assertEqual(mag_node.doc, "Computes Euclidean magnitude.")

    def test_call_graph_resolution_intra_and_cross_module(self):
        (self.root / "calc.py").write_text(
            'def helper():\n'
            '    return 42\n\n'
            'def compute():\n'
            '    return helper()\n',
            encoding="utf-8"
        )

        (self.root / "main.py").write_text(
            'from calc import compute\n\n'
            'def run():\n'
            '    val = compute()\n'
            '    return val\n',
            encoding="utf-8"
        )

        scout = cs.ASTCallScout(self.root)
        scout.scan()

        edge_pairs = [(e.source, e.target) for e in scout.edges]
        self.assertIn(("calc.py:compute", "calc.py:helper"), edge_pairs)
        self.assertIn(("main.py:run", "calc.py:compute"), edge_pairs)

    def test_exclude_tests_filter(self):
        (self.root / "core.py").write_text("def prod(): pass\n", encoding="utf-8")
        test_dir = self.root / "tests"
        test_dir.mkdir()
        (test_dir / "test_core.py").write_text("def test_prod(): pass\n", encoding="utf-8")

        # Without filter
        scout_all = cs.ASTCallScout(self.root, exclude_tests=False)
        scout_all.scan()
        self.assertEqual(len(scout_all.nodes), 2)

        # With --no-tests filter
        scout_filtered = cs.ASTCallScout(self.root, exclude_tests=True)
        scout_filtered.scan()
        self.assertEqual(len(scout_filtered.nodes), 1)
        self.assertIn("core.py:prod", scout_filtered.nodes)

    def test_exclude_externals_filter(self):
        (self.root / "app.py").write_text("import os\ndef run(): return os.getenv('KEY')\n", encoding="utf-8")

        # Without filter: includes ext:os.getenv
        scout_all = cs.ASTCallScout(self.root, exclude_externals=False)
        scout_all.scan()
        self.assertTrue(any("os.getenv" in n for n in scout_all.nodes))

        # With --no-externals filter: only internal app.py:run
        scout_internal = cs.ASTCallScout(self.root, exclude_externals=True)
        scout_internal.scan()
        self.assertFalse(any("os.getenv" in n for n in scout_internal.nodes))
        self.assertIn("app.py:run", scout_internal.nodes)

    def test_file_level_graph_aggregation(self):
        (self.root / "service.py").write_text(
            'def handle_request():\n'
            '    return 1\n',
            encoding="utf-8"
        )
        (self.root / "client.py").write_text(
            'from service import handle_request\n\n'
            'def call_a():\n'
            '    handle_request()\n\n'
            'def call_b():\n'
            '    handle_request()\n',
            encoding="utf-8"
        )

        scout = cs.ASTCallScout(self.root)
        scout.scan()

        file_nodes, file_edges = cs.build_file_level_graph(scout)
        self.assertEqual(len(file_nodes), 2)

        # Inter-file edge from client.py to service.py should have weight 2
        edge = next((fe for fe in file_edges if fe.source == "client.py" and fe.target == "service.py"), None)
        self.assertIsNotNone(edge)
        self.assertEqual(edge.weight, 2)
        self.assertEqual(len(edge.pipes), 2)

    def test_gexf_13_with_viz_and_weights(self):
        (self.root / "mod.py").write_text('def f(): pass\n', encoding="utf-8")
        scout = cs.ASTCallScout(self.root)
        scout.scan()

        gexf_file = self.root / "output.gexf"
        cs.export_gexf(scout, gexf_file, level="file")

        self.assertTrue(gexf_file.exists())
        tree = ET.parse(str(gexf_file))
        root = tree.getroot()
        self.assertTrue(root.tag.endswith("gexf"))
        self.assertEqual(root.attrib.get("version"), "1.3")

        # Verify viz:color and viz:size presence
        node_el = root.find(".//{http://gexf.net/1.3}node")
        self.assertIsNotNone(node_el)
        color_el = node_el.find("{http://gexf.net/1.3/viz}color")
        size_el = node_el.find("{http://gexf.net/1.3/viz}size")
        self.assertIsNotNone(color_el)
        self.assertIsNotNone(size_el)

    def test_html_export_generation(self):
        (self.root / "mod.py").write_text('def f(): pass\n', encoding="utf-8")
        scout = cs.ASTCallScout(self.root)
        scout.scan()

        html_file = self.root / "starmap.html"
        cs.export_html(scout, html_file)

        self.assertTrue(html_file.exists())
        content = html_file.read_text(encoding="utf-8")
        self.assertIn("Code Starmap", content)
        self.assertIn('"files"', content)
        self.assertIn('"functions"', content)

    def test_mermaid_lens_export(self):
        (self.root / "mod.py").write_text('def a(): b()\ndef b(): pass\n', encoding="utf-8")
        scout = cs.ASTCallScout(self.root)
        scout.scan()

        mermaid_code = cs.export_mermaid_lens(scout.nodes, scout.edges, focus="a", depth=1)
        self.assertIn("flowchart LR", mermaid_code)
        self.assertIn("★ a ★", mermaid_code)


if __name__ == "__main__":
    unittest.main()
