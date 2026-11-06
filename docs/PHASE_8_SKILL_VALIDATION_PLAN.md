# Phase 8: Real-World Antigravity Skill Validation Plan

**Document Version:** 1.0.0  
**Status:** APPROVED FOR EXECUTION  
**Author:** Stability Engineering & Product Validation  
**Date:** 2026-11-06  
**Scope:** Real-World Validation of Antigravity AI Skill (`scs`) prior to v1.0.0 Release  
**Target Checkpoint:** `v0.9.0-rc1` (Frozen at `5f215fc`)  
**Workspace:** `F:\000_Ai Project\AI SCS HUD`  

---

## 1. Executive Summary & Objective

With the clean release candidate successfully exported, verified (124/124 tests passing), and published to GitHub as frozen checkpoint **`v0.9.0-rc1`**, the objective shifts from internal code conformance to **Empirical User Experience & AI Skill Validation**.

Unit and integration tests prove the Python engine works mathematically; Phase 8 proves the **actual Antigravity AI pair programming experience** is seamless, intuitive, and robust under real conversation dynamics.

### Governing Constraints
- **Zero Architecture Changes:** Frozen invariants remain immutable (`canonical/ledger.json` as sole SSOT, staging quarantine gate, append-only SES evidence, zero daemons).
- **Zero Engine Features:** No Phase 2 feature expansion.
- **Strict Evidence Recording:** Every execution step, latency reading, failure, and fix must be documented under the dogfooding protocol (`DFG-012` onwards).
- **Frozen GitHub Origin:** `D:\000. GITHUB\Agent_Continuity_Steward` remains read-only during validation.

---

## 2. Environment Setup

### 2.1 Test Workspace Topologies
To validate that `scs` functions cleanly across diverse developer workflows without contaminating active development or Git trees, validation will test two independent environments:

| Environment | Purpose | Workspace Path | Continuity Vault Path |
|:---|:---|:---|:---|
| **Env A: Dedicated Sandbox Project (`SandboxApp`)** | Greenfield project simulation (simulating an external third-party user) | `F:\000_Ai Project\scs_dogfood_sandbox\SandboxApp` | `~/My_Project_Continuity/SANDBOX_APP` |
| **Env B: Active SCS Engineering Workspace** | Multi-session dogfooding on SCS itself | `F:\000_Ai Project\AI SCS HUD` | `~/My_Project_Continuity/SCS_AG_v2` |

### 2.2 Skill Installation Strategies to Validate
1. **Workspace-Level Installation:**
   - Place `.agents/skills/scs/SKILL.md` directly into `SandboxApp/.agents/skills/scs/`.
   - Verify that opening `SandboxApp` in Antigravity automatically detects the skill without machine configuration.
2. **Global Machine Installation:**
   - Link or copy `SKILL.md` into `$HOME/.gemini/config/skills/scs/SKILL.md`.
   - Verify that any unconfigured workspace on the machine inherits the skill.
3. **CLI Dispatch Verification:**
   - Primary: Verify `scs <command>` execution when installed via `pip install -e "D:\000. GITHUB\Agent_Continuity_Steward"`.
   - Fallback: Verify direct Python invocation (`python -m engine.scs_cli <command>`).

### 2.3 Skill Discovery Verification Protocol
Before issuing operations, verify:
- [ ] Antigravity system prompt exposes `scs` under the `<skills>` manifest.
- [ ] Progressive disclosure operates properly (full `SKILL.md` body is withheld until user triggers `/scs` or continuity intent).
- [ ] Typing `/scs` in chat triggers autocomplete/subcommand suggestions.
- [ ] `run_command` can execute `scs --help` within $< 0.15\text{s}$ with zero errors.

---

## 3. Core Skill Validation Matrix

The core skill validation evaluates all 8 operational touchpoints in sequential order:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  1. Loading  │ ──> │ 2. Parsing   │ ──> │ 3. Init (new)│ ──> │ 4. Record    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────┬───────┘
                                                                      │
┌──────────────┐     ┌──────────────┐     ┌──────────────┐            │
│  8. Handover │ <── │  7. Reject   │ <── │  6. Approve  │ <──────────┘
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                                 ▼
                                          ┌──────────────┐
                                          │ 5. Status    │
                                          └──────────────┘
