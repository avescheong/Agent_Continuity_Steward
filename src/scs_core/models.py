"""Domain models, enums, and RPC payload definitions for SCS-HUD."""

from enum import Enum
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone
import uuid


def utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Zero-Dependency Base Model & Field Definition (Pure Python Standard Library)
# ---------------------------------------------------------------------------

class _FieldMarker:
    def __init__(self, default=None, default_factory=None):
        self.default = default
        self.default_factory = default_factory


def Field(*, default=None, default_factory=None, **kwargs) -> Any:
    """Drop-in replacement for pydantic.Field using standard library only."""
    return _FieldMarker(default=default, default_factory=default_factory)


class BaseModel:
    """Standard library drop-in replacement for pydantic.BaseModel.

    Provides:
      - Field initialization with defaults and default_factories
      - Resilient keyword handling (ignores unknown kwargs for backward compatibility)
      - Recursive .model_dump(mode='json') and .dict()
      - __repr__ and __eq__
    """
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        declared = {}
        for base in reversed(cls.__mro__):
            for k, v in getattr(base, "__annotations__", {}).items():
                if k.startswith("_"):
                    continue
                default_val = getattr(base, k, None)
                declared[k] = (v, default_val)
        cls._declared_fields = declared

    def __init__(self, *args, **kwargs):
        declared = getattr(self.__class__, "_declared_fields", {})
        field_keys = list(declared.keys())
        for i, val in enumerate(args):
            if i < len(field_keys):
                setattr(self, field_keys[i], val)
        for name, (_, default_val) in declared.items():
            if name in kwargs:
                setattr(self, name, kwargs[name])
            elif name not in self.__dict__:
                if isinstance(default_val, _FieldMarker):
                    if default_val.default_factory is not None:
                        setattr(self, name, default_val.default_factory())
                    else:
                        setattr(self, name, default_val.default)
                else:
                    setattr(self, name, default_val)

    def model_dump(self, mode: str = "json") -> Dict[str, Any]:
        """Serializes model to dictionary recursively, converting Enums and nested models."""
        declared = getattr(self.__class__, "_declared_fields", {})
        out = {}
        for name in declared:
            val = getattr(self, name, None)
            out[name] = self._dump_value(val, mode=mode)
        return out

    def dict(self, *args, **kwargs) -> Dict[str, Any]:
        """Backward-compatibility alias for model_dump."""
        return self.model_dump(mode="python")

    @classmethod
    def _dump_value(cls, val: Any, mode: str = "json") -> Any:
        if isinstance(val, BaseModel):
            return val.model_dump(mode=mode)
        if isinstance(val, Enum):
            return val.value
        if isinstance(val, list):
            return [cls._dump_value(x, mode=mode) for x in val]
        if isinstance(val, dict):
            return {k: cls._dump_value(v, mode=mode) for k, v in val.items()}
        return val

    def __repr__(self) -> str:
        declared = getattr(self.__class__, "_declared_fields", {})
        attrs = ", ".join(f"{k}={getattr(self, k, None)!r}" for k in declared)
        return f"{self.__class__.__name__}({attrs})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, self.__class__):
            return False
        declared = getattr(self.__class__, "_declared_fields", {})
        return all(getattr(self, k, None) == getattr(other, k, None) for k in declared)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProposalType(str, Enum):
    TASK = "TASK"
    DECISION = "DECISION"
    CONSTRAINT = "CONSTRAINT"
    REJECTED_OPTION = "REJECTED_OPTION"
    IDEA = "IDEA"
    BLOCKER = "BLOCKER"
    ARTIFACT = "ARTIFACT"


class ProposalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EDITED_APPROVED = "EDITED_APPROVED"
    REJECTED = "REJECTED"


class DecisionKind(str, Enum):
    DECISION = "DECISION"
    CONSTRAINT = "CONSTRAINT"
    REJECTED_OPTION = "REJECTED_OPTION"
    IDEA = "IDEA"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ArtifactType(str, Enum):
    CODE_FILE = "CODE_FILE"
    DOCUMENT = "DOCUMENT"
    BLUEPRINT = "BLUEPRINT"
    SPECIFICATION = "SPECIFICATION"
    GENERATED_OUTPUT = "GENERATED_OUTPUT"
    OTHER = "OTHER"


class ArtifactCustodyState(str, Enum):
    CONVERSATION_ONLY = "CONVERSATION_ONLY"
    LOCAL_FILE_EXISTS = "LOCAL_FILE_EXISTS"
    VERIFIED_MATCH = "VERIFIED_MATCH"
    MODIFIED = "MODIFIED"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class CheckpointStatus(str, Enum):
    DRAFT = "DRAFT"
    GENERATED = "GENERATED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


# ---------------------------------------------------------------------------
# Domain Models
# ---------------------------------------------------------------------------

class ChatFragment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sequence_idx: int
    content: str
    source: str = "CLIPBOARD"
    captured_at: str = Field(default_factory=utc_now_iso)
    word_count: int = 0
    checksum_sha256: str = ""


class ConversationSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    fragments: List[ChatFragment] = Field(default_factory=list)
    started_at: str = Field(default_factory=utc_now_iso)
    last_activity: str = Field(default_factory=utc_now_iso)
    checkpoint_status: CheckpointStatus = CheckpointStatus.DRAFT
    latest_checkpoint_path: Optional[str] = None
    latest_checkpoint_sha256: Optional[str] = None
    latest_snapshot_code: Optional[str] = None


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    name: str
    description: str = ""
    color: str = "#6366F1"
    root_paths: List[str] = Field(default_factory=list)
    objective: str = ""
    current_focus: str = ""
    next_action: str = ""
    latest_snapshot_id: Optional[str] = None
    latest_snapshot_sha256: Optional[str] = None
    is_archived: bool = False
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class Proposal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    proposal_type: ProposalType
    title: str
    rationale_why: str = ""
    source_excerpt: str = ""
    source_origin: str = "MANUAL_CAPTURE"
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: ProposalStatus = ProposalStatus.PENDING
    resolved_entity_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    resolved_at: Optional[str] = None


class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    code: str  # DEC-001, CON-001, REJ-001, IDA-001
    record_kind: DecisionKind
    statement: str
    rationale_why: str = ""
    impact_scope: str = ""
    source_excerpt: str = ""
    source_proposal_id: Optional[str] = None
    is_active: bool = True
    author: Optional[str] = None
    approved_by: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class TaskItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    code: str  # TSK-001
    title: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    why_it_matters: str = ""
    source_excerpt: str = ""
    blocker_reason: str = ""
    related_decision_ids: List[str] = Field(default_factory=list)
    depends_on_task_ids: List[str] = Field(default_factory=list)
    source_proposal_id: Optional[str] = None
    sort_order: int = 0
    author: Optional[str] = None
    approved_by: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    completed_at: Optional[str] = None

    @property
    def compact_why(self) -> str:
        """Returns a trimmed rationale string (under 34 chars) for compact cards."""
        return compact_why(self.why_it_matters)


class ArtifactRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str
    artifact_type: ArtifactType = ArtifactType.DOCUMENT
    conversation_note: str = ""
    relative_path: Optional[str] = None
    external_ref: Optional[str] = None
    custody_state: ArtifactCustodyState = ArtifactCustodyState.CONVERSATION_ONLY
    baseline_sha256: Optional[str] = None
    observed_sha256: Optional[str] = None
    observed_size_bytes: Optional[int] = None
    observed_mtime_iso: Optional[str] = None
    required_markers: List[str] = Field(default_factory=list)
    missing_markers: List[str] = Field(default_factory=list)
    source_proposal_id: Optional[str] = None
    last_reconciled_at: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class SnapshotRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    snapshot_code: str  # SNP-YYYYMMDD-001
    label: str = ""
    state_json: str
    checksum_sha256: str
    mirror_file_path: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)


class HandoverPackage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    snapshot_id: Optional[str] = None
    protocol_version: str = "scs-handover/1.0"
    markdown_content: str
    checksum_sha256: str
    exported_file_path: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)


# ---------------------------------------------------------------------------
# DTOs / Aggregates
# ---------------------------------------------------------------------------

class ReconcileSummary(BaseModel):
    total: int = 0
    verified_match: int = 0
    local_file_exists: int = 0
    modified: int = 0
    missing: int = 0
    conversation_only: int = 0
    unknown: int = 0


class BootstrapResult(BaseModel):
    project_code: str
    prompt_text: str
    approx_tokens: int
    redacted_count: int
    reconcile_summary: ReconcileSummary


class DashboardState(BaseModel):
    active_project: Optional[Project] = None
    all_projects: List[Project] = Field(default_factory=list)
    proposals_pending: List[Proposal] = Field(default_factory=list)
    tasks: List[TaskItem] = Field(default_factory=list)
    decisions: List[DecisionRecord] = Field(default_factory=list)
    artifacts: List[ArtifactRecord] = Field(default_factory=list)
    recent_snapshots: List[SnapshotRecord] = Field(default_factory=list)
    reconcile_summary: ReconcileSummary = Field(default_factory=ReconcileSummary)
    active_session: Optional[ConversationSession] = None
    fragment_count: int = 0
    total_sessions: int = 0
    processed_sessions: int = 0
    pending_sessions: int = 0
    continuity_md_count: int = 0
    continuity_chapters: List[Dict[str, Any]] = Field(default_factory=list)
    session_records: List[Dict[str, Any]] = Field(default_factory=list)


def compact_why(text: str, max_len: int = 34) -> str:
    """Strips verbose leading prefixes and truncates to max_len chars for compact display."""
    if not text:
        return ""
    clean = text.strip()
    for prefix in ["Reason:", "reason:", "Why:", "why:", "Because:", "because:"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
            break
    if len(clean) > max_len:
        return clean[:max_len - 3].rstrip() + "..."
    return clean
