# SCS_AG_v2 Test Strategy

**System:** Session Continuity Steward for Antigravity (SCS_AG_v2)  
**Document Version:** 1.0.0  
**Status:** APPROVED & ACTIVE  
**Authority:** Stability Engineering & Product Validation  
**Total Automated Test Count:** **124 Tests** (54 Engine Suite + 70 Upstream Suite)  
**Current Pass Rate:** **100% (124/124 Passing, 0 Failures, 0 Errors)**  

---

## 1. Testing Philosophy & Guiding Principles

The SCS_AG_v2 test strategy is designed around the core architectural principle: **deterministic, zero-daemon, fully reproducible software verification**.

1. **Zero External Runtime Dependencies:** Tests require only the Python 3.10+ standard library (`unittest`, `tempfile`, `hashlib`, `json`, `pathlib`, `re`). No Docker, no SQLite servers, no network access, no background daemons.
2. **Ephemeral Test Isolation:** Every test executes inside an isolated `tempfile.TemporaryDirectory()`. Tests create, seal, verify, mutate, and tear down temporary vaults without side-effects on real continuity vaults or workspace source code.
3. **Forensic Cryptographic Verification:** All state changes are asserted using bit-level SHA-256 comparisons and schema conformance. A test passes only when cryptographic seals and manifest watermarks match expected signatures.
4. **Dual-Layer Pyramid:**
   - **Engine Layer (54 tests):** Tests the Antigravity-specific adapters, file-first vault storage, transcript readers, CLI entrypoints, and Phase 1.6 hardening invariants.
   - **Upstream Normative Layer (70 tests):** Tests the core Caveman extraction engine, approval boundaries, checkpoint engines, and benchmark scenarios to guarantee 100% backward and normative compatibility.

---

## 2. Test Architecture & Directory Topology

```
f:\000_Ai Project\AI SCS HUD\
├── SCS_AG_v2\
│   └── engine\
│       ├── test_vault_store.py              (8 tests)   - File-first vault storage, sealing & archives
│       ├── test_transcript_reader.py       (10 tests)  - Native transcript parsing & watermark slicing
│       ├── test_adapter_verification.py     (13 tests)  - Upstream bridge, scrubbers & handovers
│       ├── test_scs_cli.py                 (11 tests)  - Unified CLI command workflows
│       ├── test_phase1_5_e2e.py            (6 tests)   - Full project lifecycle end-to-end
│       └── test_phase1_6_hardening.py      (6 tests)   - Hardening invariants & deduplication
│
└── tests\                                   (70 tests)  - Upstream Normative Conformance Suite
    ├── test_approval_boundary.py           (3 tests)   - Staging quarantine vs canonical tables
    ├── test_bootstrap_and_scrubber.py      (2 tests)   - Secret scrubbing & bootstrap generation
    ├── test_caveman_validator.py           (19 tests)  - Heuristic proposition classification
    ├── test_checkpoint_engine.py           (6 tests)   - Multi-session chapter aggregation
    ├── test_db_and_models.py               (5 tests)   - Model constraints & unique indices
    ├── test_ipc_dispatcher_e2e.py          (3 tests)   - IPC dispatch & proposal staging
    ├── test_local_rpc_server.py            (8 tests)   - Local RPC authorization & tokens
    ├── test_longform_benchmarks.py         (8 tests)   - Complex multi-turn architecture scenarios
    ├── test_normative_conformance.py       (8 tests)   - Normative specification conformance
    ├── test_reconciler_readonly.py         (4 tests)   - Read-only artifact custody verification
    └── test_snapshot_and_handover.py       (3 tests)   - Handover package roundtrip & export
```

---

## 3. Test Suites Breakdown & Coverage Map

### 3.1 Engine Suite (`SCS_AG_v2/engine/`) — 54 Tests

| Test Module | Test Class | Count | Primary Focus & Coverage Area |
| :--- | :--- | :---: | :--- |
| `test_vault_store.py` | `TestVaultStore` | 8 | Vault creation, `canonical/ledger.json` read/write, markdown projections, SHA-256 sealing, single-byte tamper detection, rollback, project isolation, staging quarantine, and Tier-2 10-session consolidated archive compilation. |
| `test_transcript_reader.py` | `TestTranscriptReader` | 10 | Reading `transcript.jsonl`, resolving truncated lines via `transcript_full.jsonl`, stripping `<thinking>` and `<system>` wrappers, YAML frontmatter protection, watermark boundary slicing, multi-conversation isolation, immutable `SES*.md` formatting, and 10-session archive trigger hook. |
| `test_adapter_verification.py` | `TestCoreAdapterVerification` | 13 | Bridge between Antigravity dialogue and Caveman engine, regex secret scrubbing (API keys, JWTs), YAML frontmatter stripping, handover context compilation, resilient multi-root artifact custody reconciliation, conflict detection (offline vs cloud), and proposition sanitization. |
| `test_scs_cli.py` | `TestSCSCli` | 11 | CLI subcommands: `new`, `list`, `switch`, ambiguous project error handling, `record`, `status`, `approve`, `reject`, `handover`, `rollback`, and `ui` dashboard command. |
| `test_phase1_5_e2e.py` | `TestPhase15EndToEnd` | 6 | End-to-end user workflows: conversation auto-detection, multi-project vault creation, real session recording, custody gate ratification, cross-project isolation, and handover package restoration. |
| `test_phase1_6_hardening.py` | `TestPhase16Hardening` | 6 | Phase 1.6 Hardening Scenarios A–F: markdown table header rejection, generic word filtering (`count`, `status`), rejected option capability protection, completed task reconciliation against physical disk, handover topology overview injection, and canonical proposal idempotent deduplication. |

