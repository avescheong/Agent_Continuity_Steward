#!/usr/bin/env python3
"""
export_clean_repo.py — Clean Repository Exporter for Agent_Continuity_Steward

Exports publication-approved assets from the development workspace into the clean
GitHub release repository at D:\\000. GITHUB\\Agent_Continuity_Steward.
"""

import os
import shutil
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent
TARGET_ROOT = Path(r"D:\000. GITHUB\Agent_Continuity_Steward")

EXCLUDE_DIRS = {"__pycache__", ".continuity", ".pytest_cache", ".git", ".idea", ".vscode"}
EXCLUDE_FILES = {"desktop.ini", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db"}


def should_ignore(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    name = path.name
    if name == "desktop.ini" or name.endswith((".pyc", ".pyo")):
        return True
    return False


def copy_tree_filtered(src_dir: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src_dir):
        # Filter out exclude dirs in place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel_root = Path(root).relative_to(src_dir)
        target_sub = dst_dir / rel_root
        target_sub.mkdir(parents=True, exist_ok=True)
        for f in files:
            file_path = Path(root) / f
            if should_ignore(file_path):
                continue
            shutil.copy2(file_path, target_sub / f)


def clean_target_cache_and_artifacts(target: Path):
    """Removes __pycache__, .pyc, and other excluded artifacts from target."""
    for root, dirs, files in os.walk(target, topdown=False):
        if ".git" in Path(root).parts:
            continue
        for d in dirs:
            if d in EXCLUDE_DIRS:
                dp = Path(root) / d
                try:
                    shutil.rmtree(dp)
                except Exception:
                    pass
        for f in files:
            if f.endswith((".pyc", ".pyo")) or f in EXCLUDE_FILES:
                fp = Path(root) / f
                try:
                    fp.unlink()
                except Exception:
                    pass


def main():
    print(f"Source Root: {SOURCE_ROOT}")
    print(f"Target Root: {TARGET_ROOT}")

    if not TARGET_ROOT.exists():
        TARGET_ROOT.mkdir(parents=True, exist_ok=True)

    # 1. engine/ (from SCS_AG_v2/engine)
    print("Copying engine/...")
    copy_tree_filtered(SOURCE_ROOT / "SCS_AG_v2" / "engine", TARGET_ROOT / "engine")

    # 2. specs/ (from SCS_AG_v2/specs)
    print("Copying specs/...")
    copy_tree_filtered(SOURCE_ROOT / "SCS_AG_v2" / "specs", TARGET_ROOT / "specs")

    # 3. .agents/ (from SCS_AG_v2/.agents)
    print("Copying .agents/...")
    copy_tree_filtered(SOURCE_ROOT / "SCS_AG_v2" / ".agents", TARGET_ROOT / ".agents")

    # 4. core/ (from core)
    print("Copying core/...")
    copy_tree_filtered(SOURCE_ROOT / "core", TARGET_ROOT / "core")

    # 5. src/ (from src)
    print("Copying src/...")
    copy_tree_filtered(SOURCE_ROOT / "src", TARGET_ROOT / "src")

    # 6. tests/ (from tests)
    print("Copying tests/...")
    copy_tree_filtered(SOURCE_ROOT / "tests", TARGET_ROOT / "tests")

    # 7. test-vectors/ (from test-vectors)
    print("Copying test-vectors/...")
    copy_tree_filtered(SOURCE_ROOT / "test-vectors", TARGET_ROOT / "test-vectors")

    # 8. scripts/ (verify_release.py & export_clean_repo.py)
    print("Copying scripts/...")
    scripts_target = TARGET_ROOT / "scripts"
    scripts_target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_ROOT / "scripts" / "verify_release.py", scripts_target / "verify_release.py")
    shutil.copy2(SOURCE_ROOT / "scripts" / "export_clean_repo.py", scripts_target / "export_clean_repo.py")

    # 9. docs/
    print("Copying docs/...")
    docs_target = TARGET_ROOT / "docs"
    docs_target.mkdir(parents=True, exist_ok=True)
    doc_files = [
        "ARCHITECTURE.md",
        "DESIGN_PHILOSOPHY.md",
        "DOGFOODING_LOG.md",
        "GITHUB_REVIEW.md",
        "GOVERNANCE_MODEL.md",
        "PHASE_8_SKILL_VALIDATION_PLAN.md",
        "PHASE_8_STEP_8_1_RESULTS.md",
        "PHASE_8_STEP_8_2_RESULTS.md",
        "PHASE_8_STEP_8_3_RESULTS.md",
        "PHASE_8_STEP_8_4_RESULTS.md",
        "QUICKSTART.md",
        "README_OVERVIEW.md",
        "ROADMAP.md",
        "SECURITY_MODEL.md",
        "SKILL_PRODUCTIZATION.md",
    ]
    for df in doc_files:
        src_f = SOURCE_ROOT / "docs" / df
        if src_f.exists():
            shutil.copy2(src_f, docs_target / df)

    copy_tree_filtered(SOURCE_ROOT / "docs" / "verification", docs_target / "verification")
    copy_tree_filtered(SOURCE_ROOT / "docs" / "evidence", docs_target / "evidence")

    # 10. Root files: LICENSE, README.md, RELEASE_CANDIDATE_CHECKLIST.md, .gitignore, pyproject.toml
    print("Copying root files...")
    shutil.copy2(SOURCE_ROOT / "LICENSE", TARGET_ROOT / "LICENSE")
    shutil.copy2(SOURCE_ROOT / "RELEASE_CANDIDATE_CHECKLIST.md", TARGET_ROOT / "RELEASE_CANDIDATE_CHECKLIST.md")
    shutil.copy2(SOURCE_ROOT / "docs" / "README_OVERVIEW.md", TARGET_ROOT / "README.md")

    # Clean .gitignore
    gitignore_content = """# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class
*.so

# Distribution / packaging
dist/
build/
*.egg-info/
.eggs/

# Virtual environments
.venv/
env/
venv/
ENV/

# Private Continuity Vaults (Centralized external vaults recommended)
.continuity/
*.continuity

# OS Generated Artifacts
desktop.ini
Thumbs.db
.DS_Store

# IDE and Editor Files
.vscode/
.idea/
*.swp
*.swo

# Environment & Credentials
.env
.env.*
*.pem
*.key
"""
    (TARGET_ROOT / ".gitignore").write_text(gitignore_content, encoding="utf-8")

    # Clean pyproject.toml
    pyproject_content = """[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "agent-continuity-steward"
version = "1.0.0"
description = "Deterministic Session Continuity and Architecture Governance for AI Coding Agents"
readme = "README.md"
authors = [
    { name = "Aves Cheong & Session Continuity Steward Contributors" }
]
license = { text = "MIT" }
requires-python = ">=3.10"
dependencies = []
keywords = [
    "ai",
    "agent",
    "continuity",
    "governance",
    "antigravity",
    "session-continuity",
    "llm",
    "architecture-decision-records"
]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Topic :: Scientific/Engineering :: Artificial Intelligence"
]

[project.scripts]
scs = "engine.scs_cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["engine*", "src*"]

[project.urls]
Homepage = "https://github.com/Agent-Continuity-Steward/Agent_Continuity_Steward"
Documentation = "https://github.com/Agent-Continuity-Steward/Agent_Continuity_Steward/tree/main/docs"
Repository = "https://github.com/Agent-Continuity-Steward/Agent_Continuity_Steward"
"""
    (TARGET_ROOT / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

    # Final cache and artifact purge
    print("Purging cache directories and byte-compiled artifacts...")
    clean_target_cache_and_artifacts(TARGET_ROOT)

    print("[SUCCESS] Clean repository exported successfully to:")
    print(f"  {TARGET_ROOT}")


if __name__ == "__main__":
    main()
