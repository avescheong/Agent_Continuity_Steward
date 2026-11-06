# SCS Windows Portable Package Smoke-Test Regression Checklist

**Document ID:** `REG-SMOKE-WIN-LAUNCHER-01`  
**Target Environment:** Windows 10 / Windows 11 (64-bit)  
**Target Package:** `dist/SCS-HUD-v<VERSION>-Windows.zip`  
**Scope Classification:** Delivery-Layer Release Engineering & End-User Experience  
**Governance Authority:** Delivery validation only. Does **NOT** modify `scs-core` architecture, database schemas, or RFC normative specifications.

---

## 1. Objective and Release Governance

The purpose of this smoke-test checklist is to certify that portable Windows release distributions of Session Continuity Steward (SCS-HUD) function flawlessly on clean, non-developer end-user systems.

### Primary Goals
1. **Prevent Batch Syntax Regressions:** Guard against Windows Command Prompt (`cmd.exe`) syntax parsing errors, parenthetical sub-shell collisions, and unescaped shell operator bugs.
2. **Ensure Whitespace Resilience:** Verify that extraction paths containing spaces (e.g., `C:\Program Files\...` or `C:\Users\John Doe\...`) do not break batch argument quoting or Python path resolutions.
3. **Verify Clean Desktop Launch:** Ensure that non-technical users can double-click launcher batch files and experience zero console error flashes, instant process launch, and clean WebView2 UI initialization.

> [!IMPORTANT]
> **Strict Release Gate:**  
> This checklist must be manually executed and passed **100%** on every candidate ZIP archive before creating git release tags, uploading GitHub release assets, or distributing packages to end users. Any failure in this checklist blocks release publication immediately.

---

## 2. Windows Batch Syntax & Launcher Invariants

Historical release audits revealed specific pitfalls in Windows `cmd.exe` batch script parsing. All portable launcher scripts (`START_SCS_HUD.bat`, `START_SCS_HUD_DEBUG.bat`, `CHECK_SYSTEM.bat`) must strictly uphold the following syntactic invariants:

### Invariant 1: Linear Label-Based Control Flow (No Parenthetical Collisions)
* **Problem:** In `cmd.exe`, multi-line parenthetical blocks `if (...) else (...)` or `for (...)` parse closing parentheses `)` literally at block read time. Any child statement containing an echo with parentheses or trailing dots (e.g. `echo Checking (fallback)...`) closes the block prematurely and triggers:
  ```text
  ... was unexpected at this time.
  ```
* **Rule:** Never wrap multi-line script logic inside `if (...)` blocks when user-facing `echo` statements contain parentheses or dots. Always use linear label-based control flow with explicit `goto` statements:
  ```batch
  if not "%FOUND%"=="1" goto :PYTHON_NOT_FOUND
  ...
  goto :CONTINUE
  :PYTHON_NOT_FOUND
  echo Python not found.
  pause
  exit /b 1
  :CONTINUE
  ```

### Invariant 2: Strict Path Quoting for Whitespace Safety
* **Problem:** If a user extracts SCS into a directory containing spaces (e.g. `C:\SCS TEST WITH SPACES` or `C:\Users\User Name\Downloads`), unquoted path variables expand into multiple tokens, causing:
  ```text
  'C:\SCS' is not recognized as an internal or external command
  ```
* **Rule:** All file and script references must be strictly enclosed in double quotes:
  ```batch
  "%PYTHON_EXE%" "%~dp0run_hud.pyw"
  "%PYTHON_EXE%" "%~dp0run_hud.py" --debug
  "%PYTHON_EXE%" "%~dp0run_hud.py" --check
  ```

### Invariant 3: Zero Unescaped Ampersands in Output
* **Problem:** The ampersand `&` is a command separator in `cmd.exe`. Writing `echo SCS-HUD Diagnostic & Health Check` causes `cmd.exe` to attempt to run `Health` as a command, throwing:
  ```text
  'Health' is not recognized as an internal or external command
  ```
* **Rule:** Never use bare `&` in titles or echo lines. Use `and` or escaped caret `^&`.

### Invariant 4: Functional Interpreter Discovery
* **Problem:** Windows Store stubs (`python.exe` 0-byte redirection links) report `where python` success even if Python is uninstalled, redirecting unsuspecting users to the Microsoft Store.
* **Rule:** Always execute a lightweight test command to verify that Python actually runs before attempting to launch the HUD:
  ```batch
  "%PYTHON_EXE%" -c "import sys; sys.exit(0)" >nul 2>&1
  if errorlevel 1 goto :PYTHON_NOT_FOUND
  ```

