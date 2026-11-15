#!/usr/bin/env python3
"""
sync.py - Antigravity Toolkit Local Deploy & Sync Tool

Syncs skills between this Git repository and Antigravity's live config directory
(~/.gemini/config/skills/).

Commands:
  python sync.py --deploy             Deploy enabled skills from repo to Antigravity live config.
  python sync.py --recall NAME [...]  Remove specific skill(s) from Antigravity live config.
  python sync.py --recall-disabled    Remove all skills disabled in sync.config.json from live config.
  python sync.py --save               Save live changes from Antigravity back into repo.
  python sync.py --status             Check status and differences between live and repo.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import List, Set

from setup_toolkit import update_readme_roster

REPO_ROOT = Path(__file__).resolve().parent
REPO_SKILLS = REPO_ROOT / "skills"
LIVE_SKILLS = Path.home() / ".gemini" / "config" / "skills"
SYNC_CONFIG = REPO_ROOT / "sync.config.json"


def load_disabled(config_path: Path = SYNC_CONFIG) -> Set[str]:
    """Return the set of disabled skill names from sync.config.json."""
    if not config_path.exists():
        return set()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] Could not parse {config_path.name}: {exc}", file=sys.stderr)
        return set()
    disabled = data.get("disabled", [])
    return {str(name).strip() for name in disabled if str(name).strip()}


def deploy():
    update_readme_roster(REPO_ROOT)
    disabled = load_disabled()
    print(f"=== Deploying Skills to Antigravity Live Config ===")
    print(f"Source: {REPO_SKILLS}")
    print(f"Target: {LIVE_SKILLS}")

    LIVE_SKILLS.mkdir(parents=True, exist_ok=True)
    deployed = 0
    skipped = 0
    for skill_dir in sorted(REPO_SKILLS.iterdir(), key=lambda p: p.name.lower()):
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            if skill_dir.name in disabled:
                print(f"  [SKIPPED]  {skill_dir.name} (disabled in sync.config.json)")
                skipped += 1
                continue
            target_dir = LIVE_SKILLS / skill_dir.name
            shutil.copytree(skill_dir, target_dir, dirs_exist_ok=True)
            print(f"  [DEPLOYED] {skill_dir.name}")
            deployed += 1

    print(f"\n[OK] Deployed {deployed} skills ({skipped} disabled/skipped). They are now live in your Antigravity / menu!")


def recall(names: List[str]):
    print(f"=== Recalling Skills from Antigravity Live Config ===")
    print(f"Target: {LIVE_SKILLS}")

    if not LIVE_SKILLS.exists():
        print("[WARN] Live skills directory does not exist.")
        return

    recalled = 0
    for raw_name in names:
        name = raw_name.strip()
        if not name:
            continue
        target_dir = LIVE_SKILLS / name
        if target_dir.exists() and target_dir.is_dir():
            shutil.rmtree(target_dir)
            print(f"  [RECALLED]  {name}")
            recalled += 1
        else:
            print(f"  [NOT FOUND] {name} (not in live config)")

    print(f"\n[OK] Recalled {recalled} skill(s) from live config. Repo files were untouched.")


def save():
    print(f"=== Saving Live Skills back into Git Repo ===")
    print(f"Source: {LIVE_SKILLS}")
    print(f"Target: {REPO_SKILLS}")

    if not LIVE_SKILLS.exists():
        print("[ERROR] Live skills directory does not exist.", file=sys.stderr)
        return

    REPO_SKILLS.mkdir(parents=True, exist_ok=True)
    count = 0
    for live_dir in LIVE_SKILLS.iterdir():
        if live_dir.is_dir() and (live_dir / "SKILL.md").exists():
            repo_dir = REPO_SKILLS / live_dir.name
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            shutil.copytree(live_dir, repo_dir)
            print(f"  [SAVED] {live_dir.name}")
            count += 1

    print(f"\n[OK] Synced {count} skills into repo. Run 'git status' and 'git commit' to save.")


def status():
    disabled = load_disabled()
    print(f"=== Antigravity Toolkit Sync Status ===")
    print(f"Repo:   {REPO_SKILLS}")
    print(f"Live:   {LIVE_SKILLS}")
    print(f"Config: {SYNC_CONFIG.name} ({len(disabled)} disabled)")

    if not LIVE_SKILLS.exists():
        print("\n[WARN] Live skills directory does not exist. Run 'python sync.py --deploy' to install.")
        return

    repo_names = {d.name for d in REPO_SKILLS.iterdir() if d.is_dir()} if REPO_SKILLS.exists() else set()
    live_names = {d.name for d in LIVE_SKILLS.iterdir() if d.is_dir()}

    print("\nSkills Overview:")
    all_names = sorted(repo_names | live_names)
    for name in all_names:
        in_repo = "Yes" if name in repo_names else "MISSING"
        in_live = "Yes" if name in live_names else "NOT DEPLOYED"
        flag = " [DISABLED]" if name in disabled else ""
        print(f"  * {name:<25} | In Repo: {in_repo:<8} | Live in Menu: {in_live}{flag}")


def main():
    parser = argparse.ArgumentParser(description="Antigravity Toolkit Sync")
    parser.add_argument("--deploy", action="store_true", help="Deploy enabled repo skills to live Antigravity")
    parser.add_argument("--recall", nargs="+", metavar="NAME", help="Remove specified skill(s) from live Antigravity")
    parser.add_argument("--recall-disabled", action="store_true", help="Remove all skills disabled in sync.config.json from live Antigravity")
    parser.add_argument("--save", action="store_true", help="Save live Antigravity skills into repo")
    parser.add_argument("--status", action="store_true", help="Show sync status")

    args = parser.parse_args()

    if args.deploy:
        deploy()
    elif args.recall:
        recall(args.recall)
    elif args.recall_disabled:
        disabled = sorted(load_disabled())
        if not disabled:
            print("[OK] No skills are currently disabled in sync.config.json.")
        else:
            recall(disabled)
    elif args.save:
        save()
    elif args.status or len(sys.argv) == 1:
        status()


if __name__ == "__main__":
    main()
