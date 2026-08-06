"""
AgentContext passed to every agent during execution.
Uses explicit dependency injection to completely avoid global state.
"""
import logging
from typing import Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from config.settings import Settings
from shared.llm import LLMClient
from workflows.workspace import WorkspaceManager
from knowledge.context_manager import ContextManager
from agents.state import MigrationState

class AgentContext(BaseModel):
    """
    The universal context bundle provided to every agent.
    It encapsulates all infrastructure services, the workspace, and the shared state.
    """
    migration_id: str = Field(description="The active workspace ID")
    
    # Injected dependencies
    settings: Settings
    llm: LLMClient
    workspace: WorkspaceManager
    knowledge: ContextManager
    state: MigrationState
    logger: logging.Logger
    
    # Arbitrary shared memory for agents to pass data down the pipeline
    shared_state: Dict[str, Any] = Field(default_factory=dict)
    
    # Metadata about the execution environment
    execution_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