---

## 3. Mandatory Test Matrix

Before any public release, the candidate ZIP package must be verified against two distinct target directories on a representative Windows machine:

| Environment ID | Target Directory Path | Validation Focus |
| :--- | :--- | :--- |
| **ENV-A** (Standard Path) | `C:\SCS_TEST_INSTALL` | Clean baseline installation without spaces, standard permissions |
| **ENV-B** (Whitespace Path) | `C:\SCS TEST WITH SPACES` | Space resilience, argument quoting, deep module imports |

---

## 4. Step-by-Step Smoke Test Execution Protocol

Follow these sequential steps exactly using the candidate distribution ZIP (`dist/SCS-HUD-v*-Windows.zip`).

### Step 1: Build & Package Verification
In the repository root:
1. Rebuild the portable distribution package:
   ```powershell
   python scripts/package_release.py
   ```
2. Run the automated integrity and checksum audit:
   ```powershell
   python scripts/verify_release_package.py
   ```
   *Expected Result:* All 5 automated verification checks report `[PASS]`.

---

### Step 2: Environment A Validation (`C:\SCS_TEST_INSTALL`)

1. **Extract ZIP:**
   Extract `dist/SCS-HUD-*-Windows.zip` into `C:\SCS_TEST_INSTALL`.
   ```powershell
   if (Test-Path "C:\SCS_TEST_INSTALL") { Remove-Item -Recurse -Force "C:\SCS_TEST_INSTALL" }
   New-Item -ItemType Directory -Path "C:\SCS_TEST_INSTALL" -Force | Out-Null
   Expand-Archive -Path "dist\SCS-HUD-v0.5.0-RC-Windows.zip" -DestinationPath "C:\SCS_TEST_INSTALL"
   ```

2. **Verify Directory Contents:**
   Navigate into the extracted folder (e.g. `C:\SCS_TEST_INSTALL\SCS-HUD-v0.5.0-RC-Windows`).
   Confirm the presence of:
   - `START_SCS_HUD.bat`
   - `START_SCS_HUD_DEBUG.bat`
   - `CHECK_SYSTEM.bat`
   - `run_hud.py`
   - `run_hud.pyw`
   - `docs/user/SCS-HUD_USER_MANUAL.pdf`
   - `sample_workspace/`

3. **Run `CHECK_SYSTEM.bat`:**
   Double-click `CHECK_SYSTEM.bat` (or run in `cmd.exe`).
   * **Visual Check:** Confirm no `... was unexpected` or `'...' is not recognized` syntax errors appear.
   * **Output Verification:** Confirm all 4 diagnostic phases report `[PASS]`:
     1. Python Interpreter Detection
     2. Python Standard and Core Dependencies
     3. SCS Local Workspace and Schema Initialization
     4. Microsoft Edge WebView2 Runtime Availability
   * **Summary Check:** Output displays `[OK] All system checks passed!` and returns exit code `0`.

4. **Run `START_SCS_HUD_DEBUG.bat`:**
   Double-click `START_SCS_HUD_DEBUG.bat`.
   * **Console Check:** Console window opens and remains visible with clean logs.
   * **Diagnostic Log:** Confirm server binds to `127.0.0.1:27124`.
   * **UI Check:** The native HUD window opens on the desktop.
   * Close the HUD window to terminate the test session.

5. **Run `START_SCS_HUD.bat` (Primary User Launcher):**
   Double-click `START_SCS_HUD.bat`.
   * **Process Check:** `pythonw.exe` starts silently in the background.
   * **Console Check:** No persistent or orphaned black command prompt window remains open.
   * **UI Check:** The SCS-HUD WebView2 window appears within 2–4 seconds.
   * **HUD Operational State:**
     - Header displays version: `v0.5.0-RC` (or active release version).
     - Daemon status indicator is green: `CONNECTED`.
     - Ledger status indicator is green: `HEALTHY`.
     - Interactive tabs ("Real-time HUD", "Active Workspace", "Continuity Ledger", "System Diagnostics") switch cleanly.
   * Close the HUD window and verify process termination (`taskkill /F /IM pythonw.exe` if running background daemon).

---

### Step 3: Environment B Validation (`C:\SCS TEST WITH SPACES`)

