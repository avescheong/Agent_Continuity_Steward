# Agent Continuity Steward (SCS) — Formal Post-GA Defect Assessment

**Document ID:** DOC-SCS-POST-GA-DEFECTS-001  
**Document Status:** FORMAL POST-GA ASSESSMENT (CONFIRMED)  
**Publication Target:** `v1.0.0` General Availability (`319699738abc5b5020c7cd52883e9fc52a4933b7`)  
**Assessment Date:** 2026-11-06  
**Evaluator:** Product Architecture & Stability Engineering  
**Authority:** Architectural Governance & Quality Assurance  

---

## 1. Executive Summary

During Phase 11 Step 11.1 operational validation of the published **Agent Continuity Steward v1.0.0** release, independent testing was executed in a pristine, isolated Python 3.13 virtual environment (`--no-site-packages`) simulating an external third-party consumer pulling the repository directly from GitHub.

Two critical defects were discovered that impact the zero-configuration installation experience of external users. Both defects have been verified, replicated, and formally cataloged.

In accordance with strict post-GA governance rules, **the v1.0.0 release repository remains immutable**. No emergency hotfixes or direct commits will be made to the `main` branch. All remediations are deferred to a planned `v1.0.1` maintenance patch release following complete Phase 11 validation.

---

## 2. Defect Specifications

### Defect POST-GA-001: Undeclared Runtime Dependency on Pydantic

- **Defect ID:** `POST-GA-001`
- **Severity:** **P1 (Critical Defect — Launch Blocker in Isolated Environments)**
- **Category:** Runtime Dependency Declaration / Packaging Metadata
- **Affected Components:** `pyproject.toml`, `docs/QUICKSTART.md`, `core/python/scs_core/models.py`
- **Discovered In:** Step 11.1 (Clean-room virtual environment audit)

#### Observed Behavior
When an external developer creates a standard Python virtual environment (`python -m venv .venv`) and installs SCS following the official `QUICKSTART.md` guide (`pip install -e .`), launching the tool via `scs --help` or `python -m engine.scs_cli --help` immediately crashes with an unhandled exception:

```text
Traceback (most recent call last):
  File ".../Agent_Continuity_Steward/core/python/scs_core/models.py", line 7, in <module>
    from pydantic import BaseModel, Field
ModuleNotFoundError: No module named 'pydantic'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File ".../scs.exe/__main__.py", line 2, in <module>
    from engine.scs_cli import main
  File ".../engine/scs_cli.py", line 30, in <module>
    import core_adapter
  File ".../engine/core_adapter.py", line 73, in <module>
    raise ImportError(
    ...
    ) from exc
ImportError: Failed to import upstream scs_core from '.../core/python'. Verify that core/python exists and contains the scs_core package.
```

#### Root Cause Analysis
1. In `core/python/scs_core/models.py`, domain models and DTOs inherit from Pydantic `BaseModel` (`from pydantic import BaseModel, Field`).
2. The root packaging manifest (`pyproject.toml`) declared:
   ```toml
   [project]
   dependencies = []
   ```
   and `docs/QUICKSTART.md` stated:
   > *"Dependencies: Zero external packages required. SCS_AG_v2 uses only the Python standard library."*
3. During prior R&D phases (Phases 1 through 10), release verification scripts (`scripts/verify_release.py`) were executed in the developer's host Python environment, where `pydantic` was present in the user-level site-packages directory (`%APPDATA%\Python\Python313\site-packages`). Because Python automatically loads user-site packages unless explicitly sandboxed, the dependency absence was masked until tested in an isolated virtual environment (`include-system-site-packages = false`).

#### Impact
External users installing v1.0.0 in clean virtual environments or containers without `pydantic` pre-installed cannot execute the CLI without manual intervention.

---

### Defect POST-GA-002: Package Distribution Layout Disconnect in Built Wheels

- **Defect ID:** `POST-GA-002`
- **Severity:** **P1 (Critical Defect — Distribution Packaging)**
- **Category:** Package Distribution Layout / Module Resolution
- **Affected Components:** `pyproject.toml`, `engine/core_adapter.py`
- **Discovered In:** Step 11.1 (Remote `pip install git+https://...` audit)

#### Observed Behavior
When an external developer installs SCS directly from GitHub using standard pip syntax:
```bash
pip install "git+https://github.com/avescheong/Agent_Continuity_Steward.git@v1.0.0"
```
Pip clones the repository, successfully builds a standard Python wheel (`agent_continuity_steward-1.0.0-py3-none-any.whl`), and installs the package with exit code 0. However, executing `scs --help` immediately fails with:

```text
Traceback (most recent call last):
  File ".../site-packages/engine/core_adapter.py", line 45, in <module>
    import scs_core
ModuleNotFoundError: No module named 'scs_core'
...
ImportError: Failed to import upstream scs_core from '.../site-packages/core/python'. Verify that core/python exists and contains the scs_core package.
```

#### Root Cause Analysis
1. `pyproject.toml` declares package discovery as:
   ```toml
   [tool.setuptools.packages.find]
   where = ["."]
   include = ["engine*", "src*"]
   ```
2. When building a wheel, setuptools packages `engine/` and `src/` (placing them at `site-packages/engine` and `site-packages/src`).
3. `core/python/` (which contains upstream reference `scs_core`) is omitted from the wheel because it is not included in `packages.find`.
4. While `src/scs_core` is packaged inside `site-packages/src/scs_core`, `core_adapter.py` lines 30–45 execute `import scs_core` directly and search only `REPO_ROOT / "core" / "python"`. Since `site-packages/src` is not added to Python's `sys.path`, Python cannot locate `scs_core`.

