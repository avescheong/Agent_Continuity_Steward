# Agent Continuity Steward (SCS_AG_v2)
## Operational Feedback Update #002 — External DX Validation Ingestion

**Document Type:** Incremental Operational Feedback Intake  
**System:** Agent Continuity Steward for Antigravity (SCS_AG_v2)  
**Milestone:** Phase 13 Milestone 13.5 (External Developer Experience Validation)  
**Document Version:** 1.0.0  
**Status:** 🏁 **TRIAGED & RATIFIED**  
**Production Baseline:** `v1.0.1 General Availability (GA)` (Immutable)  
**Active Development Ref:** `develop` (`origin/develop`)  
**Ingestion Timestamp:** 2026-11-06T21:35:00+08:00  

---

### 1. Ingestion Summary

During Phase 13 Milestone 13.5, an end-to-end validation was executed simulating an external developer in a clean room environment (fresh Python 3.13 venv, zero prior `.scs` vaults, zero external dependencies). 

Three new operational feedback items (`FDB-101-013` through `FDB-101-015`) were identified, analyzed, and added to the Master Intake Matrix.

---

### 2. New Feedback Dossiers

#### 2.1 Feedback Item: `FDB-101-013`
- **Identifier:** `FDB-101-013`
- **Scenario:** `SCN-ONBD` / `SCN-EXT` (External Developer Journey & Script Integration)
- **Subsystem:** `COMP-VAULT` (`engine.vault_store.read_staging`, `engine.scs_cli.cmd_status`)
- **Severity:** **P2** (Ergonomic / Defensive Robustness)
- **Problem Statement:**
  When external tools or developer scripts write a raw JSON array `[...]` of proposals into `.continuity/staging/pending_proposals.json` rather than wrapping it in a top-level dictionary `{"protocol": "scs-staging/1.0", "proposals": [...]}`, subsequent invocations of `scs status`, `scs approve`, or `scs reject` crash with an unhandled exception:
  ```text
  AttributeError: 'list' object has no attribute 'get'
  ```
- **Root Cause:**
  `read_staging(vault_dir)` parses JSON directly and assumes the root node is a dictionary (`st.get("proposals", [])`).
- **Proposed v1.1.0 Resolution:**
  Add defensive normalization in `read_staging`:
  ```python
  data = json.loads(paths["pending_proposals_json"].read_text(encoding="utf-8"))
  if isinstance(data, list):
      data = {"protocol": "scs-staging/1.0", "proposals": data}
  return data
  ```

---

#### 2.2 Feedback Item: `FDB-101-014`
- **Identifier:** `FDB-101-014`
- **Scenario:** `SCN-ONBD` / `SCN-PERS` (Non-Antigravity & Standalone CLI Ingestion)
- **Subsystem:** `COMP-CLI` (`engine.scs_cli.cmd_record`, `engine.extractor`)
- **Severity:** **P2** (Workflow Portability)
- **Problem Statement:**
  When developers run `scs record` in a generic shell or CI/CD runner without Google Antigravity active, `scs record` fails with:
  ```text
  [X] Missing conversation ID. Provide via --conv-id <UUID> or CONVERSATION_ID env var.
  ```
  Developers wishing to import human-curated meeting notes, Markdown transcripts, or local session summaries directly from disk cannot do so without spoofing Antigravity transcript directory structures.
- **Root Cause:**
  `cmd_record` currently assumes conversation logs must reside in `<appData>/brain/<conv-id>/logs/transcript.jsonl`.
- **Proposed v1.1.0 Resolution:**
  Add `--file <PATH>` argument to `scs record`:
  ```bash
  scs record --project DX-PROJ --file ./meeting_notes.md
  ```
  If `--file` is provided, `scs record` reads dialogue evidence directly from the markdown file, parses normative statements (`Decision: ...`, `Constraint: ...`), stages proposals into quarantine, and bypasses Antigravity transcript log lookup.

---

#### 2.3 Feedback Item: `FDB-101-015`
- **Identifier:** `FDB-101-015`
- **Scenario:** `SCN-PERS` / `SCN-PROJ` (Snapshot Inspection & Recovery UX)
- **Subsystem:** `COMP-CLI` (`engine.scs_cli`)
- **Severity:** **P3** (CLI Ergonomics)
- **Problem Statement:**
  Snapshots are automatically generated upon every canonical ledger ratification (`SNP-YYYYMMDD-001`, `SNP-YYYYMMDD-002`), but developers have no CLI command to discover or inspect available snapshots without navigating `.continuity/snapshots/` directly on disk.
- **Root Cause:**
  `scs_cli` provides `rollback`, but does not expose a read-only `scs snapshot list` or `scs snapshot view` subcommand.
- **Proposed v1.2.0 Resolution:**
  Implement `scs snapshot` subcommand family:
  - `scs snapshot list [project]` $\rightarrow$ Displays tabular sequence of snapshot codes, timestamps, sealed SHA-256 hashes, and decision counts.
  - `scs snapshot inspect [project] <CODE>` $\rightarrow$ Shows JSON diff and metadata for a specific snapshot.

---

### 3. Updated Matrix Summary

With Update #002, the total operational feedback count rises from 12 to 15 items:
- **Total Triaged Items:** 15
- **Sev-1 (Critical Regressions):** 0
- **Sev-2 (Ergonomic Enhancements):** 11
- **Sev-3 (Architectural Expansions):** 3
- **Sev-4 (Documentation Polish):** 1 (Resolved)
- **Production Baseline Integrity:** 100% UNMODIFIED (`v1.0.1 GA` on `main`)

*Ratified by Stability Engineering & External Developer Advocacy.*  
*Timestamp: 2026-11-06T21:35:00+08:00*