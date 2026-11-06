"""Automated HTTP authorization and RPC endpoint tests for LocalRPCServer (ACT-04)."""

import unittest
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*Using `httpx` with `starlette.testclient`.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    from starlette.testclient import TestClient
    from scs_host.local_rpc_server import LocalRPCServer
    HAS_STARLETTE = True
except ImportError:
    HAS_STARLETTE = False
    TestClient = None
    LocalRPCServer = None

from scs_core.db.database import VaultDatabase
from scs_core.modules.mod04_projects_sessions import ProjectSessionService
from scs_core.modules.mod04_decision_ledger import DecisionLedgerService
from scs_core.modules.mod05_checklist_engine import ChecklistEngineService
from scs_core.modules.mod06_artifact_registry import ArtifactRegistryService
from scs_core.modules.mod03_approval_gate import ApprovalGateService
from scs_core.modules.mod07_reconciler import ReadOnlyReconciler
from scs_core.modules.mod02_protocol_engine import ProtocolEngineService
from scs_core.ipc.dispatcher import SCSDispatcher


@unittest.skipUnless(HAS_STARLETTE, "starlette package not installed (optional UI server dependency)")
class TestLocalRPCServerAuthorization(unittest.TestCase):
    """Test suite validating HTTP X-SCS-Token enforcement and /api/invoke behavior."""

    @classmethod
    def setUpClass(cls):
        # Suppress Starlette test client deprecation notice for httpx
        warnings.filterwarnings("ignore", message=".*StarletteDeprecationWarning.*")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test_vault.db"
        self.db = VaultDatabase(self.db_path)

        self.project_svc = ProjectSessionService(self.db, snapshots_dir=self.temp_path / "snaps")
        self.decision_svc = DecisionLedgerService(self.db)
        self.checklist_svc = ChecklistEngineService(self.db)
        self.artifact_svc = ArtifactRegistryService(self.db)
        self.gate_svc = ApprovalGateService(
            self.db, self.decision_svc, self.checklist_svc, self.artifact_svc
        )
        self.reconciler = ReadOnlyReconciler(self.db)
        self.protocol_svc = ProtocolEngineService(
            self.db,
            self.project_svc,
            self.decision_svc,
            self.checklist_svc,
            self.artifact_svc,
            self.gate_svc,
            self.reconciler,
            exports_dir=self.temp_path / "exports",
        )

        self.dispatcher = SCSDispatcher(
            self.db,
            self.project_svc,
            self.decision_svc,
            self.checklist_svc,
            self.artifact_svc,
            self.gate_svc,
            self.reconciler,
            self.protocol_svc,
        )

        self.valid_token = "valid-secret-scs-token-999"
        self.server = LocalRPCServer(self.dispatcher, session_token=self.valid_token)
        self.client = TestClient(self.server.app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_unauthorized_when_token_header_is_missing(self):
        """Requests without X-SCS-Token header must be rejected with 403 Forbidden."""
        response = self.client.post(
            "/api/invoke",
            json={"command": "get_dashboard_state", "payload": {}},
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "UNAUTHORIZED")
        self.assertEqual(body["error"]["message"], "Invalid session token")

    def test_unauthorized_when_token_header_is_invalid(self):
        """Requests with an incorrect X-SCS-Token must be rejected with 403 Forbidden."""
        response = self.client.post(
            "/api/invoke",
            json={"command": "get_dashboard_state", "payload": {}},
            headers={"X-SCS-Token": "bogus-unauthorized-token"},
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "UNAUTHORIZED")
        self.assertEqual(body["error"]["message"], "Invalid session token")

    def test_authorized_request_succeeds_with_valid_token(self):
        """Requests with the matching X-SCS-Token header must return 200 OK and invoke dispatcher."""
        response = self.client.post(
            "/api/invoke",
            json={"command": "get_dashboard_state", "payload": {}},
            headers={"X-SCS-Token": self.valid_token},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertIn("active_project", body["data"])

    def test_authorized_rpc_execution_roundtrip(self):
        """Full roundtrip through authorized HTTP RPC to create and fetch a project."""
        create_res = self.client.post(
            "/api/invoke",
            json={
                "command": "create_project",
                "payload": {"code": "TEST_PRJ", "name": "HTTP Test Project"},
            },
            headers={"X-SCS-Token": self.valid_token},
        )
        self.assertEqual(create_res.status_code, 200)
        create_body = create_res.json()
        self.assertTrue(create_body["ok"])
        project_id = create_body["data"]["id"]

        # Fetch state
        state_res = self.client.post(
            "/api/invoke",
            json={"command": "get_dashboard_state", "payload": {"project_id": project_id}},
            headers={"X-SCS-Token": self.valid_token},
        )
        self.assertEqual(state_res.status_code, 200)
        state_body = state_res.json()
        self.assertTrue(state_body["ok"])
        self.assertEqual(state_body["data"]["active_project"]["code"], "TEST_PRJ")

        # Test generate_human_briefing RPC endpoint
        briefing_res = self.client.post(
            "/api/invoke",
            json={"command": "generate_human_briefing", "payload": {"project_id": project_id}},
            headers={"X-SCS-Token": self.valid_token},
        )
        self.assertEqual(briefing_res.status_code, 200)
        briefing_body = briefing_res.json()
        self.assertTrue(briefing_body["ok"])
        self.assertIn("HUMAN_BRIEFING.md", briefing_body["data"]["file_name"])
        self.assertIn("## A. Project Identity", briefing_body["data"]["markdown_content"])

        # Test generate_recovery_card RPC endpoint
        card_res = self.client.post(
            "/api/invoke",
            json={"command": "generate_recovery_card", "payload": {"project_id": project_id}},
            headers={"X-SCS-Token": self.valid_token},
        )
        self.assertEqual(card_res.status_code, 200)
        card_body = card_res.json()
        self.assertTrue(card_body["ok"])
        self.assertIn("PROJECT_RECOVERY_CARD.md", card_body["data"]["file_name"])
        self.assertIn("## 📍 Where We Are", card_body["data"]["markdown_content"])

    def test_window_control_host_interception_authorized(self):
        """Window control host commands are intercepted and return 200 OK when authorized."""
        # Test compact / pill view mode (tight dimensions: 430x220)
        response = self.client.post(
            "/api/invoke",
            json={"command": "window_control", "payload": {"action": "set_view_mode", "mode": "pill"}},
            headers={"X-SCS-Token": self.valid_token},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["mode"], "pill")
        self.assertEqual(body["data"]["width"], 430)
        self.assertEqual(body["data"]["height"], 220)

        # Test compact mode alias
        res_compact = self.client.post(
            "/api/invoke",
            json={"command": "window_control", "payload": {"action": "set_view_mode", "mode": "compact"}},
            headers={"X-SCS-Token": self.valid_token},
        )
        self.assertEqual(res_compact.status_code, 200)
        self.assertEqual(res_compact.json()["data"]["height"], 220)

        # Test full drawer view mode
        res_drawer = self.client.post(
            "/api/invoke",
            json={"command": "window_control", "payload": {"action": "set_view_mode", "mode": "drawer"}},
            headers={"X-SCS-Token": self.valid_token},
        )
        self.assertEqual(res_drawer.status_code, 200)
        self.assertEqual(res_drawer.json()["data"]["height"], 680)

    def test_window_control_rejected_without_token(self):
        """Window control commands must also be rejected with 403 if token is missing."""
        response = self.client.post(
            "/api/invoke",
            json={"command": "window_control", "payload": {"action": "set_view_mode", "mode": "pill"}},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])

    def test_index_serves_html_with_injected_session_token(self):
        """GET / must serve index.html with the active session token injected."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertIn(f'window.__SCS_SESSION_TOKEN__ = "{self.valid_token}";', response.text)

    def test_invalid_json_body_returns_bad_request(self):
        """Malformed JSON payload with valid token must return 400 Bad Request."""
        response = self.client.post(
            "/api/invoke",
            content="invalid-non-json-payload",
            headers={"X-SCS-Token": self.valid_token, "Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "BAD_REQUEST")


if __name__ == "__main__":
    unittest.main()
