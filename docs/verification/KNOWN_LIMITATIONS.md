# SCS_AG_v2 Known Limitations & Engineering Trade-Offs

**System:** Session Continuity Steward for Antigravity (SCS_AG_v2)  
**Document Version:** 1.0.0  
**Status:** PUBLISHED ENGINEERING ASSESSMENT  
**Authority:** Stability Engineering & Product Validation  
**Scope:** Phase 1 Feature-Complete Architecture  

---

## 1. Executive Summary

This document provides a transparent, evidence-based disclosure of the technical limitations, operating boundaries, and intentional architectural trade-offs inherent in **SCS_AG_v2 Phase 1**.

Every limitation documented below is the direct result of deliberate architectural trade-offs chosen to prioritize **stability, zero-daemon reliability, forensic transparency, and human custody** over unvetted automation.

---

## 2. Technical Limitations & Trade-Offs

### 2.1 Synchronous Invocation Model (Zero-Daemon Trade-Off)
- **Description:** SCS_AG_v2 contains zero background daemons, background threads, filesystem file-watchers, or cron schedulers.
- **Operational Impact:** Memory capture is not automatic or real-time. Ingestion occurs only when the operator invokes `/scs record` or runs `python scs_cli.py record`.
- **Architectural Rationale:** Eliminates background daemon crashes, hidden CPU/memory battery drain, thread race conditions, and uncoordinated file write contention. Execution is 100% deterministic and observable.
- **Phase 2 Status:** Background watcher sidecars and IDE daemon triggers are formally deferred to Phase 2.

### 2.2 Centralized Vault Separation (Out-of-Repo Storage)
- **Description:** Continuity vaults are maintained centrally at `My_Project_Continuity/<PROJECT_CODE>/` rather than inside the application source repository root.
- **Operational Impact:** When cloning a project repository on a second development machine, the continuity vault does not automatically travel with the application git commit tree unless the centralized vault directory is also backed up or synchronized.
- **Architectural Rationale:** ADR-005 established that storing raw conversation sessions and governance snapshots inside git repositories contaminates commit histories, triggers severe git merge conflicts across developer branches, and risks leaking proprietary conversation text to public GitHub remotes.
- **Mitigation:** The `AI_HANDOVER_PACKAGE.md` can be exported or committed to the repository if a team desires a static point-in-time restoration snapshot.

### 2.3 Single-Project Resolution in Multi-Vault Environments
- **Description:** If an operator registers multiple project vaults under `My_Project_Continuity` and executes `scs record` or `scs approve` in a directory containing no clear project identifier or conversation mapping, the CLI raises `AmbiguousProjectError`.
- **Operational Impact:** The operator must provide the project code explicitly:
  ```powershell
  python SCS_AG_v2/engine/scs_cli.py record <PROJECT_CODE>
  python SCS_AG_v2/engine/scs_cli.py approve --all --project <PROJECT_CODE>
  ```
- **Architectural Rationale:** Strict isolation invariant. SCS_AG_v2 refuses to guess which project vault to mutate when ambiguity exists, preventing accidental cross-project memory contamination.

### 2.4 Upstream Heuristic Sensitivity to Markdown Checklists
- **Description:** The upstream Caveman extraction heuristic interprets Markdown checklist syntax (`- [x] ...` or `- [ ] ...`) and operational summary sentences as candidate tasks or constraints.
- **Operational Impact:** When an operator posts a progress report containing markdown checklists into the conversation, `/scs record` stages these items as candidate tasks in `staging/pending_proposals.json`.
- **Architectural Rationale & Safeguard:** This is the exact reason the **Dual-Layer Staging Architecture (ADR-001)** was created. Unverified extractions are quarantined in `staging/` and never touch `canonical/ledger.json`. The operator exercises custody by discarding non-architectural proposals with `scs reject` or `vault_store.reject_proposal()`.

### 2.5 Flat-File JSON Scale Boundary (Deferred SQLite Indexing)
- **Description:** Machine state is serialized as indented JSON (`canonical/ledger.json`, `snapshots/SNP-*.json`).
- **Scale Horizon:** 
  - Validated for: $1\text{ to }50\text{ sessions}$, $\le 100\text{ decisions}$, $\le 500\text{ tasks}$, $\le 10\text{ MB total vault size}$.
  - For massive projects exceeding $1,000+$ decisions or gigabyte-scale conversation histories, JSON deserialization latency will scale linearly ($O(N)$).
- **Mitigation:** The Tier-2 10-session consolidated chapter archive engine (`prepare_10_session_archive`) bounds raw session accumulation. Full SQLite indexing is formally specified for Phase 2.

### 2.6 Native Antigravity Log Path Dependency
- **Description:** Tier 1 transcript reading relies on Antigravity's on-disk log format:
  ```text
  <appDataDir>/brain/<conversation-id>/.system_generated/logs/transcript.jsonl
  ```
- **Operational Impact:** If Antigravity alters its internal transcript file structure or runs in an environment where file logs are restricted, direct Tier 1 capture will fail.
- **Mitigation:** SCS_AG_v2 implements a **Tier 2 Fallback Architecture**: an in-memory or CLI temporary capture file (`staging/context_capture.tmp`) can be written directly by IDE skills or hooks when native log files are inaccessible.

---

## 3. Summary of Operational Guardrails

| Risk / Limitation | Default Behavior | Built-In Safeguard / Mitigation |
| :--- | :--- | :--- |
| **No Auto-Ingest** | CLI runs only on demand | Sub-second execution ($0.25\text{s}$) allows fast manual or hook invocation |
| **Out-of-Repo Storage** | Vault separated from code | Eliminates git commit bloat & branch merge collisions |
| **Report Checklist Noise** | Staged as candidate tasks | Quarantined in `staging/`; human custody rejects before canonical mutation |
| **Multi-Project Collisions** | Rejects ambiguous execution | Halts with `AmbiguousProjectError` requiring explicit `--project` flag |
| **Large Transcripts** | Watermark jump scanning | Slices incremental dialogue turns only; never re-scans past history |
| **Out-of-Band File Tampering** | Breaks SHA-256 state seal | `verify_seal()` immediately flags `[SEAL BROKEN]` |
