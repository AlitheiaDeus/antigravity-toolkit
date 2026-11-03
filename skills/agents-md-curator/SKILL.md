---
name: agents-md-curator
description: >-
  Audit, curate, and maintain AGENTS.md and GEMINI.md project landmark files.
  Use when creating, refreshing, trimming, or reorganizing project landmark files,
  preventing documentation bloat, enforcing strict separation of concerns (keeping
  plans, kanbans, and todos in their dedicated files), and eliminating volatile,
  machine-specific paths.
---

# `agents-md-curator` - Project Landmark & Architecture Curator

`AGENTS.md` (and `GEMINI.md`) serves as the primary **architectural landmark and anchor point** for incoming AI coding agents and human engineers. It ensures agents do not waste tokens and turns scavenge-searching the codebase at the start of a session.

However, agents frequently fall into an anti-pattern: **documentation hoarding**—dumping full task backlogs, granular roadmaps, bug logs, and machine-specific local paths into `AGENTS.md`, causing it to rot, drift, and bloat.

This skill defines the strict architectural standards and curation workflow required to keep project landmark documents concise, durable, and reliable.

---

## 1. The Separation of Concerns Hierarchy

Every piece of project knowledge has a designated home. **Never cross-contaminate.**

| Document Type | Designated Home | Should it be in `AGENTS.md`? |
| :--- | :--- | :--- |
| **System Mission & Principles** | `AGENTS.md` (Section 1) | **YES** (1-2 punchy paragraphs) |
| **Portable Run Directives** | `AGENTS.md` (Section 2) | **YES** (Generic environment, portable CLI) |
| **Repository Topology** | `AGENTS.md` (Section 3) | **YES** (Core packages and directory contracts) |
| **Architectural Invariants** | `AGENTS.md` (Section 4) | **YES** (Contracts, threading, state rules) |
| **Contribution Recipes** | `AGENTS.md` (Section 5 & 6) | **YES** (Step-by-step modular recipes) |
| **Active Task Board / WIP** | `kanban.md` | **STRICTLY FORBIDDEN** (Link only) |
| **Bug History & Root Causes**| `kanban.md` (Spec table) | **STRICTLY FORBIDDEN** (Link only) |
| **Granular Roadmaps / Plans**| `docs/roadmaps/` or `plans/` | **STRICTLY FORBIDDEN** (Link only) |
| **Transient Prototype Lists**| `Snippets To Integrate/` | **STRICTLY FORBIDDEN** (Mention folder only) |
| **Local Machine Paths** | Local terminal / `.env` | **STRICTLY FORBIDDEN** (Violates portability) |

---

## 2. Invariants for `AGENTS.md`

When writing, reviewing, or editing `AGENTS.md`, enforce the following **Iron Invariants**:

### Invariant 1: Maximum Length & Focus
- Keep the document between **150 and 250 lines** (hard ceiling of 300 lines).
- If `AGENTS.md` exceeds 300 lines, identify which sections are task lists, scratch plans, or verbatim code copies, and relocate them to their proper files.

### Invariant 2: Zero Volatility (No Machine-Specific Paths)
- **Never** include absolute paths containing usernames or local home directories (e.g., `C:\Users\<user>\...` or `/home/<user>/...`).
- Always use workspace-relative paths or generic environment variables (e.g., `<conda_env_path>/python`).
- Use standard, portable CLI commands that work across shells:
  ```bash
  conda activate <env_name>
  python path/to/main.py
  python -m unittest discover tests
  ```

### Invariant 3: Zero Ephemeral Status Tags
- **Never** annotate directories or components in `AGENTS.md` with volatile status tags like `[Active]`, `[WIP]`, `[Done]`, or `[Sprint 3]`.
- If the project uses a configuration curtain (e.g. `plugins_config.json`) or dynamic registry, explicitly point to that config file as the runtime single source of truth.

### Invariant 4: Preserve Critical Architectural Contracts
- An anchor document must clearly define the invariants that agents **must not break** (e.g., state immutability, thread safety, rendering fallbacks, color palette tokens).
- Code examples in `AGENTS.md` must be abstract contracts and interfaces, not 200-line concrete implementations.

---

## 3. Step-by-Step Curation Workflow

Follow this procedure whenever auditing, refreshing, or creating `AGENTS.md`:

### Step 1: Audit for Bloat & Violations
Run an inspection check over `AGENTS.md` looking for:
1. **Absolute paths**: Search for `C:\Users\`, `/home/`, or machine-specific disk labels.
2. **Task lists & todos**: Search for `- [ ]`, `TODO`, `WIP`, or bug tracking notes.
3. **Status annotations**: Search for `[Active]`, `[WIP]`, or `[Deprecated]` in directory trees.
4. **Transient filenames**: Check if individual scratch files or temporary prototypes are enumerated.

### Step 2: Extract & Relocate
- **If task lists or bugs are found**: Move them into `kanban.md` following standard Kanban conventions.
- **If long algorithmic roadmaps are found**: Move them into a dedicated planning document (e.g., `docs/roadmaps/` or `plans/`) and add a one-line markdown link in `AGENTS.md`.
- **If temporary prototype scripts are listed**: Summarize the parent staging directory (e.g. `Snippets To Integrate/ - Staging area for reference scripts`) and remove transient individual file listings.

### Step 3: Standardize Portable Execution Directives
Ensure Section 2 specifies:
- The target environment name (e.g., `pylearn`).
- The shell activation command (`conda activate <env>` or `source <env>/bin/activate`).
- Portable execution commands for application launch and automated test suites.
- Explicit note on headless requirements (e.g. `QT_QPA_PLATFORM=offscreen` if using Qt).

### Step 4: Verify Topology & Invariants
Ensure the repository tree in Section 3 reflects the **architectural package contracts** (e.g. showing `state.py`, `solver.py`, `canvas.py`, `plugin.py` for a plugin architecture) rather than an exhaustive list of every transient file.

### Step 5: Verification Check
Before concluding, verify:
- [ ] Line count is within ~150–250 lines.
- [ ] No personal machine paths exist.
- [ ] All file links use valid relative paths or standard markdown format.
- [ ] Automated tests and application launch commands are portable and tested.