```

| Touchpoint | Action | Command Under Test | Verification Criteria |
|:---|:---|:---|:---|
| **1. Loading** | Trigger skill via chat | `/scs` or `"What is our current project status?"` | Agent reads `SKILL.md` and displays available subcommands. |
| **2. Command Parsing** | Argument validation & syntax | `scs invalid_cmd`, `scs new` (no args) | Fails closed with clean exit code `2` and actionable help text; zero traceback crash. |
| **3. Project Init** | Initialize new project vault | `/scs new SBX "Sandbox Application" --vault "~/My_Project_Continuity/SBX"` | Vault created with baseline SHA-256 seal (`SNP-BASELINE`), `BLUEPRINT.md` generated, `GEMINI.md` rule created. |
| **4. Session Capture** | Extract conversation turns | `/scs record SBX` | Slices active dialogue turns; creates immutable `SES001_*.md`; stages candidate proposals in `pending_proposals.json`; **leaves `canonical/ledger.json` 100% untouched**. |
| **5. Status Reporting** | Inspect state & quarantine | `/scs status SBX` | Reports `[SEAL INTACT]`, displays staged proposal count, displays active task completion metrics. |
| **6. Approval Custody** | Ratify valid memory | `/scs approve --all --project SBX` | **Human custody gate verified:** AI presents proposals; human ratifies; proposals promoted into `canonical/ledger.json`; deterministic SHA-256 seal recomputed (`SNP-YYYYMMDD-002`). |
| **7. Rejection Custody** | Discard operational noise | `/scs reject P03 --why "Violates offline constraint" --record-why` | Proposal discarded from staging; rationale recorded permanently into `canonical/REJECTED_OPTIONS.md`. |
| **8. Handover Export** | Cross-AI restoration pack | `/scs handover SBX` | Compiles `SBX_PROJECT_RECOVERY_CARD.md` ($< 1\text{k}$ tokens) and `SBX_AI_HANDOVER_PACKAGE.md` in $< 0.5\text{s}$. |

---

## 4. Real AI Workflow Validation Scenarios

To prove real-world viability, four realistic developer interaction scenarios will be simulated and evaluated:

### Scenario 1: Greenfield AI Project Bootstrapping
- **Context:** A developer begins a new application with an AI assistant in Antigravity chat.
- **Workflow:**
  1. Developer: *"Let's build a REST API for invoice processing using FastAPI and PostgreSQL."*
  2. Developer triggers `/scs new INV "Invoice Service"`.
  3. AI confirms project creation and links the centralized continuity vault.
  4. Developer and AI discuss database options (decide PostgreSQL, reject MongoDB due to lack of ACID transactions).
  5. Developer triggers `/scs record INV`.
  6. AI lists candidate decisions and requests operator approval.
  7. Developer approves; initial state is cryptographically sealed.
- **Pass Criteria:** Vault cleanly initialized; 0 merge conflicts in project git repository; initial seal intact.

### Scenario 2: Long-Running Multi-Turn Session
- **Context:** Sustained pair programming across 10+ conversation turns with code modifications, task completions, and follow-up discussions.
- **Workflow:**
  1. Multiple implementation turns modifying code files.
  2. Incremental `/scs record` executed at logical milestones.
  3. Watermark verification: Re-running `/scs record` immediately without new dialogue must yield `NO_NEW_TURNS` in $< 0.3\text{s}$ with 0 duplicate SES files.
  4. Task reconciliation: Completed code files on disk must automatically reconcile task lifecycle to `COMPLETED`.
- **Pass Criteria:** Watermark boundary advances monotonically; zero duplicate decisions; canonical ledger remains $< 50\text{KB}$.

### Scenario 3: Sudden Interruption & Cold Restart
- **Context:** The developer closes Antigravity or compacts the conversation history. The incoming AI assistant starts with **zero conversation context**.
- **Workflow:**
  1. Generate handover package via `/scs handover`.
  2. Launch a completely fresh, blank conversation session.
  3. Feed `PROJECT_RECOVERY_CARD.md` (~900 tokens) to the new AI.
  4. Prompt the new AI:
     - *"What is our project objective?"*
     - *"What architectural decisions have we locked in?"*
     - *"What alternatives have we explicitly rejected, and why?"*
     - *"What is our immediate next action?"*
- **Pass Criteria:** The incoming AI accurately answers all 4 questions with zero hallucination, respects negative constraints, and achieves a cold-start rehydration score $\ge 9.0/10$.

### Scenario 4: Cross-AI Handover (Model Diversity & Negative Memory)
- **Context:** Handing off a project to an alternative model (e.g. Gemini ➔ Claude or Claude ➔ GPT).
- **Workflow:**
  1. Present the master handover package to an independent subagent auditor.
  2. Prompt the subagent to suggest an architecture for an unaddressed component.
  3. Test if the subagent proposes an alternative previously recorded in `REJECTED_OPTIONS.md`.
- **Pass Criteria:** The independent model explicitly notes the rejected options and refrains from re-proposing them ("Groundhog Day" mistake prevention).

---

## 5. Evidence Collection Protocol

Every validation execution must produce auditable telemetry.

### 5.1 Telemetry Recording Template
```markdown
### Validation Run: VAL-<RUN_ID>
- **Timestamp:** YYYY-MM-DDTHH:MM:SS+08:00
- **Scenario:** [Greenfield | Long-Running | Cold-Start | Cross-AI]
- **Target Project:** [SBX | PAY | SCS_AG_v2]
- **Commands Dispatched:**
  1. `scs <cmd>` -> Exit code: 0, Latency: X.XXXs
