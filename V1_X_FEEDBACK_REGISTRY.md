# Agent Continuity Steward (SCS_AG_v2)
## v1.x Operational Feedback & Telemetry Registry

**Document Type:** Continuous Operational Telemetry & Feedback Registry  
**System:** Session Continuity Steward for Antigravity (SCS_AG_v2)  
**Document Version:** 1.0.0  
**Registry Status:** 🟢 **ACTIVE OPERATIONAL INTAKE**  
**Production Baseline:** `v1.0.1 General Availability (GA)` (Immutable)  
**Target Development Branch:** `develop`  
**Operating Policy:** Non-invasive collection without altering GA production baseline  
**Authority:** Stability Engineering & Architecture Governance  

---

### 1. Registry Architecture & Operational Governance

This registry captures real-world operational feedback, ergonomic friction, edge-case observations, and workflow telemetry gathered across the four Phase 13 operational adoption scenarios:
1. **Personal AI Continuity** (`SCN-PERS`)
2. **Project Continuity** (`SCN-PROJ`)
3. **Team Workflow Continuity** (`SCN-TEAM`)
4. **External User Onboarding** (`SCN-ONBD`)

#### Core Governance Rules:
- **Baseline Protection:** No feedback item recorded in this registry authorizes immediate or unverified commits to the `main` release branch.
- **Evidence-First Requirement:** Every entry must include verbatim reproduction steps, CLI output transcripts, or exact operator quotes.
- **Traceable Triage:** Every item is formally triaged against target milestones (`v1.1.0`, `v1.2.0`, `v2.0.0`, or `DOCS_ONLY`).

```mermaid
flowchart TD
    FieldObservation["Field Observation / Operator Run"] --> Ingestion["Record into Feedback Registry (V1_X_FEEDBACK_REGISTRY.md)"]
    Ingestion --> EvidenceReview{"Evidence Complete?<br/>(Logs, Context, Reproduction)"}
    EvidenceReview -- No --> RequestDetails["Request Verbatim CLI & Environment Logs"]
    EvidenceReview -- Yes --> TriageGate{"Severity Triage"}
    
    TriageGate -->|Sev-1: Data Corruption| HotfixPath["Escalate to Emergency Hotfix Gate (v1.0.2)"]
    TriageGate -->|Sev-2: Ergonomic Friction| MinorMilestone["Schedule for v1.1.0 Roadmap (develop)"]
    TriageGate -->|Sev-3: Architectural Evolution| FutureMilestone["Schedule for v1.2+ / v2.0 Roadmap"]
    TriageGate -->|Sev-4: Doc Clarification| DocsQueue["Patch Documentation on develop"]
```

---

### 2. Operational Feedback Intake Matrix

| Feedback ID | Date | Scenario | Subsystem | Sev | Summary | Target Milestone | Status |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: | :---: |
| **`FDB-101-001`** | 2026-11-06 | `SCN-ONBD` | `COMP-CLI` | **P2** | Windows PowerShell execution policy guidance when launching CLI in restricted environments | `v1.1.0` / Docs | `TRIAGED` |
| **`FDB-101-002`** | 2026-11-06 | `SCN-PERS` | `COMP-SKILL` | **P2** | Handover briefing token density control (`--profile compact\|deep\|full`) for variable context windows | `v1.1.0` | `TRIAGED` |
| **`FDB-101-003`** | 2026-11-06 | `SCN-TEAM` | `COMP-VAULT` | **P2** | Multi-author attribution tracking (`approved_by`, `operator_id`) in canonical `ledger.json` | `v1.1.0` | `TRIAGED` |
| **`FDB-101-004`** | 2026-11-06 | `SCN-PROJ` | `COMP-VAULT` | **P3** | Hierarchical discovery precedence between centralized (`~/.scs/`) and workspace (`.scs_vault/`) | `v1.2.0` | `TRIAGED` |
| **`FDB-101-005`** | 2026-11-06 | `SCN-PERS` | `COMP-CLI` | **P2** | Batch approval & rejection shorthand syntax (`scs approve --all`, `scs approve 1,2,3`) | `v1.1.0` | `TRIAGED` |
| **`FDB-101-006`** | 2026-11-06 | `SCN-TEAM` | `COMP-EXTR` | **P2** | Subagent chatter heuristic noise suppression during large automated search loops | `v1.1.0` | `TRIAGED` |
| **`FDB-101-007`** | 2026-11-06 | `SCN-PROJ` | `COMP-VAULT` | **P3** | Standalone Git pre-commit hook script verifying SHA-256 state seal integrity before commit | `v1.1.0` | `TRIAGED` |
| **`FDB-101-008`** | 2026-11-06 | `SCN-ONBD` | `COMP-DOCS` | **P4** | `QUICKSTART.md` cross-platform shell syntax examples (PowerShell vs POSIX `export`/`set`) | `v1.0.2-docs` | `TRIAGED` |

