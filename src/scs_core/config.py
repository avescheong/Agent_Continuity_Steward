"""Runtime configuration, paths, and constants for SCS-HUD."""

from pathlib import Path
import os

# Default workspace root is the project root containing src/
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent

# Data directory can be overridden via environment variable (useful for testing)
DEFAULT_DATA_DIR = Path(os.environ.get("SCS_DATA_DIR", WORKSPACE_ROOT / "data"))

# Sub-paths
DB_PATH = DEFAULT_DATA_DIR / "scs_vault.db"
SNAPSHOTS_DIR = DEFAULT_DATA_DIR / "snapshots"
EXPORTS_DIR = DEFAULT_DATA_DIR / "exports"

# Token budget and display limits
DEFAULT_BOOTSTRAP_TOKEN_TARGET = 600
MAX_COMPACT_WHY_LEN = 34
DEFAULT_READONLY_CHUNK_SIZE = 65536  # 64 KB

def ensure_data_directories(data_dir: Path | None = None) -> None:
    """Ensures that the runtime data directories exist."""
    base = data_dir or DEFAULT_DATA_DIR
    base.mkdir(parents=True, exist_ok=True)
    (base / "snapshots").mkdir(parents=True, exist_ok=True)
    (base / "exports").mkdir(parents=True, exist_ok=True)