- **Output Observations:**
  - Raw stdout / stderr excerpts
  - Number of dialogue turns sliced
  - Number of proposals staged vs promoted vs rejected
- **Cryptographic State:**
  - Pre-seal: SNP-YYYYMMDD-NNN (SHA-256: ...)
  - Post-seal: SNP-YYYYMMDD-NNN (SHA-256: ...)
- **Observed Anomalies:** [None | Description]
- **Root Cause & Fix:** [If applicable]
- **Verification Result:** [PASS | FAIL]
```

### 5.2 Dogfooding Log Integration
All operational observations during Phase 8 testing will be sequentially logged in `docs/DOGFOODING_LOG.md` starting at **`DFG-012`**.

---

## 6. Success Criteria for v1.0.0 General Availability

Before tagging and releasing `v1.0.0`, all of the following gates must be satisfied:

| Gate | Requirement | Threshold | Verification Method |
|:---|:---|:---|:---|
| **Gate 1: Skill Discovery** | Antigravity reliably recognizes `/scs` commands in clean workspaces | 100% recognition | Manual and automated CLI dispatch |
| **Gate 2: Custody Gate Integrity** | Zero unauthorized memory mutations into `canonical/ledger.json` | 0 leaks | Code assertion + staging audit |
| **Gate 3: Cold-Start Recovery** | Fresh AI session correctly recovers architectural context | Score $\ge 9.0 / 10.0$ | Independent auditor subagent evaluation |
| **Gate 4: Sub-Second Performance** | Incremental capture & handover generation remain instantaneous | Capture $< 0.35\text{s}$<br>Handover $< 0.60\text{s}$ | `time.perf_counter()` telemetry |
| **Gate 5: Zero Repo Bloat** | Centralized continuity vault cleanly isolated outside git | 0 vault files in repo git tracking | `git status` check in managed projects |
| **Gate 6: Negative Constraint Memory** | AI successfully avoids previously rejected architectural options | 100% adherence | Cross-AI handover validation test |
| **Gate 7: Automated Conformance** | All test suites continue to pass without regression | 124 / 124 tests (100%) | `python scripts/verify_release.py` |

---

## 7. Execution Sequence & Next Step

```
Phase 8 Execution Sequence:
  Step 8.1: Create isolated SandboxApp test workspace (Env A).
  Step 8.2: Execute Core Skill Validation Matrix (Touchpoints 1-8).
  Step 8.3: Execute Real AI Workflow Validation (Scenarios 1-4).
  Step 8.4: Conduct Blind Cold-Start AI Rehydration Benchmark.
  Step 8.5: Log all observations under DFG-012+ in DOGFOODING_LOG.md.
  Step 8.6: Author PHASE_8_VALIDATION_REPORT.md.
  Step 8.7: Present final v1.0.0 release candidate recommendation.
```

**Next Immediate Action:** Await user authorization to begin Step 8.1.
