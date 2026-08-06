"""
MCP Session Manager.
Handles concurrent migration sessions natively via isolated workspaces.
"""
import uuid
from typing import Dict, List

from mcp.models import MigrationSession
from workflows.orchestrator import Orchestrator
from agents.context import AgentContext
from workflows.workspace import WorkspaceManager
from knowledge.context_manager import ContextManager
from knowledge.document_index import DocumentIndex
from knowledge.code_index import CodeIndex
from agents.state import MigrationState
from config.settings import settings
from config.logging import get_logger
from shared.llm import LLMClient

class SessionManager:
    """Manages isolated state for multiple concurrent migrations."""
    def __init__(self):
        self.sessions: Dict[str, Orchestrator] = {}
        
    def create_session(self) -> str:
        """Initializes a new session and returns its ID."""
        mig_id = str(uuid.uuid4())
        workspace = WorkspaceManager(mig_id)
        ctx = AgentContext(
            migration_id=mig_id,
            settings=settings,
            llm=LLMClient(),
            workspace=workspace,
            knowledge=ContextManager(doc_index=DocumentIndex(), code_index=CodeIndex()),
            state=MigrationState(migration_id=mig_id),
            logger=get_logger(f"mcp_session_{mig_id}")
        )
        self.sessions[mig_id] = Orchestrator(ctx)
        return mig_id
        
    def get_orchestrator(self, session_id: str) -> Orchestrator:
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found.")
        return self.sessions[session_id]
        
    def get_session_info(self, session_id: str) -> MigrationSession:
        orch = self.get_orchestrator(session_id)
        state = orch.context.state
        return MigrationSession(
            session_id=session_id,
            workspace_path=str(orch.context.workspace.base_dir),
            current_stage=state.current_stage,
            review_score=state.statistics.get("review_score", 0),
            validation_score=state.statistics.get("validation_score", 0),
            logs=state.statistics.get("progress_logs", []),
            artifacts=[a.model_dump() for a in state.generated_artifacts],
            duration_s=state.statistics.get("Total_duration_s", 0.0),
            status=state.current_stage
        )

    def list_sessions(self) -> List[MigrationSession]:
        return [self.get_session_info(sid) for sid in self.sessions.keys()]
        
session_manager = SessionManager()
