# SCS Reference Core Engine (`core/`)

This directory houses the headless reference implementations of the Session Continuity Steward architecture.

---

## 🏗️ Implementations

- **`core/python/`**: The primary reference implementation (`scs-core` package).
  - Implements the complete dual ledger data model on SQLite 3 WAL.
  - Implements the Causal Extraction Protocol (CEP) with the default `caveman` high-efficiency profile.
  - Implements the `O_RDONLY` physical artifact custody reconciler.
  - Packaged for PyPI with zero GUI, zero Win32, and zero OS-specific dependencies.
- **`core/rust/` (Future Roadmap Target)**: High-performance native implementation targeting sub-25MB memory footprint and standalone binary distribution.

---

## Guiding Rule

Reference engines in `core/` contain **zero UI code**. They expose clean, typed programmatic interfaces and CLI dispatchers that client applications consume.