### 3.2 Upstream Normative Suite (`tests/`) — 70 Tests

| Test Module | Test Class | Count | Primary Focus & Coverage Area |
| :--- | :--- | :---: | :--- |
| `test_approval_boundary.py` | `TestApprovalBoundary` | 3 | Staged proposals do not mutate canonical state; approval creates canonical entities; rejection leaves canonical state clean. |
| `test_bootstrap_and_scrubber.py` | `TestBootstrapAndScrubber` | 2 | Secret scrubber redacts sensitive credentials; bootstrap markdown contains required sections. |
| `test_caveman_validator.py` | `TestCavemanContextValidator` | 19 | Heuristic proposition classification: distinguishing recommendations from decisions, human confirmation handling, question detection, constraint completeness, technical term preservation, conflict detection, and full provenance tracing. |
| `test_checkpoint_engine.py` | `TestCheckpointEngine` | 6 | Aggregation of 35 sessions into 4 chapters, raw evidence deduplication, continuity pillar preservation, and custody order verification (draft -> human approval -> seal). |
| `test_db_and_models.py` | `TestDBAndModels` | 5 | Data model validation, unique constraints, foreign key cascades, and entity code generators. |
| `test_ipc_dispatcher_e2e.py` | `TestIPCDispatcherE2E` | 3 | IPC dispatch lifecycle, proposal staging with rationale, and duplicate project code validation. |
| `test_local_rpc_server.py` | `TestLocalRPCServerAuthorization` | 8 | Local RPC token verification, authorization headers, HTML token injection, and unauthorized request rejection. |
| `test_longform_benchmarks.py` | `TestLongFormBenchmarks` | 8 | Benchmark scenarios: long multiturn architecture discussions, multiple rejected alternatives, decision reversals, partial agreements, code block preservation, and brainstorming filtering. |
| `test_normative_conformance.py` | `TestNormativeConformance` | 8 | Normative standard conformance tests for all standard architecture dialogue patterns. |
| `test_reconciler_readonly.py` | `TestReconcilerReadOnly` | 4 | Physical disk artifact verification, path traversal attack prevention (`../`), read-only filesystem guarantee, and required markers check. |
| `test_snapshot_and_handover.py` | `TestSnapshotAndHandover` | 3 | Snapshot sealing, project recovery card human filtering, and handover package export/re-import roundtrip. |

---

## 4. Test Execution Environment & Invocation Protocol

### 4.1 Unified Command Line Execution
The complete test suite of 124 tests is executed with zero setup via standard Python:

```powershell
python -c "
import unittest, sys
loader = unittest.TestLoader()
suite1 = loader.discover('SCS_AG_v2/engine', pattern='test_*.py')
sys.path.insert(0, 'core/python')
suite2 = loader.discover('tests', pattern='test_*.py')
runner = unittest.TextTestRunner(verbosity=2)
res1 = runner.run(suite1)
res2 = runner.run(suite2)
print(f'Engine Suite:   {res1.testsRun} run, {len(res1.failures)} failures, {len(res1.errors)} errors')
print(f'Upstream Suite: {res2.testsRun} run, {len(res2.failures)} failures, {len(res2.errors)} errors')
assert len(res1.failures) == 0 and len(res1.errors) == 0
assert len(res2.failures) == 0 and len(res2.errors) == 0
print('ALL 124 TESTS PASSED 100%')
"
```

### 4.2 Targeted Engine Hardening Suite Execution
For rapid verification during operational cycles:

```powershell
python SCS_AG_v2/engine/test_phase1_6_hardening.py
```

---

## 5. Regression Protection & Governance Invariant Enforcement

Every automated test run validates five core regression protections:

1. **Ledger SSOT Protection:** No test permits Markdown files to be read as input to canonical state.
2. **Seal Tamper Sensitivity:** If `canonical/ledger.json` is modified by even 1 character without going through `seal_snapshot()`, `verify_seal()` immediately returns `False`.
3. **Quarantine Isolation:** Candidate proposals appended to `staging/pending_proposals.json` never appear in `canonical/DECISIONS.md`, `canonical/TASKS.md`, or `canonical/ledger.json` until `promote_proposals()` is called.
4. **Watermark Monotonicity:** Ingesting step index $N$ advances the watermark. Steps $\le N$ are rejected on subsequent runs, guaranteeing idempotent ingestion.
5. **Deduplication Invariant:** Calling `promote_proposals()` with existing items updates the existing entry in-place and increments nothing, preserving strict entity uniqueness.
