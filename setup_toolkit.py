#!/usr/bin/env python3
"""
setup_toolkit.py - 1-Click Antigravity Toolkit Installer & Verification Suite

Connects this repository's skills to Antigravity's global configuration via
a portable, home-relative path in ~/.gemini/config/skills.json, and verifies
all test suites pass.

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import json
import os
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent
SKILLS_DIR = REPO_ROOT / "skills"
CONFIG_DIR = Path.home() / ".gemini" / "config"
SKILLS_JSON = CONFIG_DIR / "skills.json"
ROSTER_START = "<!-- ROSTER:START -->"
ROSTER_END = "<!-- ROSTER:END -->"


def parse_skill_frontmatter(skill_md: Path) -> Dict[str, str]:
    """Parse name and description from YAML frontmatter (supports single-line and >- / | blocks)."""
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    fm_lines: List[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        fm_lines.append(line)

    result: Dict[str, str] = {}
    i = 0
    while i < len(fm_lines):
        m = re.match(r'^([A-Za-z0-9_\-]+)\s*:\s*(.*)$', fm_lines[i])
        if not m:
            i += 1
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        if val in (">-", ">", "|-", "|"):
            block: List[str] = []
            i += 1
            while i < len(fm_lines) and (fm_lines[i].startswith("  ") or fm_lines[i].startswith("\t") or fm_lines[i].strip() == ""):
                if fm_lines[i].strip():
                    block.append(fm_lines[i].strip())
                i += 1
            result[key] = " ".join(block)
            continue
        result[key] = val.strip("\"'")
        i += 1
    return result


def discover_skills(skills_dir: Path = SKILLS_DIR) -> List[Dict[str, Any]]:
    """Discover all skills with SKILL.md and their scripts/ entrypoints."""
    items: List[Dict[str, Any]] = []
    if not skills_dir.exists():
        return items

    for d in sorted(skills_dir.iterdir(), key=lambda p: p.name.lower()):
        skill_md = d / "SKILL.md"
        if not (d.is_dir() and skill_md.exists()):
            continue
        fm = parse_skill_frontmatter(skill_md)
        scripts_dir = d / "scripts"
        py_scripts = sorted(scripts_dir.glob("*.py")) if scripts_dir.exists() else []
        script_labels = [f"scripts/{p.name}" for p in py_scripts] if py_scripts else ["SKILL.md"]
        items.append({
            "dir_name": d.name,
            "name": fm.get("name") or d.name,
            "description": fm.get("description") or "(no description)",
            "scripts": script_labels,
        })
    return items


def update_readme_roster(repo_root: Path = REPO_ROOT) -> bool:
    """Regenerate the Active Skill Roster table in README.md between ROSTER markers."""
    readme = repo_root / "README.md"
    if not readme.exists():
        return False

    content = readme.read_text(encoding="utf-8")
    if ROSTER_START not in content or ROSTER_END not in content:
        return False

    skills = discover_skills(repo_root / "skills")
    rows = [
        ROSTER_START,
        "| Skill | Primary CLI Script | Core Operational Superpower |",
        "| :--- | :--- | :--- |",
    ]
    for s in skills:
        scripts_cell = ", ".join(f"`{sc}`" for sc in s["scripts"])
        desc_cell = s["description"].replace("|", "\\|").strip()
        rows.append(f"| **`{s['name']}`** | {scripts_cell} | {desc_cell} |")
    rows.append(ROSTER_END)

    new_block = "\n".join(rows)
    pattern = re.compile(rf"{re.escape(ROSTER_START)}.*?{re.escape(ROSTER_END)}", re.DOTALL)
    updated = pattern.sub(lambda _: new_block, content, count=1)
    if updated != content:
        readme.write_text(updated, encoding="utf-8")
        print(f"[OK] Updated README.md Active Skill Roster ({len(skills)} skills)")
    return True


def get_portable_path() -> str:
    """Computes a cross-platform home-relative path (~/...) if inside user home."""
    try:
        rel = SKILLS_DIR.relative_to(Path.home())
        return f"~/{rel.as_posix()}"
    except ValueError:
        return SKILLS_DIR.as_posix()


def check_status():
    print("=== Antigravity Toolkit Status ===")
    print(f"Repository Root: {REPO_ROOT}")
    print(f"Skills Directory: {SKILLS_DIR}")
    print(f"Antigravity Config: {CONFIG_DIR}")
    print(f"Config File: {SKILLS_JSON}")

    if not SKILLS_JSON.exists():
        print("\nStatus: [NOT CONNECTED] (skills.json does not exist)")
        return False

    try:
        data = json.loads(SKILLS_JSON.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
        portable = get_portable_path()
        abs_posix = SKILLS_DIR.as_posix()

        found = False
        for e in entries:
            p = e.get("path", "")
            if p == portable or p == abs_posix or Path(os.path.expanduser(p)).resolve() == SKILLS_DIR:
                found = True
                print(f"\nStatus: [CONNECTED] via '{p}'")
                break

        if not found:
            print(f"\nStatus: [NOT CONNECTED] (Toolkit path not found in skills.json entries)")
            return False

        # List skills cheat sheet from SKILL.md frontmatter
        skills = discover_skills(SKILLS_DIR)
        print(f"\nActive Skills Cheat Sheet ({len(skills)}):")
        for s in skills:
            scripts_str = ", ".join(s["scripts"])
            print(f"  * {s['name']:<22} [{scripts_str}]")
            print(f"    {s['description']}")
        return True

    except Exception as e:
        print(f"\nStatus: [ERROR] Failed to read skills.json: {e}")
        return False


def install():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    portable_path = get_portable_path()

    config_data = {"entries": []}
    if SKILLS_JSON.exists():
        try:
            config_data = json.loads(SKILLS_JSON.read_text(encoding="utf-8"))
            if not isinstance(config_data, dict):
                config_data = {"entries": []}
            if "entries" not in config_data or not isinstance(config_data["entries"], list):
                config_data["entries"] = []
        except Exception:
            config_data = {"entries": []}

    # Check if already present
    entries = config_data["entries"]
    already_present = False
    for e in entries:
        p = e.get("path", "")
        if p == portable_path or Path(os.path.expanduser(p)).resolve() == SKILLS_DIR:
            already_present = True
            break

    if not already_present:
        entries.append({"path": portable_path})
        config_data["entries"] = entries
        SKILLS_JSON.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
        print(f"[OK] Registered '{portable_path}' in {SKILLS_JSON}")
    else:
        print(f"[OK] '{portable_path}' is already registered in {SKILLS_JSON}")


def uninstall():
    if not SKILLS_JSON.exists():
        print("[INFO] skills.json does not exist. Nothing to uninstall.")
        return

    try:
        config_data = json.loads(SKILLS_JSON.read_text(encoding="utf-8"))
        entries = config_data.get("entries", [])
        portable = get_portable_path()

        new_entries = []
        removed = False
        for e in entries:
            p = e.get("path", "")
            if p == portable or Path(os.path.expanduser(p)).resolve() == SKILLS_DIR:
                removed = True
            else:
                new_entries.append(e)

        if removed:
            config_data["entries"] = new_entries
            SKILLS_JSON.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
            print(f"[OK] Removed toolkit path from {SKILLS_JSON}")
        else:
            print("[INFO] Toolkit path was not in skills.json.")
    except Exception as e:
        print(f"[ERROR] Failed to uninstall: {e}", file=sys.stderr)


def run_tests() -> bool:
    print("\n--- Running Toolkit Unit Tests ---")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Discover tests in all skill subdirectories
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            tests_dir = skill_dir / "tests"
            if tests_dir.exists():
                skill_suite = loader.discover(str(tests_dir), pattern="test_*.py", top_level_dir=str(tests_dir))
                suite.addTests(skill_suite)

    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    return result.wasSuccessful()


def main():
    parser = argparse.ArgumentParser(description="Antigravity Toolkit Bootstrapper")
    parser.add_argument("--status", action="store_true", help="Check current registration status")
    parser.add_argument("--uninstall", action="store_true", help="Unregister toolkit from Antigravity")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running unit tests during setup")

    args = parser.parse_args()

    if args.status:
        check_status()
        return

    if args.uninstall:
        uninstall()
        return

    print("=== Setting Up Antigravity Toolkit ===")
    install()
    update_readme_roster(REPO_ROOT)

    if not args.skip_tests:
        success = run_tests()
        if not success:
            print("\n[WARN] Some tests failed. Please review errors above.", file=sys.stderr)
            sys.exit(1)
        print("\n[PASS] All toolkit test suites passed cleanly!")

    print("\n[READY] Antigravity is now connected to your toolkit!")


if __name__ == "__main__":
    main()
