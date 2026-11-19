---
name: roadmap-studio
description: >-
  Interactive 3-tab Kanban, Wardley Value Chain, and Cynefin/Kano studio backed by a per-repo .roadmap/ workspace.
  Use when initializing or cloning a project's taskboard into .roadmap/, managing tickets via CLI,
  or launching the localhost drag-and-drop ChromaForge studio (open.ps1 / serve).
---

# `roadmap-studio` — Unified Kanban + Wardley + Cynefin Studio

`roadmap-studio` combines **Kanban board management**, **Wardley Value Chain mapping**, and **Cynefin/Kano triage** into one per-repo `.roadmap/` workspace and an interactive 3-tab ChromaForge web studio.

---

## 1. `.roadmap/` Workspace Layout

```text
<repo-root>/.roadmap/
├── .gitignore          # Ignores .server.json, snapshot.html, and tasks/archived/
├── board.json          # Deterministic JSON source of truth (columns, cards, Wardley/Cynefin/Kano)
├── archived.json       # Auto-created archive & milestone/shelved index
├── kanban.md           # Auto-rendered read-only Markdown summary (refreshed on every save)
├── open.ps1            # 1-click PowerShell launcher (auto-reuses active port; 15s heartbeat exit)
└── tasks/              # Optional 1-card-1-doc Markdown specs (<ID>.md or <GROUP>/<ID>.md for grouped tickets)
    └── archived/       # Archived specs, shelved/, and milestone_*.md bundles
```

- **Do not edit `.roadmap/kanban.md` manually** — it is overwritten automatically whenever `board.json` saves so GitHub and IDE previews stay readable.
- **Custom columns** are supported natively in `board.json["columns"]` (`id`, `label`, `wip_limit`, `collapsed`). `init` scaffolds the 6 standard columns (`reported`, `frozen`, `backlog`, `todo`, `in_progress`, `completed`).

---

## 2. Agent Rules (WIP & Board Discipline)

1. **Strict Single-WIP for Agents (`WIP = 1`)**:
   - `roadmap_studio_ctl.py move <root> <ID> in_progress` enforces `wip_limit: 1` by default.
   - Do **not** pass `--force` unless the user explicitly tells you to run multiple `in_progress` cards.
   - If the user has dragged multiple cards into `in_progress` in the UI, work on the **topmost** card in `in_progress` unless the user specifies another ID.
2. **No Silent Deletion**:
   - Never delete active cards; use `archive` when the user signs off on completed work.
3. **Never Guess Ticket IDs with `rg`**:
   - `.roadmap/tasks/archived/` is `.gitignore`d, so `rg` misses archived/shelved/consolidated IDs.
   - Always use `next-id` (or `add --prefix <PREFIX>`) to allocate free ticket numbers.
4. **Grouped Tickets & Partial Archives**:
   - Every ticket (both a group container like `PLN-01` and its children like `TKT-01`) has its own card entry in `board.json`.
   - Grouping is driven purely by folder structure (`tasks/<GROUP>/<ID>.md`, with container at `tasks/<GROUP>/<GROUP>.md`); use `add --group <GROUP>` to group a new ticket.
   - `move` and `archive` operate **individually per ticket** — archive completed children incrementally without closing the parent container.
5. **5-Level Priorities**:
   - Use `Very High`, `High`, `Medium` (default), `Low`, or `Very Low`.
6. **Self-Contained Specs (Fresh-Session / Low-Reasoning Ready)**:
   - When writing or scoping `tasks/<ID>.md` (or `tasks/<GROUP>/<ID>.md`), make it **execution-ready** for a fresh session or low-reasoning model: include exact target file paths, function/class names, key edge cases, and the exact verification/test command(s) to run.

---

## 3. Onboarding a Repository

**Script Path**:  
`$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py`  
*(Windows native environment: `C:\msys64\mingw64\bin\python.exe`)*

### Path A: Blank Init or Deterministic `kanban.md` Clone
```bash
# Blank .roadmap/ scaffold + open.ps1
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" init . --title "My Project"

# Non-destructive clone from existing kanban.md / roadmap/kanban.md + tasks/
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" import .
```

### Path B: Semantic Clone (Non-Standard Taskboards)
When a repository uses `TODO.md`, `ROADMAP.md`, issue checklists, or custom notes instead of `kanban.md`:
1. Inspect the existing task files in the repo.
2. Semantically map each item into JSON (`id`, `title`, `column`, `priority`, `cynefin`, `kano`, `wardley`, `visibility`, `dependencies`, optional `spec_markdown`).
3. Pipe the JSON array (or `{"title": "...", "anchor": "USER", "cards": [...]}`) to `import --stdin`:
```bash
cat imported_board.json | python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" import . --stdin
```

---

## 4. Daily CLI & Studio Launch

```bash
# Launch interactive localhost studio (auto-reuses active server; shuts down 15s after tab close)
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" serve . --open

# Headless card operations
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" list .
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" next-id . TKT
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" next-id . TKT --count 5 --json
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" locate . TKT-01
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" cat . TKT-01
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" add . --prefix TKT --title "Add feature" --column todo --priority "Very High" --group PLN-01 --with-spec
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" add . --id TKT-01 --title "Add feature" --column todo --with-spec
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" move . TKT-01 in_progress
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" archive . TKT-01 --milestone "v1.0"
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" shelve . PLN-02 --reason "Dropped in favor of simpler design"
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" consolidate . --milestone "v1.0" --ids TKT-01,FIX-02
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" sync-md .
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" validate .

# Optional read-only static HTML snapshot
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" export-static .
```

Users can also launch the studio directly from PowerShell or Explorer via `.\.roadmap\open.ps1`.
