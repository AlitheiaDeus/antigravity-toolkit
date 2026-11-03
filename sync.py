#!/usr/bin/env python3
"""
sync.py - Antigravity Toolkit Local Deploy & Sync Tool

Syncs skills between this Git repository and Antigravity's live config directory
(~/.gemini/config/skills/).

Commands:
  python sync.py --deploy    Deploy all skills from repo to Antigravity live config.
  python sync.py --save      Save live changes from Antigravity back into repo.
  python sync.py --status    Check status and differences between live and repo.
"""

import argparse
import filecmp
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
REPO_SKILLS = REPO_ROOT / "skills"
LIVE_SKILLS = Path.home() / ".gemini" / "config" / "skills"


def deploy():
    print(f"=== Deploying Skills to Antigravity Live Config ===")
    print(f"Source: {REPO_SKILLS}")
    print(f"Target: {LIVE_SKILLS}")

    LIVE_SKILLS.mkdir(parents=True, exist_ok=True)
    count = 0
    for skill_dir in REPO_SKILLS.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            target_dir = LIVE_SKILLS / skill_dir.name
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(skill_dir, target_dir)
            print(f"  [DEPLOYED] {skill_dir.name}")
            count += 1

    print(f"\n[OK] Deployed {count} skills. They are now live in your Antigravity / menu!")


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
    print(f"=== Antigravity Toolkit Sync Status ===")
    print(f"Repo: {REPO_SKILLS}")
    print(f"Live: {LIVE_SKILLS}")

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
        print(f"  * {name:<25} | In Repo: {in_repo:<8} | Live in Menu: {in_live}")


def main():
    parser = argparse.ArgumentParser(description="Antigravity Toolkit Sync")
    parser.add_argument("--deploy", action="store_true", help="Deploy repo skills to live Antigravity")
    parser.add_argument("--save", action="store_true", help="Save live Antigravity skills into repo")
    parser.add_argument("--status", action="store_true", help="Show sync status")

    args = parser.parse_args()

    if args.deploy:
        deploy()
    elif args.save:
        save()
    elif args.status or len(sys.argv) == 1:
        status()


if __name__ == "__main__":
    main()
