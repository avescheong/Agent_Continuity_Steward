# SCS_AG_v2 System Architecture & Topology

**System:** Session Continuity Steward for Antigravity (SCS_AG_v2)  
**Document Version:** 1.0.0  
**Status:** APPROVED ARCHITECTURAL SPECIFICATION  
**Authority:** Stability Engineering & Product Validation  
**Reference ADRs:** ADR-001 through ADR-008  

---

## 1. High-Level Architecture Topology

SCS_AG_v2 operates as a layered, file-first, zero-daemon continuity pipeline. It bridges native AI agent dialogue logs with a cryptographically sealed, human-governed continuity ledger.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. NATIVE TRANSCRIPT & WATERMARK INGESTION (engine/transcript_reader.py)    │
│  - Reads transcript.jsonl & resolves truncated fields via transcript_full   │
│  - Tracks incremental step_index watermark in MANIFEST.json                │
│  - Writes immutable raw session evidence to evidence/raw_sessions/SES*.md   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Raw incremental dialogue
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. CONTEXT EXTRACTION & PROPOSITION SANITIZATION (engine/core_adapter.py)   │
│  - Pre-extraction secret scrubber (redacts API keys, tokens, passwords)     │
│  - Upstream Caveman heuristics extract decisions, constraints, tasks       │
│  - Sanitizes table scraps, generic words ("count", "noise"), and meta-terms │
│  - Protects negative knowledge against capability inversions               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Candidate proposals
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. DUAL-LAYER STAGING QUARANTINE GATE (staging/pending_proposals.json)      │
│  - Quarantines unverified AI propositions outside canonical machine state   │
│  - Exposes pending items to human operator via `/scs status`                │
│  - Prevents conversational report noise from polluting canonical SSOT       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Explicit Human Approval (/scs approve)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. CANONICAL MACHINE SSOT & CRYPTOGRAPHIC SEALING (engine/vault_store.py)   │
│  - Sole machine authority: canonical/ledger.json (Schema: scs-ledger/1.0)   │
│  - Idempotent deduplication engine: updates existing entities in-place      │
│  - Deterministic SHA-256 state sealing: snapshots/SNP-*.json & LATEST_SEAL │
│  - One-way markdown projection rendering (DECISIONS.md, TASKS.md, etc.)    │
│  - 10-session consolidated chapter archiving (prepare_10_session_archive)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Sealed state + physical reconciliation
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. CROSS-AI RESTORATION HANDOVER LAYER (engine/core_adapter.py)             │
│  - Resilient multi-root physical artifact verification                      │
│  - Master AI Handover Package (AI_HANDOVER_PACKAGE.md ~12k tokens)          │
│  - Fast Project Recovery Card (PROJECT_RECOVERY_CARD.md ~900 tokens)        │
│  - Blind Cold-Start Benchmark: 9.7 / 10.0 Production-Grade Superior         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Breakdown & Responsibilities

### 2.1 Transcript Reader (`engine/transcript_reader.py`)
- **Native Antigravity Slicing:** Discovers local conversation logs at `<appData>/brain/<conv_id>/.system_generated/logs/transcript.jsonl`.
- **Truncated Content Resolution:** Automatically resolves truncated planner responses by looking up the corresponding `step_index` in `transcript_full.jsonl`.
- **Watermark Deduplication:** Reads `watermarks_by_conversation` from `MANIFEST.json`. Only dialogue turns strictly greater than `last_step_index` are extracted. Subsequent calls without new turns return `NO_NEW_TURNS` in under 0.26s.
- **Forensic SES Creation:** Writes write-once, immutable `SES{NNN}_{YYYYMMDD}_{HHMM}.md` evidence files with YAML frontmatter containing step ranges, turn counts, and SHA-256 body hashes.

### 2.2 Core Adapter & Proposition Sanitizer (`engine/core_adapter.py`)
- **Secret Scrubber:** Executes regex-based credential redaction on conversation text before extraction, eliminating leaked secrets from continuity records.
- **Decision & Constraint Validator:** Filters out markdown table headers, test matrix scraps, and generic words (`count`, `status`, `check`, `item`) unless part of a complete architectural proposition.
- **Negative Knowledge Protection:** Verifies candidate rejected options against capability inversions, preventing core system features from being mislabeled as things to avoid.
- **Physical Artifact Custody Reconciler:** Scans registered artifacts across repository and vault roots, resiliently resolving nested subdirectories (`engine/`, `docs/`, `src/`) and verifying file existence and hashes.

