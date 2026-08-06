"""
Abstract BaseAgent defining the core contract for all MCP agents.
"""
from abc import ABC, abstractmethod
from typing import List, Any
from agents.context import AgentContext
from shared.artifacts import BaseArtifact

class BaseAgent(ABC):
    """
    The base class that every AI agent MUST inherit from.
    Enforces a strict execution contract, ensuring predictable pipelines and rollback support.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier/name of the agent (e.g., 'LegacyAnalyzer')."""
        pass
        
    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the agent accomplishes."""
        pass
        
    @property
    @abstractmethod
    def version(self) -> str:
        """Version string (e.g., '1.0.0')."""
        pass
        
    @property
    @abstractmethod
    def supported_tasks(self) -> List[str]:
        """List of task types this agent is authorized to handle."""
        pass

    @abstractmethod
    async def should_run(self, context: AgentContext, task: Any) -> bool:
        """Determines dynamically if the agent needs to execute for the given context."""
        pass

    @abstractmethod
    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        """Pre-flight check to ensure the agent has all required inputs before touching the LLM."""
        pass

    @abstractmethod
    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        """
        The core business logic of the agent.
        Interacts with the LLM and the Workspace to generate artifacts.
        """
        pass

    @abstractmethod
    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        """Post-flight check to ensure generated outputs adhere to expected schemas or constraints."""
        pass

    @abstractmethod
    async def rollback(self, context: AgentContext, task: Any) -> None:
        """
        Reverts any changes made by this agent. 
        Called by the pipeline if a downstream agent fails fatally.
        """
        pass

    @abstractmethod
    async def health_check(self, context: AgentContext) -> bool:
        """Diagnostic check to ensure the agent's specific dependencies (e.g., a specific DB) are healthy."""
        pass
