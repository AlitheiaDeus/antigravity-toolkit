# 🚀 Antigravity Agent Toolkit

A curated, version-controlled collection of custom skills, helper scripts, and guardrails for Google Antigravity agents.

---

## 📦 Included Skills

| Skill | Role | Key Tooling |
| :--- | :--- | :--- |
| **`kanban-workflow-guard`** | Modular Task Architecture (1-Card-1-Doc) & board integrity. | `scripts/kanban_ctl.py` |
| **`code-landmarks`** | Fast AST & bookmark symbol indexer for monolithic codebases. | `scripts/scan_landmarks.py` |
| **`git-workflow-guard`** | Atomic commits, privacy path sanitization, and repository hygiene. | Rules & Pre-commit guardrails |
| **`agents-md-curator`** | Landmark curation and anti-bloat invariants for `AGENTS.md`. | Architectural rules |

---

## ⚡ Quick Start (1-Click Setup)

To connect this repository to Antigravity on any machine:

```bash
python setup_toolkit.py
```

This will:
1. Register the portable path (`~/DeusLocker/AI/antigravity-toolkit/skills`) in `~/.gemini/config/skills.json`.
2. Automatically run all unit test suites across all skills to verify the local environment.

### Status & Verification
```bash
# Check current connection status
python setup_toolkit.py --status

# Run tests without modifying config
python setup_toolkit.py --skip-tests
```
