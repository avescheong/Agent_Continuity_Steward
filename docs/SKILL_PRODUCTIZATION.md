# Skill Productization & Real-World User Workflow Validation Guide

**System:** Agent Continuity Steward (SCS)  
**Release Candidate:** v0.9.0-rc1  
**Status:** Pre-Release Validation Baseline  
**Audience:** Open-Source Engineers, Antigravity Operators, AI System Architects  

---

## 1. Overview & Architecture

The **Session Continuity Steward (`scs`) Skill** transforms Google Antigravity and compatible AI coding environments into an evidence-first, memory-governed development assistant. 

Unlike conventional AI tools that mutate workspace files directly or rely on fragile conversational summaries, the `scs` skill operates strictly as a **deterministic dispatcher**:

```
┌────────────────────────────────────────────────────────┐
│                   Antigravity Chat                     │
│       Operator enters: /scs record | /scs approve      │
└───────────────────────────┬────────────────────────────┘
                            │ (Progressive Disclosure)
                            ▼
┌────────────────────────────────────────────────────────┐
│             .agents/skills/scs/SKILL.md                │
│         Governing Instructions & Dispatch Rules        │
└───────────────────────────┬────────────────────────────┘
                            │ (Subprocess CLI Execution)
                            ▼
┌────────────────────────────────────────────────────────┐
│            Unified CLI: scs / scs_cli.py               │
├───────────────────────────┬────────────────────────────┤
│  Watermark Slicer         │  Staging Quarantine Gate   │
│  Caveman Extraction (CEE) │  Canonical Machine SSOT    │
│  Secret Scrubber          │  Deterministic SHA Sealer  │
└───────────────────────────┴────────────────────────────┘
```

### Governing Architecture Invariants
1. **Dispatcher-Only Mandate:** The AI assistant never writes directly to `.continuity/` or invents custom memory schemas. All continuity operations dispatch through the verified Python CLI.
2. **Quarantine Before Canon:** Extracted proposals (decisions, tasks, rejected options) are quarantined in `staging/pending_proposals.json`. The AI is strictly barred from self-promoting memory.
3. **Sole Machine SSOT:** `canonical/ledger.json` is the sole source of truth. Markdown files (`BLUEPRINT.md`, `DECISIONS.md`) are one-way projections.
4. **Air-Gapped & Zero-Daemon:** Pure Python standard library (>= 3.10). No background servers, no daemon threads, zero external dependencies.

---

## 2. Skill Installation Workflow

The `scs` skill can be installed in three distinct ways depending on team requirements.

### Method A: Global User Installation (Recommended for Daily Development)
Installs the skill across all repositories and workspaces opened on your machine.

1. **Install the CLI Globally onto your Python Environment:**
   ```powershell
   git clone https://github.com/Agent-Continuity-Steward/Agent_Continuity_Steward.git
   cd Agent_Continuity_Steward
   pip install -e .
   ```
   *Verify installation:*
   ```powershell
   scs --help
   ```

2. **Copy the Skill Definition into Antigravity Global Configuration:**
   - **Windows:**
     ```powershell
     New-Item -ItemType Directory -Force -Path "$HOME\.gemini\config\skills\scs"
     Copy-Item -Path ".agents\skills\scs\SKILL.md" -Destination "$HOME\.gemini\config\skills\scs\SKILL.md" -Force
     ```
   - **macOS / Linux:**
     ```bash
     mkdir -p ~/.gemini/config/skills/scs
     cp .agents/skills/scs/SKILL.md ~/.gemini/config/skills/scs/SKILL.md
     ```

3. **Verification:**
   Open Antigravity in any project directory and type:
   ```
   /scs
   ```
   Antigravity will display the registered `scs` skill and its available command options.

---

### Method B: Workspace-Specific Installation (Recommended for Team Repositories)
Binds the skill directly to a project repository so every team member using Antigravity inherits it automatically from Git without manual machine configuration.

1. In your project repository root:
   ```powershell
   New-Item -ItemType Directory -Force -Path ".agents\skills\scs"
   Copy-Item -Path "path\to\Agent_Continuity_Steward\.agents\skills\scs\SKILL.md" -Destination ".agents\skills\scs\SKILL.md"
   ```
2. Commit `.agents/skills/scs/SKILL.md` to your version control system:
   ```bash
   git add .agents/skills/scs/SKILL.md
   git commit -m "feat: add Antigravity Session Continuity Steward skill"
   ```

---

### Method C: Zero-Install Standalone Execution
For environments where `pip` installation is restricted, the AI executes the CLI directly via Python:
```powershell
python -m engine.scs_cli <command>
# OR
python /path/to/Agent_Continuity_Steward/engine/scs_cli.py <command>
```

---

## 3. Skill Activation & Dispatch Workflow

