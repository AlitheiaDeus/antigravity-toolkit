---
name: system-mapper
description: >-
  Map, categorize, and report what every file and process does across a codebase in colorized C4-style Mermaid diagrams and plain-English system ledgers.
  Use when onboarding, exploring a complex or unfamiliar system, conducting architectural reviews, spotting layering violations and bottlenecks, or helping non-coders and leads understand the architecture to issue high-level fixes.
---

# `system-mapper` - Executive Architecture Cartographer & System Ledger

`system-mapper` scans a codebase of any size, extracts concise, plain-English roles for each file and process, groups them into logical architectural domains, and renders them as colorized, C4-style Mermaid flowcharts and structured system ledgers.

It is specifically designed so that **non-coders, technical product managers, domain experts, and engineering leads** can inspect the system at a glance, spot architectural smells (such as UI bypassing business logic directly into the database), and issue directive, high-level fixes without getting lost in implementation syntax.

---

## 1. When to Use

Reach for `system-mapper` whenever:
1. **System Orientation & Onboarding**: You or the user need a high-level breakdown of what each module does in an unfamiliar codebase.
2. **Explaining Architecture to Non-Coders**: The user wants an intuitive, color-coded visual map showing components, dataflows, and dependencies.
3. **Architectural Triage & Smells**: Spotting layer violations (e.g. entrypoints directly touching persistence), circular coupling, bottlenecks, or unmaintained legacy traps.
4. **Validating High-Level Fixes**: Allowing a product manager or lead to review the critical path before an agent implements major refactoring.

---

## 2. Global Tool Execution

**Script Path**:  
`$HOME/.gemini/config/skills/system-mapper/scripts/system_mapper_ctl.py`

*(Windows native environment: `C:\msys64\mingw64\bin\python.exe`)*

### CLI Quick Reference

```bash
# 1. Generate full executive report (Mermaid Diagram + Plain-English Ledger + Hotspots)
python "$HOME/.gemini/config/skills/system-mapper/scripts/system_mapper_ctl.py" report .

# 2. Output only the colorized Mermaid C4-style flowchart
python "$HOME/.gemini/config/skills/system-mapper/scripts/system_mapper_ctl.py" map .

# 3. Output the plain-English System Ledger table
python "$HOME/.gemini/config/skills/system-mapper/scripts/system_mapper_ctl.py" table .

# 4. Filter and focus on a specific subsystem (e.g. 'billing' or 'auth')
python "$HOME/.gemini/config/skills/system-mapper/scripts/system_mapper_ctl.py" map . --focus billing

# 5. Exclude non-essential directories from the architectural scan
python "$HOME/.gemini/config/skills/system-mapper/scripts/system_mapper_ctl.py" map . --exclude tests,docs,fixtures

# 6. Export structured JSON for subagent analysis or programmatic consumption
python "$HOME/.gemini/config/skills/system-mapper/scripts/system_mapper_ctl.py" scan . --json

# 7. Save report directly to an artifact or markdown file
python "$HOME/.gemini/config/skills/system-mapper/scripts/system_mapper_ctl.py" report . --output docs/ARCHITECTURE.md
```

---

## 3. The C4 Color Palette Standard

Every component in the Mermaid flowchart is color-coded using deterministic `classDef` definitions so anyone can instantly recognize responsibilities:

| Color | Badge | Architectural Role | What it Represents |
| :--- | :--- | :--- | :--- |
| **Blue** (`#1e40af`) | 🔵 | **Entrypoint / API / UI** | Where users or external traffic enter the system (routes, pages, CLI). |
| **Green** (`#166534`) | 🟢 | **Core Logic / Services** | Where business rules, calculations, and domain orchestrators execute. |
| **Amber** (`#854d0e`) | 🟡 | **Async / Queues / Workers** | Background jobs, delayed tasks, message consumers, cron schedulers. |
| **Purple** (`#581c87`) | 🟣 | **Storage / Database / State** | Persistent data stores, caches, ORM models, migration schemas. |
| **Dark Slate** (`#374151`)| ⚪ | **External Integration** | Third-party APIs, payment gateways (Stripe), SaaS clients, webhooks. |
| **Red** (`#991b1b`) | 🔴 | **Hotspot / Tech Debt** | Deprecated files, known bottlenecks, or high-risk areas. |
| **Gray** (`#475569`) | ⚙️ | **Config / Infrastructure** | Settings, environment manifests, Dockerfiles, build configurations. |

---

## 4. How to Present the Output to the User

When a user asks for an architectural map or system explanation:
1. **Run `report` or `map`** using `system_mapper_ctl.py`.
2. **Present the Colorized Mermaid Block**:
   ```mermaid
   flowchart TD
       classDef entrypoint fill:#1e40af,stroke:#3b82f6,stroke-width:2px,color:#ffffff;
       classDef core fill:#166534,stroke:#22c55e,stroke-width:2px,color:#ffffff;
       classDef storage fill:#581c87,stroke:#a855f7,stroke-width:2px,color:#ffffff;
       
       subgraph Ingestion["Domain: API"]
           Router["api/routes.py<br/><i>Dispatches HTTP requests</i>"]:::entrypoint
       end
       subgraph Core["Domain: Services"]
           Billing["services/billing.py<br/><i>Calculates invoices</i>"]:::core
       end
       subgraph State["Domain: Database"]
           DB[("db/models.py<br/><i>User & invoice records</i>")]:::storage
       end

       Router --> Billing
       Billing --> DB
   ```
3. **Include the Plain-English Ledger**:
   Map filenames to single-sentence plain-English responsibilities and downstream dependencies.
4. **Highlight Non-Coder Action Items**:
   Frame issues in clear cause-and-effect terms:
   * *"Notice how `routes.py` connects directly to `db/models.py`? That bypasses the discount calculation in `billing.py`."*
   * *"To fix this, we should route requests through `billing.py` before touching the database."*

---

## 5. Verification & Testing

All tools in this skill must adhere to the zero external dependencies policy and pass the master test suite:

```bash
python setup_toolkit.py
```
