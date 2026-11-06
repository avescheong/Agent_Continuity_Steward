# SCS_AG_v2 Security Model & Threat Assessment

**System:** Session Continuity Steward for Antigravity (SCS_AG_v2)  
**Document Version:** 1.0.0  
**Status:** APPROVED SECURITY SPECIFICATION  
**Authority:** Stability Engineering & Product Validation  
**Threat Model Standards:** STRIDE / Principle of Least Privilege  

---

## 1. Executive Summary

SCS_AG_v2 is engineered for **secure, zero-trust, air-gapped developer environments**. Because continuity stewards ingest and process developer dialogue that may inadvertently contain credentials, intellectual property, or confidential system details, the security model is built around **fail-closed isolation, automated credential redaction, and zero network attack surface**.

---

## 2. Threat Analysis & Mitigations (STRIDE Matrix)

| Threat Category | Potential Risk | SCS_AG_v2 Architectural Mitigation |
| :--- | :--- | :--- |
| **Spoofing** | Forging or tampering with continuity snapshots | **Deterministic SHA-256 State Sealing:** Every snapshot is hashed. Single-byte tampering breaks the seal immediately. |
| **Tampering** | In-flight corruption or unauthorized editing of decisions | **Immutable Raw Evidence:** `SES*.md` files are write-once append-only. Markdown files are disposable one-way projections. |
| **Repudiation** | Disputing who authorized an architectural change | **Mandatory Human Custody:** AI proposals cannot self-promote. State changes require explicit human CLI action (`scs approve`). |
| **Information Disclosure** | Accidental leakage of API keys, JWTs, or passwords | **Pre-Extraction Secret Scrubber:** Regex scrubber redacts API keys, bearer tokens, private keys, and passwords before evidence write. |
| **Denial of Service** | Process crashes, runaway loops, or resource exhaustion | **Zero-Daemon Architecture:** No background daemon threads or file watchers. Synchronous execution terminates in $<0.5$s. |
| **Elevation of Privilege** | Arbitrary file system writes or path traversal | **Path Traversal Defense:** `ReadOnlyReconciler` verifies paths and strictly blocks traversal (`../`) out of configured roots. |

---

## 3. Core Security Features

### 3.1 Automated Secret Scrubber (`core_adapter.scrub_secrets`)
Before any dialogue turn is written to raw session evidence (`SES*.md`) or parsed by extraction heuristics, it passes through the multi-pattern secret scrubber:
- **API Keys:** OpenAI (`sk-...`), Anthropic (`sk-ant-...`), Google Gemini (`AIza...`), AWS Access Keys (`AKIA...`).
- **Authentication Tokens:** Bearer JWT tokens, GitHub personal access tokens (`ghp_...`, `github_pat_...`), Slack tokens.
- **Private Keys & Certificates:** RSA/EC private key blocks (`-----BEGIN PRIVATE KEY-----`).
- **Generic Passwords:** Key-value patterns matching `password = ...`, `secret = ...`, `api_key = ...`.
- Redacted strings are safely replaced with standard placeholders (e.g., `[REDACTED_API_KEY]`).

Verified by automated regression test `test_adapter_verification.test_scrub_secrets`.

### 3.2 Path Traversal & Air-Gap Defense
When reconciling physical artifacts across project roots:
- All target paths are converted to absolute paths and normalized via `Path.resolve()`.
- The system asserts that the resolved path resides within either the configured `root_paths` or the authorized `vault_dir`.
- Traversal sequences (e.g. `../../etc/passwd` or `..\..\Windows\System32`) raise immediate traversal violations and are blocked.

Verified by automated regression test `test_reconciler_readonly.test_path_traversal_blocked`.

### 3.3 Zero Attack Surface: No Network, No Ports, No Daemons
- **Zero Open Sockets:** The system opens **0** TCP/UDP listening ports.
- **Zero Background Daemons:** The engine contains no background daemons, cron listeners, or IPC servers in standard CLI mode.
- **Zero Third-Party Telemetry:** No metrics, telemetry, or dialogue text are transmitted over the internet.
- **Air-Gapped Operation:** Functions 100% offline without internet connectivity.

### 3.4 Centralized Vault Separation (Leakage Prevention)
Storing raw conversation transcripts and developer logs inside git repositories is a major source of accidental credential leakage to public remotes.
- SCS_AG_v2 mandates **Centralized Vault Separation (ADR-005)**: vaults reside in a dedicated local directory (`~/My_Project_Continuity/<PROJECT>`), physically decoupled from git source code trees.
- Application repositories remain clean, avoiding unintended public git pushes of dialogue history.