#### Impact
External developers attempting standard non-editable wheel installations directly from the GitHub URL cannot execute `scs` without manually setting `$env:SCS_CORE_PYTHON_PATH`.

---

### Defect POST-GA-003: Incorrect CLI Syntax Documented for Rollback Command

- **Defect ID:** `POST-GA-003`
- **Severity:** **P2 (Ergonomic / Usability Defect)**
- **Category:** Documentation Accuracy / Argument Parsing
- **Affected Components:** `docs/QUICKSTART.md` (Section 5), `engine/scs_cli.py`
- **Discovered In:** Step 11.2 (Verbatim QUICKSTART execution)

#### Observed Behavior
Section 5 of `docs/QUICKSTART.md` instructs users to roll back to a prior snapshot using:
```bash
python -m engine.scs_cli rollback --snapshot SNP-20261105-001 --project PAY
```
Executing this command causes `argparse` to immediately reject the call:
```text
usage: scs rollback [-h] [--project PROJECT] [--conv-id CONV_ID] snapshot_code
scs: error: unrecognized arguments: --snapshot
```

#### Root Cause Analysis
In `engine/scs_cli.py`, `snapshot_code` is configured as a required positional argument:
```python
sub_rb.add_argument("snapshot_code", help="Snapshot code to restore (e.g. SNP-20261105-001)")
```
The documentation mistakenly prefixed the snapshot code with an unrecognized `--snapshot` flag.

#### Impact
External users attempting to test rollback per the guide receive an immediate command error.

#### Workaround
Pass `snapshot_code` positionally without the `--snapshot` flag:
```powershell
python -m engine.scs_cli rollback SNP-20261106-001 --project PAY
```

---

### Defect POST-GA-004: Release Verification Banner Output Discrepancy

- **Defect ID:** `POST-GA-004`
- **Severity:** **P3 (Minor / Cosmetic Defect)**
- **Category:** Documentation Fidelity
- **Affected Components:** `docs/QUICKSTART.md` (Section 2)
- **Discovered In:** Step 11.2 (Verbatim QUICKSTART execution)

#### Observed Behavior
`docs/QUICKSTART.md` displays sample output using emoji banner:
`🧭 SCS_AG_v2 Release Verification Suite`
Whereas `scripts/verify_release.py` outputs:
`[SCS_AG_v2] PRODUCTION RELEASE VERIFICATION SUITE`

#### Impact
Cosmetic inconsistency between documentation preview and actual terminal output.

---

## 3. Governance Decisions

In accordance with strict post-GA change management policies:

1. **v1.0.0 Immutability:** The published GitHub repository (`https://github.com/avescheong/Agent_Continuity_Steward`), the `main` branch, and the annotated tag `v1.0.0` (`76b8a737e7d6a2d5379bd206c7ab1247c27c3c34`) remain permanently frozen and immutable.
2. **Zero Hotfixes to Main:** No emergency commits or force pushes will be executed on `main`.
3. **Formal Branching for Remediation:** All fixes for `POST-GA-001` and `POST-GA-002` must be developed on an isolated maintenance branch (`dev/v1.0.1` or `fix/v1.0.1-packaging-dependencies`) branched directly from `v1.0.0`.
4. **Validation Sequencing:** Phase 11 operational validation (Steps 11.2 through 11.5) will continue using the documented v1.0.0 workarounds so that all potential post-GA usability and ergonomic findings are surfaced and remediated collectively in `v1.0.1`.

---

## 4. Current Operational Workaround Guide for v1.0.0

For developers currently evaluating or dogfooding v1.0.0 before the release of v1.0.1, the following workarounds guarantee 100% functionality:

### Workaround A: Recommended Source Installation (Verbatim Quickstart)
```powershell
# 1. Clone repository from GitHub
git clone https://github.com/avescheong/Agent_Continuity_Steward.git
cd Agent_Continuity_Steward

# 2. Install editable CLI
pip install -e .

# 3. Install runtime dependency
pip install pydantic
```
- **Result:** `scs --help` and all 10 subcommands function with zero errors in $< 0.15\text{s}$.

### Workaround B: Test Suite Conformance in Clean Virtualenv
To run `python scripts/verify_release.py` in an isolated virtual environment:
```powershell
pip install pydantic starlette httpx
python scripts/verify_release.py
```
- **Result:** **124/124 tests passing (100% conformance)** in under 5.0 seconds.

### Workaround C: Non-Editable Wheel Installation
```powershell
pip install "git+https://github.com/avescheong/Agent_Continuity_Steward.git@v1.0.0"
pip install pydantic
$env:SCS_CORE_PYTHON_PATH = (python -c "import site; print(site.getsitepackages()[0] + '/src')")
```
- **Result:** CLI resolves `scs_core` and executes cleanly.

---

## 5. Next Steps

1. Review and ratify `V1_0_1_REMEDIATION_PLAN.md`.
2. Resume Phase 11 Post-GA Operational Validation under the documented Workaround A.
3. Consolidate all Phase 11 findings into `PHASE_11_POST_GA_VALIDATION_REPORT.md`.
4. Branch `dev/v1.0.1` and execute remediation after formal authorization.
