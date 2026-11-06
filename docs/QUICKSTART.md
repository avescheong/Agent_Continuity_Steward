# Agent Continuity Steward (SCS_AG_v2) Quickstart Guide

> **Get up and running with evidence-first AI session continuity in under 5 minutes.**

[![Version: v1.0.1 GA](https://img.shields.io/badge/Release-v1.0.1%20GA-blue.svg)](https://github.com/avescheong/Agent_Continuity_Steward/releases/tag/v1.0.1)
[![Conformance: 134 Passing](https://img.shields.io/badge/Conformance-196%2F196%20Tests%20(100%25)-brightgreen.svg)](#)
[![Dependencies: Zero](https://img.shields.io/badge/Dependencies-Zero%20(Stdlib)-orange.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](../LICENSE)

---

## 1. Prerequisites & System Requirements

- **Python:** Python 3.10 or newer (certified on Python 3.10, 3.11, 3.12, 3.13).
- **Supported Operating Systems:** Windows 10/11, macOS (Apple Silicon / Intel), Linux (POSIX).
- **Runtime Dependencies:** **Zero external packages required.** Agent Continuity Steward operates purely with standard library modules (`json`, `hashlib`, `pathlib`, `argparse`, `re`, `datetime`, `sqlite3`, `uuid`).
- **IDE Environments:** Google Antigravity, VS Code, JetBrains, or standalone terminal.

---

## 2. Clean Installation & Verification

### Option A: Install from Certified Wheel (Recommended for Production)

```bash
# 1. (Optional but recommended) Create and activate a clean virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Windows Command Prompt:
.\.venv\Scripts\activate.bat
# Linux / macOS (Bash/Zsh):
source .venv/bin/activate

# 2. Install the certified zero-dependency distribution wheel
pip install agent_continuity_steward-1.1.0-py3-none-any.whl
```

### Option B: Install from GitHub Repository

```bash
git clone -b develop https://github.com/avescheong/Agent_Continuity_Steward.git
cd Agent_Continuity_Steward

# Standard local installation
pip install .

# Or editable development installation
pip install -e .
```

---

### Verify Installation

Run the CLI help command or release verification suite:

```bash
scs --help
```

Or run the automated release verification script:

```bash
python scripts/verify_release.py
```

Expected verification output:
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

--- 4. Automated Conformance Test Suite (196 Tests) ---
Ran 116 tests (Engine Suite: src/engine/) -> OK
Ran 80 tests (Upstream Normative Suite: tests/) -> OK
[OK] 100% Test Conformance Achieved (196/196 tests passing).

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

## 3. Step-by-Step Operator Workflow (Canonical v1.1.0 CLI)

### Step 1: Initialize a Project Continuity Vault
Initialize an isolated `.continuity/` vault for your project. You can store the vault inside your repository or in an out-of-repo directory to keep git history clean:

```bash
# Initialize vault using flag syntax (v1.1.0):
scs new --code PAY --name "Payment Gateway" --objective "Build Stripe & PayPal integration"

# Or initialize using backward-compatible positional syntax:
scs new PAY "Payment Gateway" --objective "Build Stripe & PayPal integration"

# Or initialize in a centralized user directory:
scs new --code PAY --name "Payment Gateway" `
  --path "$HOME\My_Project_Continuity\PAY" `
  --repo "./PaymentGateway" `
  --objective "Build Stripe & PayPal integration"
```

*Note:* Direct module execution is always available without PATH dependencies:  
`python -m engine.scs_cli new PAY "Payment Gateway"`

---

### Step 2: Record an AI Dialogue Session
After completing an architectural discussion, brainstorming alternatives, or finishing code modifications in your IDE, capture the session:

```bash
# Incremental capture from active IDE transcript:
scs record PAY

# Or standalone Markdown transcript ingestion outside Antigravity (v1.1.0):
scs record PAY --file ./session_transcripts/chat_20261107.md
```

**Under the Hood:**
1. Reads native conversation transcripts incrementally using the watermark in `MANIFEST.json`.
2. Preserves verbatim raw dialogue in an append-only file: `.continuity/evidence/raw_sessions/SES001_YYYYMMDD_HHMM.md`.
3. Sanitizes extractions, rejecting conversational noise, table scraps, and generic filler words.
4. Quarantines candidate decisions, constraints, tasks, and artifacts into `.continuity/staging/pending_proposals.json` with **zero initial authority**.

---

### Step 3: Inspect Status & Quarantine Proposals
Review the cryptographic seal status, task progress, and candidate proposals awaiting custody review:

```bash
scs status PAY
```

Output example:
```text
================================================================================
[SCS_AG_v2] STATUS REPORT: Payment Gateway (PAY)
================================================================================
Active State Seal:  14046da4bebb4127cd81943f... (SEAL INTACT)
Tasks Progress:     ✓ 4 completed / 2 pending

Pending Proposals Awaiting Human Custody Review:
  [P01] [DECISION] Adopt a Dual-Layer Staging Architecture
  [P02] [CONSTRAINT] Zero external runtime dependencies
  [P03] [TASK] Implement resilient multi-root artifact resolution
================================================================================
```

---

### Step 4: Exercise the Human Custody Gate
The human operator has sole custody over canonical memory. Promote genuine architectural decisions or reject speculative noise:

```bash
# Batch approval shorthand with attribution (v1.1.0):
scs approve --project PAY 1,2 --author "Lead Architect"

# Approve all staged proposals in batch:
scs approve --project PAY --all

# Or selectively promote specific proposals:
scs approve --project PAY P01 P02

# Or reject operational noise, optionally recording negative knowledge:
scs reject --project PAY P03 --record-why --why "Avoid external Redis daemon for local-first purity"
```

**Upon Approval:**
1. Candidate proposals are idempotently committed to `canonical/ledger.json`.
2. A new deterministic snapshot (`snapshots/SNP-YYYYMMDD-002.json`) is computed and sealed with SHA-256.
3. One-way Markdown projections (`docs/DECISIONS.md`, `docs/CONSTRAINTS.md`, `docs/TASKS.md`, `docs/REJECTED_OPTIONS.md`) are regenerated automatically.

---

### Step 5: Generate Master Handover Packages
Before switching tasks, restarting your IDE, or handing work over to another engineer or AI model, compile context restoration packages:

```bash
# Standard file generation (.continuity/handover/):
scs handover PAY

# Handover depth profiles (v1.1.0): compact, standard, or deep
scs handover PAY --profile compact

# Direct stdout piping or card-only output (v1.1.0):
scs handover PAY --stdout
scs handover PAY --card-only
```

This generates two complementary restoration documents in `.continuity/handover/`:
1. **`PAY_PROJECT_RECOVERY_CARD.md`** (~300 tokens): Ultra-fast 30-second cognitive briefing detailing current focus, immediate next action, and active tasks.
2. **`PAY_AI_HANDOVER_PACKAGE.md`** (~2,500+ tokens): Complete architectural restoration dossier containing ADR rationales, hard constraints, Do-Not-Repeat negative knowledge, and physical artifact audits.

---

### Step 6: Speculative Rollback (Safety Reversion)
If an exploratory refactoring session or speculative subagent experiment fails, revert canonical memory to a prior verified snapshot:

```bash
# Option A: Flag syntax
scs rollback --project PAY --snapshot SNP-20261106-001

# Option B: Positional syntax
scs rollback --project PAY SNP-20261106-001
```

*Guarantee:* The ledger and all one-way Markdown projections instantly revert to the exact bit-level SHA-256 seal of the chosen snapshot.

---

### Step 7: Git Pre-Commit State Seal Guard (v1.1.0)
Install the standalone zero-dependency Git pre-commit state seal verification guard into your repository:

```bash
scs hook install --git
```

**Guard Guarantees:**
- Verifies `canonical/ledger.json` syntax and schema integrity on every commit.
- Computes deterministic SHA-256 seal and validates against `snapshots/LATEST_SEAL`.
- Fails closed (blocks commit) if unauthorized manual modifications or corruption occurred.
- Preserves existing pre-commit hooks (linters, formatters, type-checkers).

---

## 4. Google Antigravity Skill Integration

When operating inside Google Antigravity, the native skill (`.agents/skills/scs/SKILL.md`) maps slash commands directly to the CLI:

| Antigravity Slash Command | CLI Equivalent | Operational Purpose |
| :--- | :--- | :--- |
| `/scs record` | `scs record` | Incremental watermark capture from current conversation transcript |
| `/scs status` | `scs status` | Display cryptographic state seal and quarantined candidate proposals |
| `/scs approve` | `scs approve --all` | Promote staged candidates into sealed canonical memory |
| `/scs handover` | `scs handover` | Generate Master AI Handover Package and Project Recovery Card |
| `/scs rollback` | `scs rollback` | Revert project state to a prior sealed snapshot |

---

## 5. Troubleshooting & External Operator Readiness

### Windows PowerShell Script Execution Policy
**Symptom:** Running `scs` in PowerShell produces `File ...\scs.ps1 cannot be loaded because running scripts is disabled on this system.`  
**Cause:** Default Windows PowerShell restricts un-signed script wrappers.  
**Resolution:**
```powershell
# Set execution policy for current process only:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

# Or execute directly via Python module (bypasses PowerShell wrapper):
python -m engine.scs_cli status PAY
```

---

### Ambiguous Project Error (`AmbiguousProjectError`)
**Symptom:** `[X] Ambiguous project routing: Multiple project vaults discovered.`  
**Cause:** Multiple `.continuity/` vaults exist in parent or sibling directories, and no project was specified.  
**Resolution:** Pass the explicit project code or target path:
```bash
scs status --project PAY
# or
scs status PAY
```

---

### Cryptographic Seal Mismatch (`[SEAL BROKEN]`)
**Symptom:** `scs status` outputs `[!] WARNING: Cryptographic seal mismatch detected!`  
**Cause:** `canonical/ledger.json` was manually edited, formatted, or modified by an external tool out-of-band.  
**Resolution:** Revert the unauthorized modification using rollback:
```bash
scs rollback --project PAY --snapshot <LATEST_VALID_SNAPSHOT>
```

---

## 6. Related Documentation

- [`GOVERNANCE_MODEL.md`](GOVERNANCE_MODEL.md) — The formal Three-Tier Memory Lifecycle & Operator Custody Protocol.
- [`DESIGN_PHILOSOPHY.md`](DESIGN_PHILOSOPHY.md) — Technical rationale for zero-daemon and standard library purity.
- [`SECURITY_MODEL.md`](SECURITY_MODEL.md) — Secret scrubbing, path traversal defense, and air-gapped guarantees.
- [`NEXT_DEVELOPMENT_ROADMAP.md`](../NEXT_DEVELOPMENT_ROADMAP.md) — Living roadmap for v1.1.0, v1.2.0, and deferred v2.0.0.
- [`PHASE_13_OPERATIONAL_ADOPTION_PLAN.md`](../PHASE_13_OPERATIONAL_ADOPTION_PLAN.md) — Phase 13 operational adoption charter and scenarios.
- [`V1_X_FEEDBACK_REGISTRY.md`](../V1_X_FEEDBACK_REGISTRY.md) — Operational feedback intake registry.