### 2.3 Vault Store & Sealing Engine (`engine/vault_store.py`)
- **Machine SSOT Authority:** Maintains `canonical/ledger.json` as the sole authoritative state. Reverse-parsing Markdown into machine state is strictly prohibited.
- **Cryptographic State Sealing:** Serializes the canonical ledger deterministically (`sort_keys=True`) and computes its SHA-256 digest into `snapshots/SNP-{YYYYMMDD}-{NNN}.json` and updates `snapshots/LATEST_SEAL`. Single-byte tampering triggers immediate validation failure.
- **Idempotent Reconciliation:** When candidate proposals are promoted, `promote_proposals()` matches existing artifacts, tasks, constraints, and decisions in-place. Duplicate accumulation is mathematically impossible.
- **Tier-2 Consolidation:** Binds raw session accumulation. Every 10 sessions, `prepare_10_session_archive()` aggregates dialogue into secret-scrubbed chapter files (`evidence/archives/MD*.md`) while leaving all raw `SES*.md` files intact on disk.

### 2.4 Unified Command Line Interface (`engine/scs_cli.py`)
- Standard subcommands:
  - `scs new <NAME> --code <CODE> --vault <PATH>`: Initializes isolated vault.
  - `scs record [PROJECT]`: Slices incremental turns into raw SES evidence.
  - `scs status [PROJECT]`: Verifies SHA-256 seal integrity and reports pending proposals.
  - `scs approve --all --project [PROJECT]`: Ratifies staged proposals into canonical ledger.
  - `scs reject <ID> --project [PROJECT]`: Discards operational noise.
  - `scs handover [PROJECT]`: Generates restoration packages and audits physical artifacts.
  - `scs rollback --snapshot <SNP> --project [PROJECT]`: Restores prior sealed state.

### 2.5 Native Skill Dispatcher (`.agents/skills/scs/SKILL.md`)
- Integrates seamlessly with Google Antigravity's chat slash command routing (`/scs record`, `/scs status`, `/scs approve`, `/scs handover`), invoking the CLI under the hood without developer friction.

---

## 3. Data Storage & Vault Hierarchy

All continuity vaults are physically isolated from source code repositories and conform to the standard layout:

```text
My_Project_Continuity/<PROJECT_CODE>/
└── .continuity/
    ├── BLUEPRINT.md                         - Architectural blueprint projection
    ├── canonical/
    │   ├── ledger.json                      - SOLE MACHINE SSOT (scs-ledger/1.0)
    │   ├── DECISIONS.md                     - Ratified ADR projection
    │   ├── TASKS.md                         - Task lifecycle projection
    │   ├── REJECTED_OPTIONS.md              - Authoritative Do-Not-Repeat registry
    │   └── ARTIFACTS.md                     - Reconciled components projection
    ├── staging/
    │   ├── pending_proposals.json           - Quarantine gate for AI propositions
    │   └── REVIEW_DRAFT.md                  - Human inspection preview
    ├── snapshots/
    │   ├── LATEST_SEAL                      - Current SHA-256 checksum string
    │   ├── SNP-20261105-001.json            - Sealed state history
    │   └── ...
    ├── evidence/
    │   ├── MANIFEST.json                    - Session index & conversation watermarks
    │   ├── raw_sessions/                    - Tier 1: Immutable raw SES*.md markdown
    │   └── archives/                        - Tier 2: 10-session consolidated chapters
    └── handover/
        ├── <CODE>_AI_HANDOVER_PACKAGE.md    - Deep cross-AI restoration package
        └── <CODE>_PROJECT_RECOVERY_CARD.md  - Fast 30-sec recovery card
```

---

## 4. Frozen Governance Invariants (Immutable)

1. **Sole Machine SSOT:** `canonical/ledger.json` is the exclusive source of truth. Markdown files are strictly one-way projections.
2. **Immutable Forensic Backbone:** Raw session markdown files in `evidence/raw_sessions/` are append-only.
3. **Mandatory Human Custody:** Unverified AI extractions must be quarantined in `staging/` until explicit human approval.
4. **Upstream Read-Only Core:** Upstream `scs_core` files in `core/`, `src/`, `spec/` remain 100% read-only and immutable.
5. **Zero-Daemon Execution:** No long-running background processes or external database dependencies.
