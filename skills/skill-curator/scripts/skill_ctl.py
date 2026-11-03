#!/usr/bin/env python3
"""
skill_ctl.py - Project-Specific Skill Artisan & In-Workspace Curator

Manages the lifecycle of project-specific skills inside <workspace>/.agents/skills/:
  1. list: Discovers and inspects all in-project skills.
  2. create: Scaffolds compliant skills following the official Antigravity anatomy.
  3. audit: Validates frontmatter, anatomy, test coverage, and privacy path hygiene.
  4. promote: Promotes proven project skills to the global toolkit.

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any

SKILL_TEMPLATE = """---
name: {name}
description: >-
  {description}
---

# `{name}` - Project-Specific Runbook

{description}

---

## 1. When to Use

Use this skill when:
* [Specific condition or task 1]
* [Specific condition or task 2]

---

## 2. Procedures & Workflow

1. Step one instructions
2. Step two instructions

---

## 3. Verification & Acceptance Invariants

* [ ] Condition 1 holds
* [ ] Tests pass
"""

PATH_LEAK_RE = re.compile(r'(?:[a-zA-Z]:[\\/][uU]sers[\\/]|/(?:home|Users)/)[a-zA-Z0-9_\-\.]+[\\/]')


def get_workspace_root(start_path: Path) -> Path:
    """Finds workspace root via git or looks for .agents directory."""
    curr = start_path.resolve()
    try:
        res = subprocess.run(
            ["git", "-C", str(curr), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        )
        return Path(res.stdout.strip())
    except Exception:
        pass

    # Walk up looking for .agents or .git
    for p in [curr] + list(curr.parents):
        if (p / ".agents").exists() or (p / ".git").exists():
            return p
    return curr


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """Extracts frontmatter YAML key-values and remaining markdown."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    yaml_block = parts[1]
    body = parts[2]
    data = {}

    name_m = re.search(r'^name\s*:\s*(.+)$', yaml_block, re.MULTILINE)
    if name_m:
        data["name"] = name_m.group(1).strip().strip("'\"")

    desc_m = re.search(r'^description\s*:\s*(?:>-\s*|\s*)(.+?)(?=\n[a-zA-Z0-9_\-]+:|\Z)', yaml_block, re.DOTALL | re.MULTILINE)
    if desc_m:
        data["description"] = " ".join(desc_m.group(1).split())

    return data, body


