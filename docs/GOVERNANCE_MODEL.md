# SCS_AG_v2 Governance & Custody Model

**System:** Session Continuity Steward for Antigravity (SCS_AG_v2)  
**Document Version:** 1.0.0  
**Status:** APPROVED GOVERNANCE SPECIFICATION  
**Authority:** Stability Engineering & Product Validation  
**Reference ADRs:** ADR-001, ADR-002, ADR-005  

---

## 1. Executive Summary

The SCS_AG_v2 Governance Model establishes the formal rules, boundaries, and cryptographic verification mechanisms that ensure project memory remains **authoritative, tamper-evident, idempotent, and strictly under human control**.

Unlike conventional AI tools where agents silently mutate memory stores, SCS_AG_v2 enforces a strict separation of powers between **AI Extraction (Proposals)**, **Human Custody (Ratification)**, and **Machine State (Canonical Ledger)**.

---

## 2. The Three-Tier Memory Lifecycle

```
[ Tier 1: Raw Evidence ]      [ Tier 2: Staging Quarantine ]     [ Tier 3: Canonical SSOT ]
    SES*.md (Immutable)     ──►    pending_proposals.json     ──►      ledger.json (Sealed)
(Permanent Forensic Log)         (Unverified AI Extraction)           (Ratified Truth)
                                            │
                                            ▼
                               [ Human Operator Review ]
                                  - /scs approve (Promote)
                                  - /scs reject  (Discard)
```

### Tier 1: Forensic Raw Evidence (`evidence/raw_sessions/SES*.md`)
- Capture is additive and strictly append-only.
- Verbatim developer-AI dialogue turns are recorded with step indices and timestamps.
- Every file has a YAML frontmatter header containing a SHA-256 body checksum.
- Raw files are never mutated, re-written, or deleted.

### Tier 2: Staging Quarantine Gate (`staging/pending_proposals.json`)
- AI context extraction heuristics parse dialogue and generate candidate proposals (`DECISION`, `CONSTRAINT`, `TASK`, `ARTIFACT`, `REJECTED_OPTION`).
- Candidate proposals have **zero authority**. They cannot be referenced by cold-start AI agents as canonical constraints.
- Proposals reside in quarantine until a human operator acts upon them.

### Tier 3: Canonical Machine SSOT (`canonical/ledger.json`)
- The single source of truth for all ratified project state, conforming to `scs-ledger/1.0`.
- Only modified when an operator executes `scs approve` or rolls back to a sealed snapshot.
- Cryptographically sealed with SHA-256 into `snapshots/SNP-*.json`.

---

## 3. Human Custody Gate Protocols

### 3.1 Operator Custody Actions
The human operator is the sole authority permitted to promote or discard staged proposals:

1. **Inspection (`scs status`):** Displays all pending items awaiting approval, alongside cryptographic seal status and task completion progress.
2. **Promotion (`scs approve`):**
   - Validates candidate items against quality invariants.
   - Idempotently updates or appends to `canonical/ledger.json`.
   - Computes a new SHA-256 state seal and creates a numbered snapshot (`SNP-YYYYMMDD-NNN.json`).
   - Regenerates all one-way Markdown projections (`DECISIONS.md`, `TASKS.md`, etc.).
   - Clears promoted items from `staging/pending_proposals.json`.
3. **Discard / Rejection (`scs reject <ID>`):**
   - Discards operational noise, report fragments, and false extractions.
   - Removed from `staging/pending_proposals.json` without canonical memory mutation.
   - Optionally records the rejection into `canonical/REJECTED_OPTIONS.md` if the operator explicitly intended to ban the proposed alternative.

---

## 4. Cryptographic State Sealing & Tamper Detection

### 4.1 Deterministic State Hashing
Every snapshot seal is computed using standard library Python `hashlib.sha256`:

$$\text{Seal} = \text{SHA-256}\Big(\text{JSON\_Encode}\big(\text{ledger}, \text{sort\_keys}=\text{True}, \text{indent}=2\big)\Big)$$

- The resulting 64-character hexadecimal digest is stored in `snapshots/SNP-{YYYYMMDD}-{NNN}.json`.
- The active seal string is mirrored in `snapshots/LATEST_SEAL`.

### 4.2 Tamper Sensitivity ($O(1)$ Verification)
When `/scs status` or `/scs handover` is invoked:
1. `vault_store.verify_seal()` reads `canonical/ledger.json`.
2. Computes the current SHA-256 hash.
3. Compares the hash with `snapshots/LATEST_SEAL`.
4. If a single byte, space, or newline has been modified out-of-band:
   - Output immediately warns: `[SEAL BROKEN]`
   - Handover package generation halts or flags the discrepancy.

---

## 5. Machine SSOT vs. Presentation Projections

| Attribute | Canonical SSOT (`canonical/ledger.json`) | Presentation Projections (`canonical/*.md`) |
| :--- | :--- | :--- |
| **Format** | Strictly formatted JSON (`scs-ledger/1.0`) | GitHub-flavored Markdown |
| **Authority** | **Sole Machine Authority** | Disposable presentation view |
| **Parser Direction**| Memory ➔ JSON ➔ Seal | JSON ➔ Markdown (ONE-WAY ONLY) |
| **Reverse Parsing** | N/A | **STRICTLY PROHIBITED** |
| **Regeneration** | Sealed incrementally via `scs approve` | Re-rendered in milliseconds from JSON |

---

## 6. The Authoritative Do-Not-Repeat Registry

To permanently defeat the "Groundhog Day" anti-pattern, SCS_AG_v2 maintains an explicit **Do-Not-Repeat Registry** (`canonical/REJECTED_OPTIONS.md`).

### Structure of Negative Knowledge
Every entry in the registry contains:
- **Code:** Unique identifier (`REJ-001`, `REJ-002`, etc.).
- **Alternative Statement:** What technology, architecture, or pattern was considered.
- **Why Rejected:** Specific engineering failure mode, cost trade-off, or risk that caused rejection.
- **Source Session:** Forensic link back to the exact dialogue session where the alternative was evaluated.

### Anti-Inversion Safeguards
The extraction adapter enforces strict invariants before allowing an item into the Do-Not-Repeat registry:
- **Capability Protection:** Built-in SCS features (e.g., Do-Not-Repeat memory, staging quarantine, file-first storage) can never be classified as rejected options.
- **Generic Word Rejection:** Words such as `"noise"`, `"status"`, or conversational fragments cannot become negative knowledge.
