"""
MigrationState for tracking the execution of a migration pipeline.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from shared.artifacts import BaseArtifact, ReviewReport, ValidationReport

class MigrationState(BaseModel):
    """
    Central state machine tracker for a migration run.
    Contains the lifecycle status, timing, and all aggregated artifacts.
    Supports JSON serialization.
    """
    migration_id: str = Field(description="The unique run ID")
    current_stage: str = Field(default="INITIALIZED", description="The currently executing stage/agent")
    
    completed_stages: List[str] = Field(default_factory=list, description="Stages that executed successfully")
    failed_stages: List[str] = Field(default_factory=list, description="Stages that failed")
    
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings emitted during the run")
    errors: List[str] = Field(default_factory=list, description="Fatal error tracebacks")
    
    generated_artifacts: List[BaseArtifact] = Field(default_factory=list, description="All artifacts produced")
    
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Run start time")
    end_time: Optional[datetime] = Field(default=None, description="Run end time")
    
    statistics: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary stats like execution duration per agent")
