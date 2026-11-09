#!/usr/bin/env python3
"""
Unit tests for system_mapper_ctl.py
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path so we can import system_mapper_ctl directly
import sys
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import system_mapper_ctl as sm


class TestSystemMapperCtl(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="sys_mapper_test_")
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sanitize_node_id(self):
        self.assertEqual(sm.sanitize_node_id("api/v1/routes.py"), "node_api_v1_routes_py")
        self.assertEqual(sm.sanitize_node_id("services-core.ts"), "node_services_core_ts")
        self.assertEqual(sm.sanitize_node_id(""), "node_root")

    def test_classify_file_heuristics(self):
        self.assertEqual(sm.classify_file(Path("api/routes.py")), "entrypoint")
        self.assertEqual(sm.classify_file(Path("workers/email_queue.py")), "async")
        self.assertEqual(sm.classify_file(Path("models/database.py")), "storage")
        self.assertEqual(sm.classify_file(Path("clients/stripe_adapter.py")), "external")
        self.assertEqual(sm.classify_file(Path("legacy/old_sync.py")), "flag")
        self.assertEqual(sm.classify_file(Path("config/settings.yaml")), "config")
        self.assertEqual(sm.classify_file(Path("services/calculation_engine.py")), "core")

    def test_extract_file_role_python_docstring(self):
        py_file = self.root / "billing.py"
        py_file.write_text('"""\nCalculates monthly subscription invoices and applies promo discounts.\n"""\n\ndef run(): pass', encoding="utf-8")
        role = sm.extract_file_role(py_file, Path("billing.py"))
        self.assertTrue("Calculates monthly subscription invoices" in role)

    def test_extract_file_role_js_comment_and_license_strip(self):
        js_file = self.root / "auth.js"
        js_file.write_text('// Copyright 2026 Acme Corp. All rights reserved.\n// Validates JWT session tokens for incoming HTTP requests.\nconst x = 1;', encoding="utf-8")
        role = sm.extract_file_role(js_file, Path("auth.js"))
        self.assertTrue("Validates JWT session tokens" in role)
        self.assertFalse("Copyright" in role)

    def test_find_codebase_files_and_ignores(self):
        # Create normal files
        (self.root / "api").mkdir(parents=True)
        (self.root / "api" / "routes.py").write_text("# API routes\n", encoding="utf-8")

        # Create ignored directory with files
        (self.root / "node_modules").mkdir(parents=True)
        (self.root / "node_modules" / "express.js").write_text("# Ignored\n", encoding="utf-8")

        (self.root / ".git").mkdir(parents=True)
        (self.root / ".git" / "config").write_text("# Git config\n", encoding="utf-8")

        scanned = sm.find_codebase_files(self.root)
        rel_paths = [r.as_posix() for _, r in scanned]

        self.assertIn("api/routes.py", rel_paths)
        self.assertNotIn("node_modules/express.js", rel_paths)
        self.assertNotIn(".git/config", rel_paths)

    def test_detect_file_dependencies(self):
        # Setup files that import each other
        (self.root / "services").mkdir(parents=True)
        svc = self.root / "services" / "payment.py"
        svc.write_text("from db import get_user_db\nimport stripe_client\n", encoding="utf-8")

        stems = {
            "db": "database/db.py",
            "stripe_client": "clients/stripe_client.py",
            "unrelated": "other/unrelated.py"
        }

        deps = sm.detect_file_dependencies(svc, stems)
        self.assertIn("database/db.py", deps)
        self.assertIn("clients/stripe_client.py", deps)
        self.assertNotIn("other/unrelated.py", deps)

    def test_build_system_map_and_domain_grouping(self):
        # Setup mini architecture
        (self.root / "api").mkdir(parents=True)
        (self.root / "services").mkdir(parents=True)
        (self.root / "db").mkdir(parents=True)

        (self.root / "api" / "router.py").write_text('"""Handles incoming HTTP requests."""\nimport order_service', encoding="utf-8")
        (self.root / "services" / "order_service.py").write_text('"""Processes orders."""\nimport database', encoding="utf-8")
        (self.root / "db" / "database.py").write_text('"""Stores persistent user orders."""\n', encoding="utf-8")

        data = sm.build_system_map(self.root)
        self.assertEqual(data["total_files"], 3)

        comps = {c["filename"]: c for c in data["components"]}
        self.assertEqual(comps["router.py"]["domain"], "api")
        self.assertEqual(comps["router.py"]["category"], "entrypoint")
        self.assertEqual(comps["order_service.py"]["category"], "core")
        self.assertEqual(comps["database.py"]["category"], "storage")

    def test_generate_mermaid_flowchart(self):
        system_data = {
            "total_files": 2,
            "root": str(self.root),
            "components": [
                {
                    "id": "node_api_router_py",
                    "path": "api/router.py",
                    "filename": "router.py",
                    "domain": "api",
                    "category": "entrypoint",
                    "role": "Dispatches API calls.",
                    "dependencies": ["services/billing.py"]
                },
                {
                    "id": "node_services_billing_py",
                    "path": "services/billing.py",
                    "filename": "billing.py",
                    "domain": "services",
                    "category": "core",
                    "role": "Calculates billing.",
                    "dependencies": []
                }
            ]
        }

        mermaid = sm.generate_mermaid_flowchart(system_data)
        self.assertIn("flowchart TD", mermaid)
        self.assertIn("classDef entrypoint", mermaid)
        self.assertIn("classDef core", mermaid)
        self.assertIn("node_api_router_py --> node_services_billing_py", mermaid)
        self.assertIn("subgraph sub_1_api", mermaid)

    def test_generate_system_table(self):
        system_data = {
            "components": [
                {
                    "path": "api/routes.py",
                    "filename": "routes.py",
                    "domain": "api",
                    "category": "entrypoint",
                    "role": "Entrypoint routes.",
                    "dependencies": ["services/logic.py"]
                }
            ]
        }
        table = sm.generate_system_table(system_data)
        self.assertIn("| Component / File | Domain | Category |", table)
        self.assertIn("`api/routes.py`", table)
        self.assertIn("🔵 Entrypoint", table)

    def test_find_codebase_files_with_exclude_dirs(self):
        (self.root / "src").mkdir(parents=True)
        (self.root / "src" / "app.py").write_text("# app\n", encoding="utf-8")
        (self.root / "tests_temp").mkdir(parents=True)
        (self.root / "tests_temp" / "dummy.py").write_text("# dummy test\n", encoding="utf-8")

        files = sm.find_codebase_files(self.root, exclude_dirs={"tests_temp"})
        rel_paths = [r.as_posix() for _, r in files]
        self.assertIn("src/app.py", rel_paths)
        self.assertNotIn("tests_temp/dummy.py", rel_paths)

    def test_detect_multi_import_dependencies(self):
        (self.root / "services").mkdir(parents=True)
        svc = self.root / "services" / "multi_import.py"
        svc.write_text("from app.core import auth, session, metrics\nimport config, utils\n", encoding="utf-8")

        stems = {
            "auth": "core/auth.py",
            "session": "core/session.py",
            "utils": "common/utils.py"
        }

        deps = sm.detect_file_dependencies(svc, stems)
        self.assertIn("core/auth.py", deps)
        self.assertIn("core/session.py", deps)
        self.assertIn("common/utils.py", deps)

    def test_hotspots_detection(self):
        # Case 1: Layer violation: entrypoint directly calling storage
        system_data = {
            "components": [
                {
                    "path": "api/routes.py",
                    "category": "entrypoint",
                    "role": "Routes",
                    "dependencies": ["db/models.py"]
                },
                {
                    "path": "db/models.py",
                    "category": "storage",
                    "role": "Models",
                    "dependencies": []
                },
                {
                    "path": "legacy/old_hack.py",
                    "category": "flag",
                    "role": "Legacy sync hack",
                    "dependencies": []
                }
            ]
        }
        report = sm.generate_telemetry_report(system_data)
        self.assertIn("Architectural Telemetry", report)

    def test_detect_god_files_and_subsystems(self):
        code = '''
class SwarmSimulator:
    def __init__(self):
        self.c2 = C2Gateway()
    def _rf_calc_loss(self): pass
    def _rf_apply_jammer(self): pass
    def _rf_get_horizon(self): pass
    def _atc_reserve(self): pass
'''
        res = sm.detect_god_files_and_subsystems(Path("sim.py"), code, line_threshold=8)
        self.assertIsNotNone(res)
        self.assertEqual(res["file"], "sim.py")
        pfx_names = [s["prefix"] for s in res["detected_subsystems"]]
        self.assertIn("rf", pfx_names)
        self.assertTrue(any("self.c2" in inst for inst in res["embedded_instances"]))

    def test_detect_proxy_tightropes(self):
        code = '''
class SwarmSimulator:
    def deploy_payload_drop(self, a): return self.c2.deploy_payload_drop(a)
    def start_rng_recon(self, b): return self.c2.start_rng_recon(b)
    def deploy_mission_route(self, c): self.c2.deploy_mission_route(c)
'''
        proxies = sm.detect_proxy_tightropes(Path("sim.py"), code)
        self.assertEqual(len(proxies), 1)
        self.assertEqual(proxies[0]["target"], "self.c2")
        self.assertEqual(proxies[0]["proxy_count"], 3)

    def test_detect_in_memory_bleeds(self):
        code = '''
class WebServer:
    def __init__(self, sim):
        self.sim = sim
'''
        bleeds = sm.detect_in_memory_bleeds(Path("web_server.py"), code)
        self.assertEqual(len(bleeds), 1)
        self.assertEqual(bleeds[0]["severity"], "HIGH")
        self.assertIn("self.sim", bleeds[0]["leak"])

    def test_detect_roadmap_tickets(self):
        code = '''
# TKT-61: Extract sitl_engine subsystems
# TODO: Refactor MAVLink queue
def run(): pass
'''
        tickets = sm.detect_roadmap_tickets(Path("engine.py"), code)
        tags = [t["tag"] for t in tickets]
        self.assertIn("TKT-61", tags)
        self.assertIn("TODO", tags)

    def test_detect_network_bindings(self):
        code = '''
# MAVLink UDP loopback on Port 9000
# WebSocket streaming on Port 9001
def bind(): pass
'''
        bindings = sm.detect_network_bindings(Path("bridge.py"), code)
        ports = [b["port"] for b in bindings]
        self.assertIn(9000, ports)
        self.assertIn(9001, ports)


if __name__ == "__main__":
    unittest.main()
