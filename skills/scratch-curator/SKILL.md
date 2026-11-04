---
name: scratch-curator
description: Tidy up, catalog, and index ad-hoc scripts, debug testbeds, and transient scratch files generated during agent debugging sessions. Use when finding loose debug scripts (debug_*.py, probe_*.py, tmp_*), organizing repeatable testbeds into scripts/scratch/ with a phonebook catalog, or purging ephemeral dumps and temp files.
---

# Scratch Curator (`scratch_ctl.py`)

Deterministic workspace hygiene and scratch script curator for agentic pair-programming sessions.

When debugging complex systems, agents and developers frequently write isolated scratch scripts (`debug_rf.py`, `probe_serial.ps1`, `temp_dump.json`) in the project workspace. Over time, these become orphaned fossils—no docstring, no ticket reference, no phonebook entry.

`scratch-curator` audits the workspace, purges throwaway trash, and catalogs reusable testbeds into an indexed scratch repository with standardized metadata.

---

## 🛠️ Key CLI Capabilities

All commands are run using Python 3.8+ standard library:

### 1. Scan & Audit Workspace
Scans the workspace for untracked scratch items, categorizing into **Ephemeral Trash** vs. **Debug Scripts**:
```bash
python path/to/scratch_ctl.py scan
python path/to/scratch_ctl.py scan --root /path/to/project
```

### 2. Catalog a Debug Script (The "Phonebook" Pipeline)
Moves an ad-hoc script into `scripts/scratch/`, injects a standardized metadata header, and registers it in `SCRATCH_PHONEBOOK.md`:
```bash
python path/to/scratch_ctl.py catalog debug_atc_disconnect.py \
  --ticket BUG-02 \
  --purpose "Isolated verification for async RF link timeout during ATC landing."
```

### 3. Purge Ephemeral Trash
Safely removes temporary files (`*.tmp`, `dump_*.json`, loose `.log` files):
```bash
# Preview what would be deleted
python path/to/scratch_ctl.py purge --dry-run

# Execute permanent deletion
python path/to/scratch_ctl.py purge --force
```

### 4. Rebuild Scratch Phonebook
Rebuilds `SCRATCH_PHONEBOOK.md` by reading metadata from all scripts in `scripts/scratch/`:
```bash
python path/to/scratch_ctl.py phonebook
```

---

## 📐 Standard Scratch Header Specification

When cataloged, every script receives an un-intrusive metadata docstring:

```python
"""
[SCRATCH ARTIFACT]
Script   : debug_atc_disconnect.py
Ticket   : BUG-02
Created  : 2026-11-05
Purpose  : Isolated verification for async RF link timeout during ATC landing.
Command  : python scripts/scratch/debug_atc_disconnect.py
"""
```

---

## 📋 Standard Phonebook Layout

The generated `SCRATCH_PHONEBOOK.md` maintains a clean tabular index:

| Script Name | Ticket / Tag | Purpose | Created | Execution Command |
| :--- | :--- | :--- | :--- | :--- |
| [`debug_atc.py`](debug_atc.py) | `BUG-02` | Isolated verification for async RF link timeout | 2026-11-05 | `python scripts/scratch/debug_atc.py` |
