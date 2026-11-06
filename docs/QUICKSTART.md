# SCS_AG_v2 Quickstart Guide

> **Get up and running with evidence-first AI session continuity in under 5 minutes.**

---

## 1. Prerequisites

- **Python:** Python 3.10 or newer (tested on 3.10, 3.11, 3.12, 3.13).
- **Environment:** Windows, macOS, or Linux.
- **Dependencies:** **Zero external packages required.** SCS_AG_v2 uses only the Python standard library (`json`, `hashlib`, `pathlib`, `argparse`, `re`, `datetime`).

---

## 2. Installation & Verification

Clone the repository and install as an editable package (or use direct module execution):

```powershell
# 1. Clone repository
git clone https://github.com/avescheong/Agent_Continuity_Steward.git
cd Agent_Continuity_Steward

# 2. Option A: Standard installation (provides global 'scs' command)
pip install .

# 2. Option B: Editable development installation
pip install -e .

# 3. Run release verification suite
python scripts/verify_release.py
```

Expected output:
```text
================================================================================
[SCS_AG_v2] PRODUCTION RELEASE VERIFICATION SUITE
================================================================================

--- 1. Python Environment Check ---
Detected Python Version: 3.13.x
[OK] Python version satisfies minimum requirement (>= 3.10).

--- 2. Dependency Verification ---
[OK] All 10 standard library modules verified.
[OK] Zero external third-party pip dependencies required.

--- 3. Codebase Component Discovery ---
[OK] Found: src\engine\vault_store.py
[OK] Found: src\engine\core_adapter.py
[OK] Found: src\engine\transcript_reader.py
[OK] Found: src\engine\scs_cli.py
[OK] Found: .agents\skills\scs\SKILL.md

--- 4. Automated Conformance Test Suite (134 Tests) ---
Ran 54 tests (Engine Suite: src/engine/) -> OK
Ran 80 tests (Upstream Normative Suite: tests/) -> OK
[OK] 100% Test Conformance Achieved (134/134 tests passing).

--- 5. Live Vault Lifecycle Verification (Ephemeral Sandbox) ---
[OK] Ephemeral vault created successfully.
[OK] Baseline SHA-256 state seal verified intact.
[OK] Proposal quarantine gate verified (1 item staged).
[OK] Human custody promotion & SHA-256 re-sealing verified intact.

================================================================================
[SUCCESS] RELEASE VERIFICATION SUCCESSFUL
================================================================================
```

---

## 3. Step-by-Step Operator Workflow

### Step 1: Initialize a Centralized Project Continuity Vault
Continuity vaults reside outside the project repository to prevent git commit bloat:

```powershell
scs new PAY "Payment Gateway" `
  --path "$HOME\My_Project_Continuity\PAY" `
  --repo "./PaymentGateway" `
  --objective "Build Stripe & PayPal integration"
```

*(Or zero-install: `python -m engine.scs_cli new PAY "Payment Gateway" ...`)*

This creates an isolated `.continuity/` vault with an initial cryptographic seal `SNP-BASELINE`.

### Step 2: Record an AI Session
After having an architecture discussion or completing a coding task in Antigravity, record the session:

```powershell
python -m engine.scs_cli record PAY
```

What happens under the hood:
1. Reads `transcript.jsonl` incrementally using the step-index watermark in `MANIFEST.json`.
2. Creates an immutable raw evidence file: `.continuity/evidence/raw_sessions/SES001_YYYYMMDD_HHMM.md`.
3. Sanitizes propositions (rejecting table scraps and generic words).
4. Quarantines candidate decisions, constraints, tasks, and artifacts in `.continuity/staging/pending_proposals.json`.

### Step 3: Inspect Status & Staged Quarantine Proposals
Inspect the cryptographic seal and review what the AI extracted:

```powershell
python -m engine.scs_cli status PAY
```

Output displays:
- Snapshot seal status: `[OK] [SEAL INTACT]`
- Task completion progress: `✓ 6 completed / 4 pending`
- Staged proposals awaiting custody review:
  - `[P01] [DECISION] Adopt a Dual-Layer Staging Architecture`
  - `[P02] [TASK] Implement resilient multi-root artifact resolution`

### Step 4: Exercise the Human Custody Gate
Approve genuine architectural memory into canonical SSOT:

```powershell
# Approve all staged proposals
python -m engine.scs_cli approve --all --project PAY

# Or selectively reject operational noise
python -m engine.scs_cli reject P03 --project PAY
```

Upon approval:
1. Candidate proposals are idempotently merged into `canonical/ledger.json`.
2. A new cryptographic snapshot (`SNP-YYYYMMDD-002`) is computed and sealed with SHA-256.
3. One-way Markdown projections (`DECISIONS.md`, `TASKS.md`, `REJECTED_OPTIONS.md`, `ARTIFACTS.md`) are regenerated automatically.

### Step 5: Generate Master Handover Packages
Before switching conversations, restarting your IDE, or handing off to another AI agent:

```powershell
python -m engine.scs_cli handover PAY
```

Outputs two cross-AI restoration packages in `.continuity/handover/`:
1. **`PAY_PROJECT_RECOVERY_CARD.md`** (~900 tokens): Fast 30-second cognitive briefing outlining active focus, immediate next action, and top tasks.
2. **`PAY_AI_HANDOVER_PACKAGE.md`** (~12k tokens): Complete architectural restoration package including topology overview, ADR rationales, Do-Not-Repeat negative knowledge, and physical artifact audits.

---

## 4. Using Antigravity Chat Slash Commands

When working inside Google Antigravity, the native skill routes slash commands directly to the CLI:

- `/scs record`: Captures new turns from active conversation into evidence.
- `/scs status`: Displays seal integrity and staged proposals.
- `/scs approve`: Ratifies staged proposals.
- `/scs handover`: Regenerates recovery card and master handover package.

---

## 5. Rollback to Prior Sealed State

If an accidental change occurs, rollback to any sealed snapshot deterministically. Both flag alias and positional syntax are supported:

```powershell
# Option A: Flag syntax
scs rollback --snapshot SNP-20261105-001 --project PAY

# Option B: Positional syntax
scs rollback SNP-20261105-001 --project PAY
```

*(Or direct module execution: `python -m engine.scs_cli rollback --snapshot SNP-20261105-001 --project PAY`)*
