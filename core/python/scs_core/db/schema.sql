PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '#6366F1',
    root_paths_json TEXT NOT NULL DEFAULT '[]',
    objective TEXT NOT NULL DEFAULT '',
    current_focus TEXT NOT NULL DEFAULT '',
    next_action TEXT NOT NULL DEFAULT '',
    latest_snapshot_id TEXT,
    latest_snapshot_sha256 TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    proposal_type TEXT NOT NULL CHECK (
        proposal_type IN ('TASK', 'DECISION', 'CONSTRAINT', 'REJECTED_OPTION', 'IDEA', 'BLOCKER', 'ARTIFACT')
    ),
    title TEXT NOT NULL,
    rationale_why TEXT NOT NULL DEFAULT '',
    source_excerpt TEXT NOT NULL DEFAULT '',
    source_origin TEXT NOT NULL DEFAULT 'MANUAL_CAPTURE',
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'APPROVED', 'EDITED_APPROVED', 'REJECTED')
    ),
    resolved_entity_id TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_proposals_project_status ON proposals(project_id, status);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    record_kind TEXT NOT NULL CHECK (
        record_kind IN ('DECISION', 'CONSTRAINT', 'REJECTED_OPTION', 'IDEA')
    ),
    statement TEXT NOT NULL,
    rationale_why TEXT NOT NULL DEFAULT '',
    impact_scope TEXT NOT NULL DEFAULT '',
    source_excerpt TEXT NOT NULL DEFAULT '',
    source_proposal_id TEXT REFERENCES proposals(id) ON DELETE SET NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, code)
);
CREATE INDEX IF NOT EXISTS idx_decisions_project_kind ON decisions(project_id, record_kind, is_active);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED')
    ),
    priority TEXT NOT NULL DEFAULT 'MEDIUM' CHECK (
        priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    ),
    why_it_matters TEXT NOT NULL DEFAULT '',
    source_excerpt TEXT NOT NULL DEFAULT '',
    blocker_reason TEXT NOT NULL DEFAULT '',
    related_decision_ids_json TEXT NOT NULL DEFAULT '[]',
    depends_on_task_ids_json TEXT NOT NULL DEFAULT '[]',
    source_proposal_id TEXT REFERENCES proposals(id) ON DELETE SET NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(project_id, code)
);
CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    artifact_type TEXT NOT NULL DEFAULT 'DOCUMENT' CHECK (
        artifact_type IN ('CODE_FILE', 'DOCUMENT', 'BLUEPRINT', 'SPECIFICATION', 'GENERATED_OUTPUT', 'OTHER')
    ),
    conversation_note TEXT NOT NULL DEFAULT '',
    relative_path TEXT,
    external_ref TEXT,
    custody_state TEXT NOT NULL DEFAULT 'CONVERSATION_ONLY' CHECK (
        custody_state IN ('CONVERSATION_ONLY', 'LOCAL_FILE_EXISTS', 'VERIFIED_MATCH', 'MODIFIED', 'MISSING', 'UNKNOWN')
    ),
    baseline_sha256 TEXT,
    observed_sha256 TEXT,
    observed_size_bytes INTEGER,
    observed_mtime_iso TEXT,
    required_markers_json TEXT NOT NULL DEFAULT '[]',
    missing_markers_json TEXT NOT NULL DEFAULT '[]',
    source_proposal_id TEXT REFERENCES proposals(id) ON DELETE SET NULL,
    last_reconciled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_project_state ON artifacts(project_id, custody_state);
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_project_relpath ON artifacts(project_id, relative_path) WHERE relative_path IS NOT NULL AND relative_path != '';

CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    snapshot_code TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    state_json TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    mirror_file_path TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, snapshot_code)
);

CREATE TABLE IF NOT EXISTS handover_packages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    snapshot_id TEXT REFERENCES snapshots(id) ON DELETE SET NULL,
    protocol_version TEXT NOT NULL DEFAULT 'scs-handover/1.0',
    markdown_content TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    exported_file_path TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_code TEXT,
    session_num INTEGER,
    content TEXT NOT NULL DEFAULT '',
    checksum_sha256 TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'CLIPBOARD',
    word_count INTEGER NOT NULL DEFAULT 0,
    raw_file_path TEXT,
    fragments_json TEXT NOT NULL DEFAULT '[]', -- Deprecated compatibility column
    started_at TEXT NOT NULL,
    last_activity TEXT NOT NULL,
    checkpoint_status TEXT NOT NULL DEFAULT 'DRAFT',
    latest_checkpoint_path TEXT,
    latest_checkpoint_sha256 TEXT,
    latest_snapshot_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_project_status ON conversation_sessions(project_id, checkpoint_status);
