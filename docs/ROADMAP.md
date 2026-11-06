# SCS_AG_v2 Engineering Roadmap

**System:** Session Continuity Steward for Antigravity (SCS_AG_v2)  
**Document Version:** 1.0.0  
**Status:** PUBLISHED ROADMAP  
**Current Milestone:** Phase 1 Feature Complete & Production Hardened (v1.0.0-prod)  
**Authority:** Stability Engineering & Product Validation  

---

## 1. Roadmap Overview & Phasing Principles

To maintain absolute software stability and forensic integrity, SCS_AG_v2 adheres to a strict phasing discipline:
- **Phase 1 (v1.0.0):** Focuses exclusively on core reliability, zero-daemon execution, file-first storage, cryptographic state sealing, and human custody boundaries. **(100% Complete & Hardened)**.
- **Phase 2 (v2.0.0):** Explores optional acceleration, multi-vault search, and IDE daemon sidecars without compromising Phase 1 invariants. **(Formally Deferred)**.

```
┌────────────────────────────────────────────────────────┐
│ PHASE 1: Zero-Daemon Core Architecture (v1.0.0)        │  [100% COMPLETE & SEALED]
│  - Native transcript reading & watermark slicing       │  ✓ 124/124 Passing Tests
│  - Dual-layer staging quarantine gate                  │  ✓ 8 Dogfooding Sessions
│  - Canonical machine SSOT (ledger.json)                │  ✓ 11 Sealed Snapshots
│  - One-way deterministic markdown projections          │  ✓ 9.7/10 Rehydration Score
│  - Centralized out-of-repo vault separation            │  ✓ Production Verified
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ PHASE 2: Scale Acceleration & Tooling Ecosystem        │  [FROZEN / DEFERRED]
│  - SQLite shadow index for gigabyte-scale transcripts   │  ⏸ Pending Phase 1 sign-off
│  - Optional background filesystem watcher sidecar       │  ⏸ No daemon in v1.0
│  - Cross-project semantic search & embeddings          │  ⏸ Zero network in v1.0
│  - VS Code / JetBrains IDE language server extensions   │  ⏸ CLI/Skill first
└────────────────────────────────────────────────────────┘
```

---

## 2. Phase 1 Milestone Verification (v1.0.0 Feature Complete)

All Phase 1 capabilities are fully implemented, verified, and sealed:

- [x] **Step 1.1:** Read-Only Core Adapter (`engine/core_adapter.py`) bridging Antigravity dialogue to Caveman heuristics with secret scrubbing and path traversal defense.
- [x] **Step 1.2:** File-First Vault Storage (`engine/vault_store.py`) with deterministic SHA-256 state sealing, rollback, and staging quarantine.
- [x] **Step 1.3:** Streaming Transcript Reader (`engine/transcript_reader.py`) with watermark boundary deduplication and truncated line resolution.
- [x] **Step 1.4:** Unified Zero-Dependency CLI (`engine/scs_cli.py`) supporting `new`, `record`, `status`, `approve`, `reject`, `handover`, and `rollback`.
- [x] **Step 1.5:** Native Antigravity Skill Packaging (`.agents/skills/scs/SKILL.md`) with end-to-end slash command dispatch.
- [x] **Phase 1.6 Hardening:** Decision proposition sanitization, generic word filtering, Do-Not-Repeat capability protection, task reconciliation, and idempotent proposal deduplication.
- [x] **Production Dogfooding Program:** 8 production sessions recorded, 11 snapshots sealed, 0 canonical duplicates, and 9.7/10 independent cold-start rehydration score.

---

## 3. Phase 2 Capabilities (Formally Deferred)

The following capabilities were evaluated and intentionally deferred to Phase 2 to prevent premature complexity:

### 3.1 SQLite Shadow Indexing (Large Scale Optimization)
- **Concept:** Add an optional read-only SQLite shadow index for projects with $>1,000$ decisions or multi-gigabyte session logs.
- **Why Deferred:** Flat JSON files provide instantaneous sub-second execution ($0.25\text{s}$) for 1–50 sessions with complete human transparency and zero binary corruption risk.

### 3.2 Optional Background Watcher Sidecar
- **Concept:** An optional daemon process that listens for file write events and automatically triggers incremental capture without manual slash commands.
- **Why Deferred:** Background daemons introduce silent crash risks, battery drain, and file lock contention. The zero-daemon model is 100% reliable and deterministic.

### 3.3 Cross-Vault Semantic Search
- **Concept:** Vector embeddings for multi-project knowledge retrieval across distinct vaults.
- **Why Deferred:** Introduces heavy external dependencies (PyTorch, ONNX, external vector databases). Phase 1 maintains zero external dependencies.

### 3.4 Native IDE Extension Ecosystem
- **Concept:** Dedicated VS Code and JetBrains plugins rendering the visual recovery card and custody approval panel directly in the editor sidebar.
- **Status:** Architecture blueprint drafted in `FUTURE_ARCHITECTURE.md`; implementation scheduled for post-v1.0.

---

## 4. Release Milestones & Timeline

- **Milestone 1.0-RC1 (Completed):** Phase 1.6 Hardening complete, 116 tests passing, dogfooding baseline established.
- **Milestone 1.0-RC2 (Completed):** 124 tests passing, 8 sessions dogfooded, 11 snapshots sealed, 9.7/10 benchmark achieved.
- **Milestone 1.0-PROD (Active):** Production evidence preparation, verification suite documentation, reproducible validation scripts.
- **Milestone 1.1 (Next):** Session 10 Scalability Validation (Tier-2 consolidated chapter archive generation).
