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
└── tasks/              # Optional 1-card-1-doc Markdown specs (<ID>.md)
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
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" locate . TKT-01
python "$HOME/.gemini/config/skills/roadmap-studio/scripts/roadmap_studio_ctl.py" cat . TKT-01
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