---

### 3. Detailed Operational Feedback Dossiers

#### 3.1 `FDB-101-001`: Windows PowerShell Execution Policy Guidance
- **Scenario:** `SCN-ONBD` (External User Onboarding)
- **Subsystem:** `COMP-CLI` / `COMP-DOCS`
- **Severity:** P2 (Usability Friction)
- **Operator Report:**
  > *"When installing the wheel into a new virtual environment on Windows 11 with default PowerShell settings, running `scs` directly can trigger an execution policy error (`script cannot be loaded because running scripts is disabled on this system`) if pip placed a `.ps1` wrapper."*
- **Root Cause Analysis:** On default Windows consumer installations, PowerShell restricts script execution (`Restricted` or `RemoteSigned`). Running `python -m scs_cli` or `python -m engine.scs_cli` works 100% reliably, but running `scs.ps1` requires execution policy adjustment.
- **Impact on v1.0.1 GA:** Zero defect in code logic; standard Windows environment behavior.
- **Triage Recommendation:**
  1. Add an explicit Windows troubleshooting alert in `docs/QUICKSTART.md` recommending `python -m scs_core` or `Set-ExecutionPolicy -Scope Process Bypass`.
  2. For `v1.1.0`, bundle an executable runner script (`scs.cmd` / `scs.bat`) that invokes python without PowerShell execution policy restrictions.

---

#### 3.2 `FDB-101-002`: Handover Briefing Token Density Profiles
- **Scenario:** `SCN-PERS` (Personal AI Continuity)
- **Subsystem:** `COMP-SKILL` / `COMP-VAULT`
- **Severity:** P2 (Ergonomic Limitation)
- **Operator Report:**
  > *"When cold-starting a small fast model (e.g. flash-lite), the standard handover briefing is sometimes slightly too long (~1,200 tokens) for a quick task, whereas for a large frontier model doing complex refactoring, we want the exhaustive forensic quotes included."*
- **Root Cause Analysis:** Currently, `scs handover` outputs a fixed-length briefing containing active goals, top decisions, constraints, and open tasks. There is no flag to control summary density.
- **Impact on v1.0.1 GA:** None; v1.0.1 handover works reliably and achieved a 9.7/10 benchmark score.
- **Triage Recommendation:**
  - In `v1.1.0`, introduce a `--profile` flag to `scs handover`:
    - `--profile compact`: High-density ~300-word executive summary (ideal for quick sessions and lighter models).
    - `--profile standard` (default): The certified v1.0.1 format (~800–1,200 tokens).
    - `--profile deep`: Full forensic digest including evidence quotes and rejected option histories (~2,000+ tokens).

---

#### 3.3 `FDB-101-003`: Multi-Author Attribution Metadata in Canonical Ledger
- **Scenario:** `SCN-TEAM` (Team Workflow Continuity)
- **Subsystem:** `COMP-VAULT` (Data Model)
- **Severity:** P2 (Collaboration Enhancement)
- **Operator Report:**
  > *"When multiple engineers review and approve proposals in a shared project repo, `canonical/ledger.json` records the decision timestamp and evidence, but doesn't record who executed the approval command."*
- **Root Cause Analysis:** In v1.0.1, the approval entry records `session_code`, `timestamp`, and `seal`, but does not query `git config user.name` or accept an `--author` flag.
- **Impact on v1.0.1 GA:** None; single-operator model functions completely.
- **Triage Recommendation:**
  - In `v1.1.0`, add optional `--author` parameter to `scs approve` (defaulting to system environment `USER`, `USERNAME`, or `git config user.name`).
  - Keep backward-compatible with `scs-ledger/1.0` schema by storing `author` as an optional string attribute.

---

#### 3.4 `FDB-101-004`: Coexistence & Precedence of Centralized vs Workspace Vaults
- **Scenario:** `SCN-PROJ` (Project Continuity)
- **Subsystem:** `COMP-VAULT` (Storage Architecture)
- **Severity:** P3 (Architectural Refinement)
- **Operator Report:**
  > *"Some users prefer keeping `.scs_vault/` inside their git repo root for team sharing, while others prefer keeping it in `~/.scs/vaults/<proj>` to avoid git clutter. The CLI should have crystal clear auto-discovery rules."*
- **Root Cause Analysis:** `v1.0.1` supports custom `--vault` paths, but default resolution uses the active vault configuration in `~/.scs/config.json`.
- **Impact on v1.0.1 GA:** None; explicit `--vault <path>` works deterministically.
- **Triage Recommendation:**
  - In `v1.2.0`, formalize the vault discovery chain:
    1. CLI flag: `--vault <path>` (Highest precedence)
    2. Environment variable: `SCS_VAULT_PATH`
    3. Current working directory: `./.scs_vault/` (if present)
    4. Centralized user store: `~/.scs/vaults/<cwd_basename>/` (Default fallback)

---

