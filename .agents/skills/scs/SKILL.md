---
name: scs
description: Session Continuity Steward for Antigravity. Preserves multi-session memory, causal decisions, rejected options, and project state without manual copy/paste.
---

# Session Continuity Steward (SCS_AG_v2)

This skill provides session continuity, causal decision tracking, rejected options memory, and cross-AI restoration for Antigravity projects without requiring manual copy/paste.

## Governing Principles

1. **Dispatcher Only**: This skill NEVER implements custom memory structures or writes directly to `.continuity/`. ALL actions MUST dispatch directly through the verified Python CLI: `python SCS_AG_v2/engine/scs_cli.py <subcommand>`.
2. **Preserve the Brain**: Uses the upstream SCS Caveman Context Extraction Engine (CEE), Reconciler, and Scrubber.
3. **Human Custody Gate**: When sessions are recorded (`/scs record`), extracted proposals are quarantined in `staging/pending_proposals.json`. The AI assistant CANNOT self-promote memory into canonical SSOT (`canonical/ledger.json`). An explicit operator command (`/scs approve`) is required.
4. **Cryptographic Sealing**: Canonical memory is sealed with deterministic SHA-256 hashes (`snapshots/LATEST_SEAL`).
5. **Fail-Closed Project Isolation**: Each project maintains its own isolated `.continuity/` vault. If multiple projects exist and context is ambiguous, the system halts and prompts the operator to specify the project code.

---

## Command Dispatch Reference

When the user enters `/scs <command>` or requests continuity operations, execute the corresponding command using `run_command`:

| User Command | CLI Execution | Description |
| :--- | :--- | :--- |
| `/scs record [PROJECT]` | `python SCS_AG_v2/engine/scs_cli.py record [PROJECT]` | Captures recent conversation turns, verifies raw immutability, extracts Caveman proposals, and places them into staging quarantine. |
| `/scs status [PROJECT]` | `python SCS_AG_v2/engine/scs_cli.py status [PROJECT]` | Displays project health, SHA-256 seal status, quarantined proposals, and active tasks. |
| `/scs approve [P01 ...] [--all]` | `python SCS_AG_v2/engine/scs_cli.py approve [P01 ...] [--all]` | Human custody ratification. Promotes quarantined proposals into canonical memory and creates a new cryptographic seal. |
| `/scs reject <P01> [--why "..."] [--record-why]` | `python SCS_AG_v2/engine/scs_cli.py reject <P01> [--why "..."] [--record-why]` | Discards a proposal, optionally recording it permanently in `REJECTED_OPTIONS.md`. |
| `/scs handover [PROJECT]` | `python SCS_AG_v2/engine/scs_cli.py handover [PROJECT]` | Compiles the Master AI Handover Package and fast Recovery Card for cross-AI session transfer. |
| `/scs rollback <SNP_CODE>` | `python SCS_AG_v2/engine/scs_cli.py rollback <SNP_CODE>` | Instantly rolls back canonical state to a previously sealed snapshot. |
| `/scs new <CODE> "<Name>"` | `python SCS_AG_v2/engine/scs_cli.py new <CODE> "<Name>"` | Initializes a new project continuity vault with baseline cryptographic seal. |
| `/scs list` | `python SCS_AG_v2/engine/scs_cli.py list` | Lists all discovered project vaults in the workspace and active focus. |
| `/scs switch <CODE>` | `python SCS_AG_v2/engine/scs_cli.py switch <CODE>` | Switches active project context to another discovered vault. |
| `/scs ui [PROJECT]` | `python SCS_AG_v2/engine/scs_cli.py ui [PROJECT]` | Generates an interactive Antigravity Generative UI HTML dashboard artifact. |

---

## Workflow Protocol for the AI Assistant

### 1. Recording Session Memory (`/scs record`)
When the user types `/scs record` or asks to checkpoint/record session progress:
1. Run `python SCS_AG_v2/engine/scs_cli.py record`.
   - Conversation ID, transcript path, and project routing are automatically detected.
2. Read the output. If candidate proposals were staged:
   - Present the proposals clearly to the operator (Decisions, Constraints, Tasks, Rejected Options).
   - Inform the operator that proposals are currently **quarantined in staging** awaiting their custody approval.
   - Prompt the operator: *"Please review the staged proposals above. Reply with `/scs approve --all` to ratify into canonical memory, or `/scs reject <ID>` to discard."*
3. **DO NOT** attempt to write to `canonical/ledger.json` or `.continuity/` directly.

### 2. Ratifying Proposals (`/scs approve`)
When the user types `/scs approve` or `/scs approve --all`:
1. Run `python SCS_AG_v2/engine/scs_cli.py approve --all` (or specific IDs if indicated).
2. Report the new cryptographic seal code, SHA-256 hash prefix, and updated markdown projections (`BLUEPRINT.md`, `canonical/*.md`).

### 3. Cross-AI Handover (`/scs handover`)
When the user types `/scs handover` or asks to prepare for another session / another AI:
1. Run `python SCS_AG_v2/engine/scs_cli.py handover`.
2. Confirm that `.continuity/handover/AI_HANDOVER_PACKAGE.md` and `.continuity/handover/PROJECT_RECOVERY_CARD.md` have been updated.
3. Present a concise summary of the active focus, next action, and how the next AI should resume.

### 4. Project Initialization (`/scs new`)
When the user types `/scs new <CODE> "<Name>"`:
1. Run `python SCS_AG_v2/engine/scs_cli.py new <CODE> "<Name>"`.
2. Confirm the `.continuity/` directory structure and baseline cryptographic seal.
