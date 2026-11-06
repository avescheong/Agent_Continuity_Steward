# SCS Normative Conformance Test Suite (`test-vectors/`)

This directory contains language-agnostic test vectors used to certify that an implementation strictly conforms to the SCS specification.

---

## Directory Structure

- **`multi_turn_scenarios/`**: Raw conversational transcripts (`.txt`, `.md`) capturing complex multi-turn developer-AI dialogues.
- **`expected_extraction/`**: Canonical JSON fixture files specifying the exact expected outputs:
  - Classified Conversation Acts (`PROPOSAL`, `DISCUSSION`, `AGREEMENT`, `REJECTION`, `REVERSAL`, `DIRECT_DECISION`).
  - Extracted Decisions with full causal rationale.
  - Extracted Constraints with semantic subsumption applied.
  - Rejected Options with recorded rationale.
  - Tasks and referenced physical artifacts.
- **`conflict_scenarios/`**: Test dialogues introducing mutually exclusive propositions (e.g. offline execution vs cloud services) designed to test fail-closed contradiction detection.

---

## Conformance Certification

Any engine claiming SCS compliance (whether written in Python, Rust, Go, or TypeScript) must execute against these test fixtures and achieve **100% semantic agreement**.