class SkillCurator:
    def __init__(self, workspace_root: Path):
        self.root = workspace_root
        self.skills_dir = self.root / ".agents" / "skills"

    def list_skills(self) -> List[Dict[str, Any]]:
        if not self.skills_dir.exists():
            return []

        skills = []
        for p in sorted(self.skills_dir.iterdir()):
            if p.is_dir() and (p / "SKILL.md").exists():
                content = (p / "SKILL.md").read_text(encoding="utf-8", errors="replace")
                fm, _ = parse_frontmatter(content)
                has_scripts = (p / "scripts").exists() and any((p / "scripts").iterdir())
                has_tests = (p / "tests").exists() and any((p / "tests").iterdir())
                skills.append({
                    "dir_name": p.name,
                    "name": fm.get("name", p.name),
                    "description": fm.get("description", "No description provided"),
                    "has_scripts": has_scripts,
                    "has_tests": has_tests,
                    "path": p
                })
        return skills

    def create_skill(self, name: str, description: Optional[str] = None, with_script: bool = True) -> Path:
        clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '-', name.lower().strip())
        skill_dir = self.skills_dir / clean_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        desc = description or f"Specialized project runbook for {clean_name}. Use when executing this project-specific procedure."
        skill_md = skill_dir / "SKILL.md"

        if not skill_md.exists():
            skill_md.write_text(
                SKILL_TEMPLATE.format(name=clean_name, description=desc),
                encoding="utf-8"
            )

        if with_script:
            scripts_dir = skill_dir / "scripts"
            tests_dir = skill_dir / "tests"
            scripts_dir.mkdir(exist_ok=True)
            tests_dir.mkdir(exist_ok=True)

            sample_script = scripts_dir / f"{clean_name.replace('-', '_')}_tool.py"
            if not sample_script.exists():
                sample_script.write_text(
                    f'#!/usr/bin/env python3\n"""Helper script for {clean_name}."""\n\ndef main():\n    print("Running {clean_name} helper...")\n\nif __name__ == "__main__":\n    main()\n',
                    encoding="utf-8"
                )

        return skill_dir

    def audit_skill(self, skill_dir: Path) -> List[str]:
        issues = []
        skill_md = skill_dir / "SKILL.md"

        if not skill_md.exists():
            return [f"Missing required SKILL.md in {skill_dir.name}"]

        content = skill_md.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(content)

        # 1. Frontmatter validation
        if "name" not in fm or not fm["name"]:
            issues.append(f"{skill_dir.name}: SKILL.md missing 'name' in frontmatter.")
        elif fm["name"] != skill_dir.name:
            issues.append(f"{skill_dir.name}: Frontmatter name '{fm['name']}' does not match directory '{skill_dir.name}'.")

        if "description" not in fm or len(fm["description"]) < 20:
            issues.append(f"{skill_dir.name}: Description is too short (< 20 chars). Semantic router needs clear usage triggers.")

        # 2. Privacy & Path Leak check
        for p in skill_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".md", ".py", ".sh", ".json", ".yaml", ".yml"}:
                text = p.read_text(encoding="utf-8", errors="replace")
                if PATH_LEAK_RE.search(text):
                    issues.append(f"{skill_dir.name}/{p.name}: Leaked hardcoded user profile path detected!")

        # 3. Anatomy check
        scripts_dir = skill_dir / "scripts"
        tests_dir = skill_dir / "tests"
        if scripts_dir.exists() and any(scripts_dir.iterdir()):
            if not tests_dir.exists() or not any(tests_dir.iterdir()):
                issues.append(f"{skill_dir.name}: Contains scripts/ but missing verification tests in tests/.")

        return issues

    def promote_skill(self, name: str, global_toolkit_skills: Path) -> Tuple[bool, str]:
        skill_dir = self.skills_dir / name
        if not skill_dir.exists():
            return False, f"Project skill '{name}' not found in {self.skills_dir}."

        issues = self.audit_skill(skill_dir)
        if issues:
            return False, f"Cannot promote '{name}' due to audit failures:\n" + "\n".join(f"  - {i}" for i in issues)

        target = global_toolkit_skills / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(skill_dir, target)
        return True, f"Successfully promoted '{name}' to {target}."


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Project-Specific Skill Artisan & Curator")
    parser.add_argument("--root", default=".", help="Workspace root directory (default: auto-detected)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. list
    subparsers.add_parser("list", help="List all project-specific skills in workspace")

    # 2. create
    p_create = subparsers.add_parser("create", help="Scaffold a new project skill")
    p_create.add_argument("name", help="Skill identifier (e.g. build-runner, deploy-helper)")
    p_create.add_argument("--description", help="Descriptive trigger for when to use this skill")
    p_create.add_argument("--no-script", action="store_true", help="Skip scaffolding scripts/ and tests/ folders")

    # 3. audit
    p_audit = subparsers.add_parser("audit", help="Audit project skills against official standards")
    p_audit.add_argument("name", nargs="?", help="Specific skill to audit (audits all if omitted)")

    # 4. promote
    p_promote = subparsers.add_parser("promote", help="Promote a project skill to global toolkit")
    p_promote.add_argument("name", help="Skill to promote")
    p_promote.add_argument("--target", default="C:/Users/AlitheiaDeus/DeusLocker/AI/antigravity-toolkit/skills", help="Global skills target directory")

    args = parser.parse_args()
    ws_root = get_workspace_root(Path(args.root))
    curator = SkillCurator(ws_root)

    if args.command == "list":
        skills = curator.list_skills()
        print(f"=== Project Skills: {ws_root.name} (.agents/skills/) ===")
        if not skills:
            print("  (No project-specific skills found. Run 'skill_ctl.py create <name>' to start!)")
            return
        for s in skills:
            scripts_badge = "[Scripts: Yes]" if s["has_scripts"] else "[No Scripts]"
            tests_badge = "[Tests: Yes]" if s["has_tests"] else "[No Tests]"
            print(f"\n📦 {s['name']} {scripts_badge} {tests_badge}")
            print(f"   {s['description']}")

    elif args.command == "create":
        target = curator.create_skill(args.name, description=args.description, with_script=not args.no_script)
        print(f"[OK] Created project skill '{args.name}' in {target.relative_to(ws_root)}")

    elif args.command == "audit":
        if args.name:
            target_dir = curator.skills_dir / args.name
            if not target_dir.exists():
                print(f"[FAIL] Skill '{args.name}' not found.", file=sys.stderr)
                sys.exit(1)
            targets = [target_dir]
        else:
            targets = [p for p in curator.skills_dir.iterdir() if p.is_dir()] if curator.skills_dir.exists() else []

        print(f"=== Auditing {len(targets)} Project Skill(s) in {ws_root.name} ===")
        all_clean = True
        for t in targets:
            issues = curator.audit_skill(t)
            if issues:
                all_clean = False
                print(f"\n[FAIL] {t.name}:", file=sys.stderr)
                for iss in issues:
                    print(f"  - {iss}", file=sys.stderr)
            else:
                print(f"[PASS] {t.name}: 100% compliant with Antigravity anatomy & privacy standards.")

        if not all_clean:
            sys.exit(1)

    elif args.command == "promote":
        global_target = Path(args.target).resolve()
        success, msg = curator.promote_skill(args.name, global_target)
        if success:
            print(f"[OK] {msg}")
        else:
            print(f"[ERROR] {msg}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