### 3.1 Progressive Disclosure
Antigravity automatically loads only the skill name and description into the conversation prompt:
> `scs: Session Continuity Steward for Antigravity. Preserves multi-session memory, causal decisions, rejected options, and project state without manual copy/paste.`

When the user enters `/scs <command>` or asks continuity questions, Antigravity loads the full `SKILL.md` instructions dynamically.

### 3.2 Dynamic CLI Dispatch Precedence
The AI assistant resolves the execution path using the following deterministic hierarchy:
1. **`scs <command>`:** If `scs` is registered on system `PATH` (via pip).
2. **`python -m engine.scs_cli <command>`:** If executing from an SCS repository root.
3. **`python <resolved_path_to_scs_cli.py> <command>`:** Dynamic path discovery across workspace roots.

### 3.3 The Operator Custody Lifecycle
```
Step 1: Discussion & Work
        Operator and AI collaborate in Antigravity chat.
                       │
                       ▼
Step 2: Incremental Capture
        Operator triggers: /scs record
        Engine reads transcript.jsonl via step watermark.
        Raw evidence stored in .continuity/evidence/raw_sessions/SES*.md.
        Proposals staged in .continuity/staging/pending_proposals.json.
                       │
                       ▼
Step 3: Staging Review
        AI reports staged items (Decisions, Constraints, Tasks).
        AI informs operator: "Quarantined in staging awaiting human custody approval."
                       │
                       ▼
Step 4: Custody Ratification
        Operator triggers: /scs approve --all (or /scs reject <ID>)
        Engine merges items into canonical/ledger.json.
        Deterministic SHA-256 state seal computed (SNP-YYYYMMDD-NNN).
        One-way Markdown projections updated.
                       │
                       ▼
Step 5: Handover Compilation
        Operator triggers: /scs handover
        Engine compiles PROJECT_RECOVERY_CARD.md and AI_HANDOVER_PACKAGE.md.
```

---

## 4. User Command Reference

| Command | Syntax | Primary Options | Description |
|:---|:---|:---|:---|
| **`new`** | `/scs new <CODE> "<Name>"` | `--vault <PATH>`<br>`--roots <PATHS>`<br>`--objective "<TEXT>"` | Initializes an isolated project continuity vault with baseline cryptographic seal (`SNP-BASELINE`). |
| **`record`** | `/scs record [CODE]` | `--conv-id <ID>`<br>`--app-data <PATH>` | Reads recent conversation turns incrementally, extracts propositions via CEE, scrubs secrets, and places candidates into staging quarantine. |
| **`status`** | `/scs status [CODE]` | `--json` | Displays snapshot seal status, cryptographic integrity, quarantined proposal count, and task completion metrics. |
| **`approve`** | `/scs approve [--all] [P01 ...]` | `--project <CODE>` | **Human custody gate.** Ratifies quarantined proposals into canonical memory and computes a new SHA-256 seal. |
| **`reject`** | `/scs reject <P01>` | `--why "<REASON>"`<br>`--record-why`<br>`--project <CODE>` | Discards a staged proposal, optionally recording the rationale permanently into `REJECTED_OPTIONS.md`. |
| **`handover`** | `/scs handover [CODE]` | None | Compiles the fast Recovery Card (~900 tokens) and complete Master Handover Package (~12k tokens) in `.continuity/handover/`. |
| **`rollback`** | `/scs rollback <SNP_CODE>` | `--project <CODE>` | Instantly restores `canonical/ledger.json` from a previous cryptographic snapshot seal. |
| **`list`** | `/scs list` | `--workspace <PATH>` | Discovers and lists all project continuity vaults found in the active workspace and external centralized vault directory. |
| **`switch`** | `/scs switch <CODE>` | None | Sets the active project context in multi-project workspaces. |
| **`ui`** | `/scs ui [CODE]` | `--open` | Generates a standalone, interactive HTML dashboard artifact visualizing project topology, decisions, and tasks. |

### Exit Codes
- `0`: Success (Operation completed, seal verified).
- `1`: Error (Validation failed, seal mismatch, or fail-closed violation).
- `2`: Syntax Error (Missing required positional arguments).

---

## 5. Example Project Integration Walkthrough

This walkthrough demonstrates integrating `scs` into a realistic greenfield or existing project (`PaymentService`).

### Phase 1: Initialize Vault Outside the Git Tree
To avoid bloating Git history with continuous snapshot evidence, vaults live in a centralized user directory:

```powershell
# In your terminal or via Antigravity chat:
scs new PAY "Payment Microservice" `
  --objective "Build Stripe & PayPal webhook processing service" `
  --vault "$HOME\My_Project_Continuity\PAY" `
  --roots "$HOME\projects\PaymentService"
