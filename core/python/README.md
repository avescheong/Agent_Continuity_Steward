# scs-core: Session Continuity Steward Reference Implementation

`scs-core` is the normative, headless Python reference implementation of the **Session Continuity Steward (SCS)** open specification.

It provides a vendor-neutral, local-first continuity stewardship engine designed to preserve project intelligence across disconnected, multi-turn AI sessions (ChatGPT, Claude, Gemini, local LLMs, and IDE assistants).

---

## Architectural Principles & Invariants

`scs-core` strictly enforces the five core architectural invariants established in [ADR-SCS-2026-001](../../SCS_ADR_v1.0.md) and [RFC-0001](../../spec/RFC-0001-CORE-SPEC.md):

1. **Human Custody & Authority Gating:** AI models cannot self-authorize. AI recommendations remain quarantined proposals until an authorized human operator explicitly ratifies them. Generic acknowledgments (*"OK"*, *"Continue"*, *"Proceed"*) cannot ratify proposals without explicit subject naming or affirmative adoption language.
2. **Dual-Ledger State Isolation:** Unverified evidence and raw conversation fragments reside strictly in the Quarantine Ledger (`staged_proposals`, `conversation_sessions`). Only ratified items cross into the Canonical Ledger (`decisions`, `tasks`, `artifacts`, `snapshots`).
3. **Fail-Closed Causal Verification:** Unparseable, ambiguous, or incomplete causal statements fail closed to unclassified context. Speculation and brainstorming are never classified as decisions.
4. **O_RDONLY Reality Auditing:** Reconciling recorded project state against local disk is strictly read-only (`O_RDONLY`). Verification must never modify, delete, or create files on disk.
5. **Cryptographic Snapshot Sealing:** Memory checkpoints and handover packages are sealed with SHA-256 hashes computed over canonical state, ensuring tampering cannot go undetected.

---

## Package Architecture

```
core/python/
├── pyproject.toml              # Standalone package definition (zero external dependencies)
├── README.md                   # Core documentation
├── scs_core/                   # Pure headless domain library
│   ├── __init__.py             # Public API exports
│   ├── config.py               # Runtime environment configuration
│   ├── models.py               # Strict Pydantic domain models
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py         # ACID SQLite connection manager with WAL & migrations
│   │   └── schema.sql          # Canonical relational schema
│   ├── ipc/
│   │   ├── __init__.py
│   │   └── dispatcher.py       # Headless JSON-RPC 2.0 command dispatcher
│   └── modules/
│       ├── __init__.py
│       ├── scrubber.py                 # Secret & credential redaction
│       ├── caveman_context_validator.py# RFC-0004 causal extraction grammar parser
│       ├── caveman_engine.py           # Continuity chapter & handover package compiler
│       ├── mod02_protocol_engine.py    # Multi-session lifecycle orchestration
│       ├── mod03_approval_gate.py      # Human ratification & promotion gate
│       ├── mod04_decision_ledger.py    # Canonical architectural decisions & rejected options
│       ├── mod04_projects_sessions.py  # Session tracking & SHA-256 snapshot sealing
│       ├── mod05_checklist_engine.py   # Canonical checklist & task engine
│       ├── mod06_artifact_registry.py  # Canonical code & file artifact registry
│       └── mod07_reconciler.py         # O_RDONLY filesystem verifier
└── tests/                      # Comprehensive headless test suite (54 tests)
```

---

## Installation

### Requirements
- **Python:** >= 3.11
- **Dependencies:** None (standard library only)
- **Zero GUI / OS Dependencies:** Runs identically on Linux, macOS, and Windows.

```bash
pip install -e .
```

---

## Quickstart

```python
from pathlib import Path
from scs_core.db.database import VaultDatabase
from scs_core.modules.mod02_protocol_engine import ProtocolEngineService
from scs_core.modules.mod04_projects_sessions import ProjectSessionService
from scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from scs_core.modules.mod03_approval_gate import ApprovalGateService
from scs_core.modules.mod07_reconciler import ReadOnlyReconciler

# 1. Initialize SQLite Continuity Vault
db = VaultDatabase(Path("./data/scs_vault.db"))
proj_svc = ProjectSessionService(db)
dec_svc = DecisionLedgerService(db)
task_svc = ChecklistEngineService(db)
art_svc = ArtifactRegistryService(db)
appr_svc = ApprovalGateService(db, dec_svc, task_svc, art_svc)
recon_svc = ReadOnlyReconciler(db)

engine = ProtocolEngineService(
    db=db,
    project_svc=proj_svc,
    decision_svc=dec_svc,
    task_svc=task_svc,
    artifact_svc=art_svc,
    approval_svc=appr_svc,
    reconciler_svc=recon_svc,
)

# 2. Ingest raw conversation evidence (e.g. from ChatGPT or Claude session)
project = proj_svc.get_default_project()
raw_text = """
AI: We could use either PostgreSQL or SQLite for local storage. SQLite is serverless and zero-config.
Human: Proceed with SQLite migration.
AI: Agreed. We will implement SQLite with WAL mode.
"""
engine.add_chat_fragment(project_id=project.id, text=raw_text, source="PASTE")

# 3. Generate unsealed draft continuity chapter (Evidence -> Draft)
draft = engine.generate_continuity_md_draft(project.id)
print("Extracted draft chapter:", draft["chapter_code"])

# 4. Human approval gate: ratify intelligence into canonical memory & seal snapshot
approval_result = engine.approve_continuity_md_draft(
    project_id=project.id,
    approved_decision_ids=draft.get("detected_decision_ids", []),
)
print("Sealed Snapshot SHA-256:", approval_result["snapshot_hash"])

# 5. Export cryptographically sealed AI handover package
handover = engine.generate_handover_package(project.id)
print("Handover Package generated at:", handover["exported_file_path"])
```

---

## Verification & Testing

The core engine contains 62 comprehensive unit and conformance tests verifying human authority gates, causal grammar extraction, snapshot sealing, `O_RDONLY` reality reconciliation, and RFC-0006 normative test vector conformance:

```bash
# Run complete test suite (domain + RFC-0006 test vectors)
python -m unittest discover -s tests -v
```

All 62 tests run completely headless with in-memory or temporary SQLite databases.

---

## License

Licensed under the MIT License. See [LICENSE](../../LICENSE) for details.
