# Antigravity Agent Toolkit

A curated, version-controlled repository of custom skills, deterministic CLI helper scripts, and guardrails for Google Antigravity agents.

---

## 📦 Active Skill Roster

All skills are designed with **zero external runtime dependencies** (pure Python 3.8+ standard library) and are tested via automated unit suites:

<!-- ROSTER:START -->
| Skill | Primary CLI Script | Core Operational Superpower |
| :--- | :--- | :--- |
| **`agents-md-curator`** | `SKILL.md` | Audit, curate, and maintain AGENTS.md and GEMINI.md project landmark files. Use when creating, refreshing, trimming, or reorganizing project landmark files, preventing documentation bloat, enforcing strict separation of concerns (keeping plans, kanbans, and todos in their dedicated files), and eliminating volatile, machine-specific paths. |
| **`code-landmarks`** | `scripts/scan_landmarks.py` | Fast structural symbol and landmark indexer for navigating large or monolithic codebases and documents. Use when locating classes, methods, functions, or [LANDMARK: ...] bookmarks in files (>300 lines), or when finding exact line ranges before calling read_file, edit_file, refactoring, or debugging. |
| **`code-starmap`** | `scripts/code_starmap_ctl.py` | Map the call-graph topology and functional nervous system of a codebase into an interactive Cyberpunk HTML Starfield or Gephi GEXF graph. Use when exploring unfamiliar functional codebases, untangling messy function/method/class call chains, isolating blast radius with Short-Range EMP, hunting dead stars (uncalled functions), identifying black-hole dispatchers, or copying direct pipe links into chat for pairing. |
| **`code-tour`** | `SKILL.md` | Manual trigger only: turn-gated, one-block-at-a-time codebase walkthrough. Use ONLY when the user explicitly invokes `code-tour`, `@code-tour`, or asks for a "code tour" or "walk me through <file/feature> step by step". Do NOT trigger for general code explanations, debugging, architecture summaries, or editing tasks. |
| **`de-slop`** | `scripts/deslop_ctl.py` | Audit, ground, and de-slop codebases across code, test suites, documentation prose, and filenames. Detects AI enterprise foam, conversational chat debris, defensive panic wrappers, hollow abstractions, test suite paper tigers (mock theatre, hollow assertions), and hyper-verbose filenames, while strictly protecting battle-tested StackOverflow copypasta and platform hacks. |
| **`doc-hygiene`** | `scripts/doc_ctl.py` | Maintain project documentation integrity, scan and update in-place directory trees between markers (ASCII or Mermaid treeView-beta), verify relative markdown links, and validate edit targets before modifying files. Use when generating or updating repository structure trees in README.md or AGENTS.md, checking for broken doc links, or verifying unique string matches before editing. |
| **`git-workflow-guard`** | `scripts/git_sanitize_check.py` | Enforce pragmatic Git commit hygiene, atomic feature commits, remote publication safety, privacy sanitization, and .gitignore guardrails. Use when staging, committing, pushing, or reviewing version control changes. Prevents micro-commit clutter, hardcoded personal path leaks, unwanted destructive git rewinds, and repository pollution with local documentation and scratch files. |
| **`kanban-workflow-guard`** | `scripts/kanban_ctl.py` | Enforce strict Kanban workflow discipline, modular 1-card-1-doc task lifecycle tracking, and board integrity. Manages the Modular Task Architecture (kanban.md, tasks/, tasks/backlog/, tasks/archived/, kanban_archive.md), prevents silent clearing of tickets, enforces single-WIP focus, and validates ticket prefix taxonomy. |
| **`roadmap-lens`** | `scripts/roadmap_lens_ctl.py` | Read-only strategic evolution (Wardley Map) and triage psychology (Cynefin domain + Kano developer motivation) visualizer for kanban.md and tasks/. Use when prioritizing a backlog, mapping dependency chains and evolution vectors, classifying tickets into Cynefin quadrants and Kano categories, or generating an interactive ChromaForge HTML HUD with 1-click Agent Directives. |
| **`roadmap-studio`** | `scripts/roadmap_studio_ctl.py` | Interactive 3-tab Kanban, Wardley Value Chain, and Cynefin/Kano studio backed by a per-repo .roadmap/ workspace. Use when initializing or cloning a project's taskboard into .roadmap/, managing tickets via CLI, or launching the localhost drag-and-drop ChromaForge studio (open.ps1 / serve). |
| **`scratch-curator`** | `scripts/scratch_ctl.py` | Tidy up, catalog, and index ad-hoc scripts, debug testbeds, and transient scratch files generated during agent debugging sessions. Use when finding loose debug scripts (debug_*.py, probe_*.py, tmp_*), organizing repeatable testbeds into scripts/scratch/ with a phonebook catalog, or purging ephemeral dumps and temp files. |
| **`skill-curator`** | `scripts/skill_ctl.py` | Audit, scaffold, and curate project-specific skills in <workspace-root>/.agents/skills/. Use when creating new in-project skills, validating frontmatter triggers and anatomy, checking for leaked machine paths, or promoting proven project skills to the global toolkit. |
| **`system-mapper`** | `scripts/system_mapper_ctl.py` | Map, categorize, and report what every file and process does across a codebase in colorized C4-style Mermaid diagrams, intent-aware architectural telemetry, and plain-English system ledgers. Use when onboarding, exploring a complex or unfamiliar system, conducting architectural reviews, spotting monolithic God-files, unpacking embedded subsystems, exposing in-memory boundary tightropes, or helping non-coders and leads understand the architecture to issue high-level fixes. |
<!-- ROSTER:END -->

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
# Deploy enabled skills from this repo to live Antigravity config (skips skills in sync.config.json "disabled")
python sync.py --deploy

# Manually remove specific skill(s) or all disabled skills from live config (never touches repo files)
python sync.py --recall <skill-name>
python sync.py --recall-disabled

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