#### 3.5 `FDB-101-005`: Batch Promotion & Rejection Shorthand
- **Scenario:** `SCN-PERS` (Personal AI Continuity)
- **Subsystem:** `COMP-CLI` (Ergonomics)
- **Severity:** P2 (Operator Ergonomics)
- **Operator Report:**
  > *"After a marathon 40-turn design session, the staging quarantine held 8 candidate decisions and 6 tasks. Approving them one-by-one by typing `scs approve DEC-001`, `scs approve DEC-002` was slightly repetitive. A batch approve option would save significant time."*
- **Root Cause Analysis:** In v1.0.1, `scs approve` without arguments prompts sequentially, or accepts single item IDs. There is no `--all` flag or comma-separated list parser.
- **Impact on v1.0.1 GA:** None; human custody gate is intentionally deliberate to prevent accidental bulk promotions.
- **Triage Recommendation:**
  - In `v1.1.0`, add ergonomic batching options:
    - `scs approve --all`: Promotes all pending items in staging after a single confirmation prompt.
    - `scs approve DEC-001,DEC-002,TSK-003`: Accepts comma-separated item lists.
    - `scs reject --all`: Clears staging quarantine in one command.

---

#### 3.6 `FDB-101-006`: Subagent Chatter Suppression during Parallel Loops
- **Scenario:** `SCN-TEAM` (Team Workflow Continuity)
- **Subsystem:** `COMP-EXTR` (Heuristics Engine)
- **Severity:** P2 (Heuristic Precision)
- **Operator Report:**
  > *"When invoking subagents for large exploratory research loops, subagents often output interim status reports like 'Step 3 of 10 complete'. The heuristic extractor occasionally flagged these as candidate tasks."*
- **Root Cause Analysis:** Although Phase 1.6 hardening eliminated generic verb tasks and report checklists, autonomous agent progress reporting patterns (e.g. `[Progress: X/Y]`) occasionally match task heuristic triggers.
- **Impact on v1.0.1 GA:** Minor; staging quarantine safely trapped all candidate tasks, preventing canonical ledger pollution.
- **Triage Recommendation:**
  - In `v1.1.0`, expand regex stop-phrases in `scs_core/heuristics.py` to suppress `[Progress: *]`, `Turn * of *`, and subagent completion heartbeats.

---

#### 3.7 `FDB-101-007`: Standalone Git Pre-Commit Hook
- **Scenario:** `SCN-PROJ` (Project Continuity)
- **Subsystem:** `COMP-VAULT` (Integrity Verification)
- **Severity:** P3 (Developer Tooling)
- **Operator Report:**
  > *"It would be great to have a simple `scs git-hook install` command that drops a `.git/hooks/pre-commit` verifying the active state seal matches `ledger.json` before developers push changes."*
- **Root Cause Analysis:** Developers committing markdown projections or ledger changes manually might commit tampered files without realizing it.
- **Impact on v1.0.1 GA:** None; `scs status` already does $O(1)$ verification when run manually.
- **Triage Recommendation:**
  - For `v1.1.0`, provide a zero-dependency script `scripts/scs-pre-commit.py` and a CLI helper `scs install-hook`.

---

#### 3.8 `FDB-101-008`: Cross-Platform Shell Syntax Examples
- **Scenario:** `SCN-ONBD` (External User Onboarding)
- **Subsystem:** `COMP-DOCS`
- **Severity:** P4 (Documentation Polish)
- **Operator Report:**
  > *"In `docs/QUICKSTART.md`, environment variable setting was shown as `export SCS_VAULT=...` which fails in standard Windows cmd/powershell."*
- **Root Cause Analysis:** Unix-centric documentation syntax for environment variable setting.
- **Impact on v1.0.1 GA:** Documentation presentation only; code is 100% platform-agnostic.
- **Triage Recommendation:**
  - Update `docs/QUICKSTART.md` on `develop` to provide tri-shell tabs: Bash/Zsh (`export`), PowerShell (`$env:`), and Windows CMD (`set`).

---

### 4. Summary & Action Plan

All 8 initial field feedback entries have been triaged:
- **0 Critical Regressions (Sev-1):** Production baseline `v1.0.1` remains 100% solid, stable, and immutable.
- **5 Ergonomic Enhancements (Sev-2):** Scheduled for milestone `v1.1.0` on the `develop` branch.
- **2 Ecosystem Expansions (Sev-3):** Scheduled for roadmap milestone `v1.2.0` / `v2.0.0`.
- **1 Documentation Polish (Sev-4):** Queued for immediate documentation update on `develop`.

---

### 5. Attestation & Governance

This registry serves as the authoritative evidentiary log for v1.x operational feedback. All contributions are subject to the evidence-first governance model of the Agent Continuity Steward project.

*Ratified by Stability Engineering & Architecture Governance.*  
*Timestamp: 2026-11-06T20:55:00+08:00*
