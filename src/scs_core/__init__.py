"""SCS Core - Session Continuity Steward Reference Implementation.

Headless domain engine providing:
- Multi-session continuity extraction (CavemanContextExtractionEngine)
- Dual-ledger state management and human approval gates
- SHA-256 cryptographic snapshot sealing
- O_RDONLY reality auditing (ReadOnlyReconciler)
- Fail-closed causal verification
"""

__version__ = "0.5.0"
__author__ = "Session Continuity Steward Contributors"
__license__ = "MIT"

from scs_core.db.database import VaultDatabase
from scs_core.modules.caveman_engine import CavemanContextExtractionEngine
from scs_core.modules.caveman_context_validator import CavemanContextValidator
from scs_core.modules.mod02_protocol_engine import ProtocolEngineService
from scs_core.modules.mod03_approval_gate import ApprovalGateService
from scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from scs_core.modules.mod04_projects_sessions import ProjectSessionService
from scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from scs_core.modules.mod07_reconciler import ReadOnlyReconciler
from scs_core.ipc.dispatcher import SCSDispatcher

# Specification alias
JsonRpcDispatcher = SCSDispatcher

__all__ = [
    "__version__",
    "VaultDatabase",
    "CavemanContextExtractionEngine",
    "CavemanContextValidator",
    "ProtocolEngineService",
    "ApprovalGateService",
    "DecisionLedgerService",
    "ProjectSessionService",
    "ChecklistEngineService",
    "ArtifactRegistryService",
    "ReadOnlyReconciler",
    "SCSDispatcher",
    "JsonRpcDispatcher",
]
