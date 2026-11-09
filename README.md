# Antigravity Agent Toolkit

A curated, version-controlled repository of custom skills, deterministic CLI helper scripts, and guardrails for Google Antigravity agents.

---

## 📦 Active Skill Roster

All skills are designed with **zero external runtime dependencies** (pure Python 3.8+ standard library) and are tested via automated unit suites:

| Skill | Primary CLI Script | Core Operational Superpower |
| :--- | :--- | :--- |
| **`system-mapper`** | `scripts/system_mapper_ctl.py` | Executive Architecture Cartographer: maps files & processes to plain-English roles, renders colorized C4 Mermaid flowcharts & system ledgers. |
| **`kanban-workflow-guard`** | `scripts/kanban_ctl.py` | 6-Tier Kanban pipeline, WIP=1 guard, anti-burnout `shelve`, `roadmap/` auto-detection, and project scaffolding (`init`). |
| **`code-landmarks`** | `scripts/scan_landmarks.py` | Fast AST & bookmark symbol indexer for monolithic codebases (>300 lines), line bounds scanner, and padded code slicer. |
| **`doc-hygiene`** | `scripts/doc_ctl.py` | In-place tree updater (ASCII & Mermaid `treeView-beta`), relative markdown link auditor (`links`), and pre-flight edit string verifier (`verify`). |
| **`git-workflow-guard`** | `scripts/git_sanitize_check.py` | Pre-commit privacy shield: machine path leak detector (`C:\Users\...`), credential blocker, and `.gitignore` auto-fixer. |
| **`scratch-curator`** | `scripts/scratch_ctl.py` | Workspace hygiene: audits ad-hoc scripts, catalogs with headers into `scripts/scratch/` phonebook, and purges ephemeral trash. |
| **`skill-curator`** | `scripts/skill_ctl.py` | In-workspace skill artisan: scaffolds, audits, and promotes bespoke project skills (`<workspace>/.agents/skills/`). |
| **`de-slop`** | `scripts/deslop_ctl.py` | Codebase grounding & de-slopping: detects and removes AI enterprise fluff, conversational debris, and hollow abstractions. |
| **`agents-md-curator`** | `SKILL.md` | Architectural landmark curation and anti-bloat invariants for `AGENTS.md` (< 250 lines). |

---

## 🚀 Quick Start (1-Click Setup & Verification)

To connect and verify this repository on any machine:

```bash
# On Windows, invoke with the proper Python binary:
C:\msys64\mingw64\bin\python.exe setup_toolkit.py
```

This will:
1. Register the portable path (`~/<path-to-repo>/skills`) in `~/.gemini/config/skills.json`.
2. Discover and execute all unit test suites across all skills to verify the local environment (**30 / 30 tests passing**).

---

## 🔄 Live Deployment Workflow (`sync.py`)

Because Antigravity's desktop UI slash command (`/`) menu reads physical folders from `~/.gemini/config/skills/`, use `sync.py` to maintain two-way synchronization:

```bash
# Deploy changes from this repo to live Antigravity config
python sync.py --deploy

# Pull external tweaks from live config back into this repo
python sync.py --save
```

---

## 🛠️ Developing & Maintaining Skills

Refer to [`AGENTS.md`](AGENTS.md) for non-negotiable architectural invariants:
1. **Develop**: Build under `skills/<name>/` (`SKILL.md`, `scripts/`, `tests/`).
2. **Verify**: Run `python setup_toolkit.py` to ensure all tests pass.
3. **Deploy**: Run `python sync.py --deploy` to update live Antigravity.
4. **Sanitize**: Run `python skills/git-workflow-guard/scripts/git_sanitize_check.py`.
5. **Commit**: Atomic Git commit on `main`.