1. **Extract ZIP:**
   Extract `dist/SCS-HUD-*-Windows.zip` into `C:\SCS TEST WITH SPACES`.
   ```powershell
   if (Test-Path "C:\SCS TEST WITH SPACES") { Remove-Item -Recurse -Force "C:\SCS TEST WITH SPACES" }
   New-Item -ItemType Directory -Path "C:\SCS TEST WITH SPACES" -Force | Out-Null
   Expand-Archive -Path "dist\SCS-HUD-v0.5.0-RC-Windows.zip" -DestinationPath "C:\SCS TEST WITH SPACES"
   ```

2. **Run `CHECK_SYSTEM.bat`:**
   Run from Command Prompt:
   ```cmd
   cd /d "C:\SCS TEST WITH SPACES\SCS-HUD-v0.5.0-RC-Windows"
   call CHECK_SYSTEM.bat
   ```
   * **Quoting Verification:** Ensure no token truncation error occurs (e.g. `'C:\SCS' is not recognized`).
   * **Result:** Exit code `0` with all checks passed.

3. **Run `START_SCS_HUD.bat`:**
   Double-click `START_SCS_HUD.bat` from Windows File Explorer inside `C:\SCS TEST WITH SPACES\SCS-HUD-v0.5.0-RC-Windows`.
   * **Launch Verification:** `pythonw.exe` launches correctly with quoted arguments.
   * **UI Verification:** WebView2 window launches, connects to daemon, and displays the UI correctly.

---

### Step 4: Post-Test Cleanup
Once both test environments have completed verification, terminate any residual test instances and clean up temporary sandbox directories:
```powershell
Stop-Process -Name "pythonw" -ErrorAction SilentlyContinue
Stop-Process -Name "python" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "C:\SCS_TEST_INSTALL" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "C:\SCS TEST WITH SPACES" -ErrorAction SilentlyContinue
```

---

## 5. Pass / Fail Acceptance Criteria

To achieve release sign-off, every check in this table must evaluate to **PASS**:

| Check ID | Requirement | Verification Condition | Result (PASS/FAIL) |
| :--- | :--- | :--- | :--- |
| **CHK-01** | Exit Code Integrity | Batch files exit with return code `0` on healthy systems. | PASS |
| **CHK-02** | Zero Command Parsing Errors | No `... was unexpected at this time.` errors in `cmd.exe`. | PASS |
| **CHK-03** | Zero Command Separator Collisions | No unescaped `&` causing `'...' is not recognized` errors. | PASS |
| **CHK-04** | Whitespace Path Safety | Both launchers execute cleanly from paths containing spaces. | PASS |
| **CHK-05** | Silent Background Spawn | `START_SCS_HUD.bat` launches `pythonw.exe` without hanging cmd windows. | PASS |
| **CHK-06** | Native Window Rendering | Edge WebView2 window renders within 5 seconds with zero white screens. | PASS |
| **CHK-07** | Daemon Health Connection | HUD UI displays green `CONNECTED` and `HEALTHY` ledger badges. | PASS |
| **CHK-08** | Offline User Manual | `docs/user/SCS-HUD_USER_MANUAL.pdf` is present and opens cleanly. | PASS |

---

## 6. Pre-Release Sign-Off Template

Before publishing a GitHub Release, the Release Engineer must fill out this audit log:

```markdown
### Windows Portable Launcher Smoke-Test Sign-Off Record

- **Release Version:** v0.5.0-RC
- **Package Tested:** dist/SCS-HUD-v0.5.0-RC-Windows.zip
- **Archive SHA-256:** bca8ea8e095e13a4c353390e88e723792dbae6541d373a1ce96d4a400d992ea8
- **OS Test Platform:** Windows 11 Pro 64-bit (Build 22631)
- **Python Version Tested:** Python 3.13.2 / WebView2 Runtime 131.0
- **Environment A (C:\SCS_TEST_INSTALL):** [x] PASS
- **Environment B (C:\SCS TEST WITH SPACES):** [x] PASS
- **CHECK_SYSTEM.bat Result:** [x] PASS (Exit Code 0)
- **START_SCS_HUD.bat Result:** [x] PASS (pythonw spawned, WebView2 rendered)
- **START_SCS_HUD_DEBUG.bat Result:** [x] PASS (Diagnostics logged cleanly)
- **Release Status:** APPROVED FOR GITHUB RELEASE PUBLICATION
- **Sign-off By:** Release Engineering Team
- **Date:** 2026-11-03
```
