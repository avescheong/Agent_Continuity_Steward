# SCS_AG_v2 Design Philosophy & Core Architectural Choices

**System:** Session Continuity Steward for Antigravity (SCS_AG_v2)  
**Document Version:** 1.0.0  
**Status:** PUBLISHED ENGINEERING RATIONALE  
**Authority:** Stability Engineering & Product Validation  
**Reference ADRs:** ADR-001 through ADR-008  

---

## 1. The Foundational Problem: AI Session Amnesia

Every software developer working with Large Language Models (LLMs) encounters **Session Amnesia**:

1. **Context Window Limits:** Conversations cannot grow indefinitely. When context windows fill up, conversations are truncated, compacted, or restarted.
2. **Loss of Causal Memory:** When a new session starts, the AI retains no memory of *why* choices were made. It cannot distinguish between an option that was never considered and an option that was evaluated, tested, and rejected.
3. **The Groundhog Day Anti-Pattern:** A fresh AI session repeatedly suggests previously discarded architectures (e.g., "Let's add PostgreSQL and Redis!") because it lacks negative knowledge.
4. **Capability Inversions:** Naive LLM summarizers frequently invert statements—turning descriptions of existing features into things to avoid, or misinterpreting constraints.
5. **Manual Copy-Paste Toil:** Developers resort to manually maintaining markdown files, copying summaries back and forth, losing versioning, and introducing human error.

SCS_AG_v2 was conceived not as another LLM chat wrapper, but as a **forensic continuity steward** that gives AI development the rigorous memory and causal continuity expected in safety-critical systems engineering.

---

## 2. Why Evidence-First Continuity is Required

Most memory tools treat memory as an ephemeral database of embeddings or summaries. SCS_AG_v2 is grounded in the **Evidence-First Principle**:

> **"If an architectural claim cannot be traced to immutable raw evidence, it is an unverified hallucination."**

- **Forensic Backbone:** Every recorded session produces an immutable, write-once Markdown file (`SES*.md`) containing the verbatim conversation text, step indices, turn counts, and a SHA-256 body hash.
- **Auditable Provenance:** Every decision in the canonical ledger links back to its `source_session_code` and an `evidence_quote`.
- **Permanent Audit Trail:** Even when sessions are consolidated into 10-session chapters (`MD*.md`), the raw `SES*.md` files are **never deleted or modified**.

---

## 3. Why the Human Custody Gate is Mandatory

A common design temptation in AI tools is "fully autonomous self-updating memory." In SCS_AG_v2, **autonomous canonical mutation is strictly rejected**.

### The Danger of Auto-Mutation
In real-world dogfooding (e.g., `DFG-006` and `DFG-007`), the LLM extracted operational checklist items (`- [x] Memory Integrity verified...`) from progress reports as candidate tasks. If the system had automatically mutated its ledger, the canonical task list would have been contaminated with dozens of ephemeral conversational report fragments.

### The Staging Quarantine Boundary (ADR-001)
- All AI extractions are quarantined in `staging/pending_proposals.json`.
- Candidate proposals have **zero authority** and cannot mutate the machine SSOT.
- The human operator reviews proposals via `/scs status` and explicitly promotes them via `/scs approve`.
- The operator discards conversational noise via `/scs reject`, keeping canonical memory pristine.

---

## 4. Why Markdown is Projection Only (Zero Reverse-Parsing)

Many developer tools attempt to use Markdown files as the database—reading markdown tables, parsing headings, and updating them in place. SCS_AG_v2 strictly forbids this:

```
[ canonical/ledger.json ] ──(One-Way Deterministic Render)──► [ Markdown Projections ]
     (Machine SSOT)                                               - DECISIONS.md
                                                                 - TASKS.md
                                                                 - REJECTED_OPTIONS.md
                                                                 - ARTIFACTS.md
```

1. **Markdown is Ambiguous:** Markdown syntax is designed for human presentation, not structured machine serialization. Formatting variations, list indentation, and emojis easily break regex and AST parsers.
2. **Reverse-Parsing Causes Hallucination & Drift:** Reading Markdown back into data structures inevitably corrupts whitespace, drops metadata fields, and causes cumulative state drift across sessions.
3. **Machine SSOT Authority:** `canonical/ledger.json` (conforming to `scs-ledger/1.0`) is the sole machine authority. It is serialized deterministically with sorted keys and sealed with SHA-256. Markdown files are disposable projections that can be blown away and regenerated in milliseconds without data loss.

---

## 5. Why SQLite, Background Daemons, and Auto-Triggers Were Rejected

During Phase 1 architecture exploration, three tempting features were evaluated and **formally rejected** in the foundational ADRs:

### A. Rejected: Direct SQLite Database Without Staging (ADR-001 / REJ-001)
- **Why Rejected:** Binary SQLite databases hide state from human inspection, cannot be diffed easily in Git, risk silent file lock corruption, and bypass the visual human custody boundary. Flat JSON files provide complete transparency, instant diffability, and zero corruption risk.

### B. Rejected: Background Daemons & Real-Time File Watchers (ADR-002)
- **Why Rejected:** Background daemon processes crash silently, drain laptop battery, introduce threading race conditions, and require complex PID/service management. SCS_AG_v2 operates with **strictly synchronous, zero-daemon execution**. Commands run on demand, complete in under 0.5 seconds, and terminate cleanly.

### C. Rejected: Automatic Checkpointing Without Human Review (REJ-004)
- **Why Rejected:** Automatic checkpointing removes human accountability, permits hallucinated propositions to become permanent architectural constraints, and leads to rapid context pollution.

---

## 6. How Dogfooding Transformed the System

SCS_AG_v2 was not designed in an ivory tower; it was dogfooded upon itself from Day 1:

1. **DFG-001 (Extraction Hardening):** Pre-hardening Caveman heuristics collapsed 10 decisions into `"Adopt count"` and inverted features into rejected options. Real dogfooding prompted the creation of Phase 1.6 Hardening, raising the rehydration score from 6.2/10 to 9.3/10.
2. **DFG-003 (Idempotent Deduplication):** Dogfooding caught duplicate artifact references in `staging/`, leading to the implementation of idempotent reconciliation in `promote_proposals()` that guarantees zero duplicate accumulation mathematically.
3. **DFG-004 (Resilient Path Resolution):** Real-world test runs revealed physical artifact reconciliation failures (4/27 verified). Resilient path scanning expanded resolution to 22/27 immediately and 26/32 today.
4. **DFG-005 (Independent AI Audit):** A blind audit by an independent subagent scored the system at **9.7 / 10.0**, identifying subtle verb duplications (`"Use Read..."`) that were surgically fixed in the adapter layer.
5. **DFG-008 (Negative Knowledge Protection):** Conversational discussion containing words like `"Noise"` was falsely classified as a rejected option. Hardened regex and token validators completely blocked generic word pollution while preserving technical alternatives like `PostgreSQL` and `Kafka`.

---

## 7. Conclusion: The Sovereign Invariants

SCS_AG_v2 stands on five non-negotiable pillars:
1. **Machine Authority:** `ledger.json` is the sole machine truth.
2. **Forensic Immutability:** Raw evidence is never deleted or altered.
3. **Human Custody:** AI proposes; humans ratify.
4. **Deterministic Sealing:** Every snapshot is cryptographically hashed with SHA-256.
5. **Zero-Daemon Simplicity:** Sub-second Python execution without background daemons.
