# Agent Continuity Steward (SCS_AG_v2) Engineering Roadmap

**System:** Agent Continuity Steward for Antigravity (SCS_AG_v2)  
**Document Version:** 1.0.1 GA Baseline  
**Status:** PUBLISHED ENGINEERING ROADMAP & BASELINE RECORD  
**Production Milestone:** Phase 1 GA Complete & Sealed (`v1.0.1 GA` — Commit `988cce7dc8d060532f4e694aa8228baca6248ebb`)  
**Forward Development Ref:** [`NEXT_DEVELOPMENT_ROADMAP.md`](../NEXT_DEVELOPMENT_ROADMAP.md) (on `develop` branch)  
**Authority:** Stability Engineering & Product Validation  

---

## 1. Roadmap Overview & Phasing Principles

To maintain absolute software stability and forensic integrity, Agent Continuity Steward adheres to a strict phasing discipline:

- **Phase 1 (v1.0.0 & v1.0.1 GA):** Focuses exclusively on core reliability, zero-daemon execution, file-first storage, cryptographic state sealing, and human custody boundaries. **(100% Complete, Hardened & Sealed)**.
- **Phase 13 (v1.x Operational Adoption):** Validates real-world adoption across four scenarios (`SCN-PERS`, `SCN-PROJ`, `SCN-TEAM`, `SCN-ONBD`) without mutating the frozen GA baseline.
- **Phase 2 (v2.0.0):** Explores optional acceleration, multi-vault search, and IDE daemon sidecars without compromising Phase 1 invariants. **(Formally Deferred)**.

```
┌────────────────────────────────────────────────────────┐
│ PHASE 1: Zero-Daemon Core Architecture (v1.0.1 GA)     │  [100% COMPLETE & SEALED]
│  - Native transcript reading & watermark slicing       │  ✓ 134/134 Passing Tests
│  - Dual-layer staging quarantine gate                  │  ✓ 8 Dogfooding Sessions
│  - Canonical machine SSOT (ledger.json)                │  ✓ 11 Sealed Snapshots
│  - One-way deterministic markdown projections          │  ✓ 9.7/10 Rehydration Score
│  - Standard library pure models (zero dependencies)   │  ✓ Clean-Room Certified
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ PHASE 13: v1.x Operational Adoption (Active on develop)│  [ACTIVE ADOPTION]
│  - Personal AI Continuity (SCN-PERS)                   │  ✓ Sub-30s Rehydration
│  - Project Continuity & Rollback (SCN-PROJ)            │  ✓ Verified Hash Restoration
│  - Team Swarm & Quarantine Isolation (SCN-TEAM)        │  ✓ 100% Gate Protection
│  - External Onboarding (SCN-ONBD)                      │  ✓ Zero-Dependency Journey
│  - Target Release: v1.1.0 Ergonomics Minor Milestone   │  → NEXT_DEVELOPMENT_ROADMAP.md
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ PHASE 2: Scale Acceleration & Tooling Ecosystem        │  [FROZEN / DEFERRED]
│  - SQLite shadow index for gigabyte-scale transcripts   │  ⏸ Pending Phase 1 sign-off
│  - Optional background filesystem watcher sidecar       │  ⏸ No daemon in v1.x
│  - Cross-project semantic search & embeddings          │  ⏸ Zero network in v1.x
│  - VS Code / JetBrains IDE language server extensions   │  ⏸ CLI/Skill first
└────────────────────────────────────────────────────────┘
```

---

## 2. Phase 1 Milestone Verification (v1.0.1 GA Complete)

All Phase 1 core capabilities are fully implemented, verified, and sealed into the production baseline:

- [x] **Step 1.1:** Read-Only Core Adapter (`engine/core_adapter.py`) bridging Antigravity dialogue to Caveman heuristics with secret scrubbing and path traversal defense.
- [x] **Step 1.2:** File-First Vault Storage (`engine/vault_store.py`) with deterministic SHA-256 state sealing, rollback, and staging quarantine.
- [x] **Step 1.3:** Streaming Transcript Reader (`engine/transcript_reader.py`) with watermark boundary deduplication and truncated line resolution.
- [x] **Step 1.4:** Unified Zero-Dependency CLI (`engine/scs_cli.py`) supporting `new`, `record`, `status`, `approve`, `reject`, `handover`, and `rollback`.
- [x] **Step 1.5:** Native Antigravity Skill Packaging (`.agents/skills/scs/SKILL.md`) with end-to-end slash command dispatch.
- [x] **Phase 1.6 Hardening:** Decision proposition sanitization, generic word filtering, Do-Not-Repeat capability protection, task reconciliation, and idempotent proposal deduplication.
- [x] **Post-GA Remediation (v1.0.1):** Zero external dependencies achieved via stdlib models (`POST-GA-001`), canonical PyPA package layout consolidated (`POST-GA-002`), dual rollback syntax added (`POST-GA-003`), and Quickstart aligned with 134/134 passing tests (`POST-GA-004`).

---

## 3. Forward Engineering Roadmap (`v1.1.0` and Beyond)

All forward development for the v1.x series is governed by [`NEXT_DEVELOPMENT_ROADMAP.md`](../NEXT_DEVELOPMENT_ROADMAP.md) and conducted exclusively on the `develop` branch:

- **Milestone `v1.1.0` (Ergonomics & Team Polish):**
  - Batch custody promotion shorthand (`scs approve --all`, `scs approve 1,2,3`).
  - Handover depth profiles (`--profile compact|standard|deep`).
  - Multi-author attribution tracking (`approved_by`, `operator_id`).
  - Standalone Git pre-commit state seal integrity hook.
  - Dual flag syntax aliases for `scs new` (`--code` and `--name`).
- **Milestone `v1.2.0` (Scale & Archival Compaction):**
  - Tier-2 consolidated chapter archiving (`scs archive` for Session 10+ compaction).
  - Universal vault discovery precedence chain.

---

## 4. Phase 2 Capabilities (Formally Deferred)

The following capabilities were evaluated and intentionally deferred to Phase 2 to protect the zero-daemon, zero-dependency guarantees of the v1.x series:

### 4.1 SQLite Shadow Indexing (Large Scale Optimization)
- **Concept:** Add an optional read-only SQLite shadow index for projects with $>1,000$ decisions or multi-gigabyte session logs.
- **Why Deferred:** Flat JSON files provide instantaneous sub-second execution ($0.12\text{s}$–$0.25\text{s}$) for 1–50 sessions with complete human transparency and zero binary corruption risk.

### 4.2 Optional Background Watcher Sidecar
- **Concept:** An optional daemon process that listens for file write events and automatically triggers incremental capture without manual slash commands.
- **Why Deferred:** Background daemons introduce silent crash risks, battery drain, and file lock contention. The zero-daemon model is 100% reliable and deterministic.

### 4.3 Cross-Vault Semantic Search
- **Concept:** Vector embeddings for multi-project knowledge retrieval across distinct vaults.
- **Why Deferred:** Introduces heavy external dependencies (PyTorch, ONNX, external vector databases). The v1.x series maintains zero external dependencies.

### 4.4 Native IDE Extension Ecosystem
- **Concept:** Dedicated VS Code and JetBrains plugins rendering visual recovery cards and custody panels directly in editor sidebars.
- **Status:** Architecture blueprint preserved in `FUTURE_ARCHITECTURE.md`; implementation scheduled for post-v1.x.

---

## 5. Master Release Log

- **Milestone 1.0.0 GA (Completed 2026-11-06):** Commit `3196997` (124 tests, production baseline established).
- **Milestone 1.0.1 GA (Completed 2026-11-06):** Commit `988cce7` (134 tests, stdlib models, zero runtime dependencies, PyPA layout). **(IMMUTABLE PRODUCTION BASELINE)**.
- **Milestone 13.1 & 13.2 (Completed 2026-11-06):** Operational adoption charter, 4 controlled simulation field runs, telemetry baseline recorded on `develop`.
- **Milestone 1.1.0 (Next Target):** Operational ergonomics and team collaboration enhancements on `develop`.
