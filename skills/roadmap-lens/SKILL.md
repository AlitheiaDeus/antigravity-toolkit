---
name: roadmap-lens
description: >-
  Read-only strategic evolution (Wardley Map) and triage psychology (Cynefin domain + Kano developer motivation) visualizer for kanban.md and tasks/.
  Use when prioritizing a backlog, mapping dependency chains and evolution vectors, classifying tickets into Cynefin quadrants and Kano categories,
  or generating an interactive ChromaForge HTML HUD with 1-click Agent Directives.
---

# `roadmap-lens` — Wardley & Cynefin/Kano Strategic HUD

`roadmap-lens` is a **strictly read-only** strategic and triage visualizer for `kanban.md` and `tasks/`. It complements `system-mapper` (C4 architecture) and `code-starmap` (call-graph topology) by mapping **how components evolve** (Wardley Map) and **how tickets should be approached** (Cynefin domain + Kano developer motivation).

> **Boundary Invariant**: `roadmap-lens` NEVER mutates `kanban.md`, `tasks/`, or source code. All board state mutations belong exclusively to `kanban-workflow-guard`.

---

## 1. When to Use

Invoke `roadmap-lens` whenever:
1. **Backlog Triage & Prioritization**: Deciding which tickets are `Execute Now` (Clear/Chaotic), `Spike First` (Complex), or `Hold` (Frozen/Low-leverage).
2. **Strategic Value-Chain Mapping**: Visualizing how tickets sit from User-Facing (`V5`) down to Infrastructure (`V1`) across `Genesis → Custom → Product → Commodity`.
3. **Dependency & Leverage Analysis**: Identifying upstream blockers and downstream dependents before promoting a ticket.
4. **Interactive Visual Review**: Opening `roadmap_lens.html` to filter by Kano value (`must-be`, `performance`, `delighter`), board state, and copy tailored `[Copy Agent Directive]` prompts.

---

## 2. Primary Agent Workflow (Universal JSON-First Pipeline)

`roadmap-lens` works on **any** repository (even without `kanban.md`) via a 4-step JSON-first pipeline:

1. **Inspect Repo**: Survey `kanban.md`, `tasks/`, `TODO`s, issues, or architecture modules.
2. **Synthesize JSON**: Construct a JSON array (or `{"cards": [...]}`) of items with `id`/`ticket`, `title`, `column`/`status`, `cynefin`, `kano`, `wardley`, `visibility` (`1..5`), `dependencies`, `recommended_action`, and `agent_directive`.
3. **Pipe to `render --stdin`**: `roadmap_lens_ctl.py` normalizes fields, computes reverse `dependents` and `structural_leverage`, and injects the payload into `resources/template.html`.
4. **Write `.agents/roadmap_lens.html`**: Default `--output` is `.agents/roadmap_lens.html` (kept out of project roots). Browser launch is strictly opt-in via `--open`.

**Script Path**:  
`$HOME/.gemini/config/skills/roadmap-lens/scripts/roadmap_lens_ctl.py`  
*(Windows native environment: `C:\msys64\mingw64\bin\python.exe`)*

### CLI Quick Reference

```bash
# Primary: Pipe synthesized roadmap JSON into the ChromaForge HUD (.agents/roadmap_lens.html)
cat roadmap.json | python "$HOME/.gemini/config/skills/roadmap-lens/scripts/roadmap_lens_ctl.py" render --stdin

# Or render from a JSON file (and optionally open in browser with --open)
python "$HOME/.gemini/config/skills/roadmap-lens/scripts/roadmap_lens_ctl.py" render --data roadmap.json --output .agents/roadmap_lens.html --open

# Kanban-backed repos: Scout board & tasks (auto-detects roadmap/kanban.md or root kanban.md)
python "$HOME/.gemini/config/skills/roadmap-lens/scripts/roadmap_lens_ctl.py" scout .
python "$HOME/.gemini/config/skills/roadmap-lens/scripts/roadmap_lens_ctl.py" scout . --json

# Output compact Markdown triage matrix for inline chat review
python "$HOME/.gemini/config/skills/roadmap-lens/scripts/roadmap_lens_ctl.py" matrix .

# Direct HTML generation from kanban.md/tasks/ (writes .agents/roadmap_lens.html)
python "$HOME/.gemini/config/skills/roadmap-lens/scripts/roadmap_lens_ctl.py" html .
```

---

## 3. Optional Ticket Metadata Tags

`roadmap_lens_ctl.py` automatically classifies tickets using prefix and keyword heuristics (`PLN-`, `TKT-`, `BUG-`, `TLK-`), and honors explicit metadata tags inside `tasks/*.md` or `tasks/backlog/*.md` when present:

```markdown
- cynefin: clear | complicated | complex | chaotic
- kano: must-be | performance | delighter
- wardley: genesis | custom | product | commodity
- visibility: 1..5
```

Dependencies are extracted from `Dependencies:`, `Depends on:`, `Blocked by:`, or `Upstream:` lines referencing ticket IDs (e.g. `TKT-12`, `PLN-04`). Files under `tasks/archived/` are ignored.

---

## 4. Interactive HTML HUD (`roadmap_lens.html`)

- **Tab 1 — Wardley Value Chain**: Plots tickets across `Genesis`, `Custom Built`, `Product`, and `Commodity` (X-axis) and `V5 User-Facing` to `V1 Infrastructure` (Y-axis). Clicking any node highlights upstream/downstream dependency wires; toggling **Evolution Vectors** shows rightward shifts on `Todo` / `In Progress` cards.
- **Tab 2 — Cynefin & Kano Triage Board**: 4-quadrant grid (`Complex`, `Complicated`, `Chaotic`, `Clear`) with Kano-colored cards (`Must-Be`, `Performance`, `Delighter`) and clickable filter pills for Kano, State, and Recommended Action.
- **Side Detail Drawer**: Includes `[Copy Agent Directive]` for 1-click handoff back into Antigravity chat.
