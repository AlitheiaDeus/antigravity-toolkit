---
name: skill-curator
description: >-
  Audit, scaffold, and curate project-specific skills in <workspace-root>/.agents/skills/.
  Use when creating new in-project skills, validating frontmatter triggers and anatomy,
  checking for leaked machine paths, or promoting proven project skills to the global toolkit.
---

# `skill-curator` - In-Workspace Project Skills Artisan

This skill manages the lifecycle of project-specific skills located in `<workspace-root>/.agents/skills/`. It ensures in-project runbooks follow the official Antigravity anatomy, contain high-intent semantic triggers, maintain test coverage, and prevent personal machine paths from leaking into project version control.

---

## 1. When to Use

Reach for `skill-curator` when:
1. **Scaffolding In-Project Skills**: Creating a specialized build runner, deploy script, or test harness specific to the active repository.
2. **Quality & Privacy Auditing**: Verifying that `.agents/skills/` conforms to official Antigravity standards and leaks zero user machine paths (`C:\Users\...`).
3. **Inspecting Workspace Capabilities**: Listing all skills active in the current project.
4. **Promoting to Global**: Promoting a proven, reusable project skill to your global toolkit (`skills/`).

---

## 2. Global Tool Execution

**Script Path**:  
`$HOME/.gemini/config/skills/skill-curator/scripts/skill_ctl.py`

### CLI Quick Reference

```bash
# 1. List all project-specific skills in the current workspace (.agents/skills/)
python "$HOME/.gemini/config/skills/skill-curator/scripts/skill_ctl.py" list

# 2. Scaffold a new project skill (creates SKILL.md, scripts/, and tests/)
python "$HOME/.gemini/config/skills/skill-curator/scripts/skill_ctl.py" create my-tool --description "Specialized runner for project XYZ."

# 3. Audit all project skills against Antigravity standards & privacy rules
python "$HOME/.gemini/config/skills/skill-curator/scripts/skill_ctl.py" audit

# 4. Audit a specific project skill
python "$HOME/.gemini/config/skills/skill-curator/scripts/skill_ctl.py" audit my-tool

# 5. Promote a proven project skill to your global toolkit
python "$HOME/.gemini/config/skills/skill-curator/scripts/skill_ctl.py" promote my-tool
```

---

## 3. Official Skill Anatomy Enforced

`skill-curator` guarantees that every generated or audited skill adheres to the canonical standard:

```text
.agents/skills/<skill-name>/
├── SKILL.md          # Frontmatter (name + semantic description) + runbook body
├── scripts/          # Deterministic Python / Shell helper executables
└── tests/            # Automated unit tests validating script behavior
```

---

## 4. The Promotion Pipeline

When you develop a brilliant in-project skill that turns out to be useful across multiple repositories:
1. Run `python skill_ctl.py audit my-tool` to ensure 100% compliance.
2. Run `python skill_ctl.py promote my-tool` to copy it to your global toolkit repository.
3. Commit it to your Git repository and run `python sync.py --deploy` to make it available everywhere!
