"""
MCP Models.
Pydantic schemas exposed via the MCP protocol.
"""
from pydantic import BaseModel, Field
from typing import List, Any, Optional

class MigrationSession(BaseModel):
    session_id: str = Field(description="Unique session ID representing the workspace")
    workspace_path: str = Field(description="Path to the isolated workspace")
    current_stage: str = Field(description="Current running stage in the Orchestrator")
    review_score: int = Field(description="Latest architectural review score")
    validation_score: int = Field(description="Latest compilation validation score")
    logs: List[str] = Field(default_factory=list, description="Execution progress logs")
    artifacts: List[Any] = Field(default_factory=list, description="Generated artifacts")
    duration_s: float = Field(description="Total migration duration in seconds")
    status: str = Field(description="Session state")