```

**Output:**
```
Creating continuity vault for Payment Microservice (PAY) at: C:\Users\<YOU>\My_Project_Continuity\PAY...
[OK] Successfully created .continuity vault.
  Project Code:  PAY
  Baseline Seal: a8f4e2... (Valid: True)
  Kickoff File:  C:\Users\<YOU>\My_Project_Continuity\PAY\.continuity\BLUEPRINT.md
  Workspace Rule:C:\Users\<YOU>\projects\PaymentService\GEMINI.md
```

### Phase 2: Discuss Architecture in Antigravity Chat
Discuss requirements with your AI assistant:
> **Developer:** "Let's use PostgreSQL with SQLAlchemy for payment transaction logs, and implement HMAC SHA-256 signature verification for Stripe webhooks. We should explicitly reject storing raw credit card details in our database to maintain strict PCI-DSS Level 1 compliance."

### Phase 3: Ingest Dialogue Evidence
Run the record command:
```
/scs record
```

**Output:**
```
[SCS] Sliced 4 new dialogue turns into SES001_20261106_1400.md.
[SCS] 3 candidate proposals staged in pending_proposals.json:
  [P01] [DECISION] Adopt PostgreSQL with SQLAlchemy for payment transaction logs
  [P02] [CONSTRAINT] Reject storing raw credit card details for PCI-DSS compliance
  [P03] [TASK] Implement HMAC SHA-256 webhook signature verification
[SCS] All proposals quarantined. Please review and approve via /scs approve --all.
```

### Phase 4: Ratify Proposals (Human Custody Gate)
Review and approve the memory:
```
/scs approve --all
```

**Output:**
```
[SCS] Promoted 3 proposals into canonical/ledger.json.
[SCS] State sealed at snapshot SNP-20261106-002 (SHA-256: 7f8b91a...).
[SCS] Projections regenerated: BLUEPRINT.md, DECISIONS.md, TASKS.md.
```

### Phase 5: Generate Master Handover Package
Before ending your work session:
```
/scs handover
```

**Generated Artifacts:**
1. `.continuity/handover/PAY_PROJECT_RECOVERY_CARD.md`: Fast 30-second context briefing for next session.
2. `.continuity/handover/PAY_AI_HANDOVER_PACKAGE.md`: Complete architectural state including ADRs and Do-Not-Repeat memory.

---

## 6. Skill Testing & Quality Assurance Checklist

Use this checklist to validate the `scs` skill experience prior to public deployment.

### 6.1 Discovery & Syntax Tests
- [ ] **Frontmatter Validity:** Verify `SKILL.md` contains valid YAML header (`name: scs`, valid description).
- [ ] **Slash Command Recognition:** Typing `/scs` in Antigravity chat suggests the skill and lists subcommands.
- [ ] **Help Command:** `scs --help` executes in $< 0.1\text{s}$ with zero errors.

### 6.2 Dispatch & Execution Tests
- [ ] **Global CLI Dispatch:** Test `/scs status` when installed via `pip install -e .`.
- [ ] **Fallback Module Dispatch:** Test `python -m engine.scs_cli status` from repository root.
- [ ] **Zero-Daemon Verification:** Confirm no lingering background process or open socket remains after any command finishes.

### 6.3 Custody Gate & Security Tests
- [ ] **Quarantine Enforcement:** Confirm `/scs record` leaves `canonical/ledger.json` unchanged until `/scs approve` is issued.
- [ ] **AI Self-Promotion Prevention:** Confirm the AI assistant refuses to edit `canonical/ledger.json` directly.
- [ ] **Secret Scrubber:** Test recording dialogue containing mock API keys (`sk-ant-12345...`) and confirm keys are redacted as `[REDACTED_API_KEY]`.

### 6.4 Sealing & Integrity Tests
- [ ] **Deterministic Sealing:** Verify `/scs status` reports `[SEAL INTACT]`.
- [ ] **Tamper Sensitivity:** Manually modify 1 character in `canonical/ledger.json` and verify `/scs status` immediately alerts `[FAIL] SEAL MISMATCH`.
- [ ] **Deterministic Rollback:** Verify `/scs rollback <PREV_SEAL>` restores exact ledger state and re-verifies seal.

### 6.5 Cold-Start Rehydration Tests
- [ ] Open a completely new, blank Antigravity chat session.
- [ ] Feed `PROJECT_RECOVERY_CARD.md`.
- [ ] Ask the AI: *"What is our architecture focus, and what approaches did we explicitly reject?"*
- [ ] Verify the incoming AI accurately recalls decisions and respects negative constraints without re-proposing rejected options.

---

## 7. Operational Surveillance & Dogfooding Protocol

Any defect observed during operational testing is recorded under the strict format:
```
Observation → Evidence → Root Cause → Fix Proposal → Verification
```
All observations during this phase are cataloged starting at **`DFG-011`** in `docs/DOGFOODING_LOG.md`.
