"""
AgentRegistry for dynamically discovering and loading agents.
Prevents hardcoded imports and allows for future plugin extensibility.
"""
import importlib
import pkgutil
from typing import Dict, List, Type
from agents.base import BaseAgent
from config.logging import get_logger

logger = get_logger(__name__)

class AgentRegistry:
    """
    In-memory registry of all available agents.
    Provides dynamic discovery without requiring massive import chains.
    """
    
    def __init__(self):
        # Maps agent name to the agent class
        self._agents: Dict[str, Type[BaseAgent]] = {}
        
    def register(self, agent_class: Type[BaseAgent]) -> None:
        """Explicitly registers an agent class into the registry."""
        try:
            # Instantiate briefly to grab the required name property
            agent_instance = agent_class()
            self._agents[agent_instance.name] = agent_class
            logger.debug(f"Registered agent: {agent_instance.name} (v{agent_instance.version})")
        except Exception as e:
            logger.error(f"Failed to register agent {agent_class.__name__}: {e}")

    def unregister(self, agent_name: str) -> None:
        """Removes an agent from the registry."""
        if agent_name in self._agents:
            del self._agents[agent_name]
            
    def get(self, agent_name: str) -> Type[BaseAgent]:
        """Retrieves an agent class by name."""
        return self._agents.get(agent_name)
        
    def list(self) -> List[str]:
        """Returns a list of all registered agent names."""
        return list(self._agents.keys())
        
    def discover(self, package_name: str = "agents.implementations") -> None:
        """
        Dynamically scans a Python package and registers any class inheriting from BaseAgent.
        This enables drop-in plugin support in the future.
        """
        try:
            package = importlib.import_module(package_name)
            for _, name, is_pkg in pkgutil.iter_modules(package.__path__):
                if not is_pkg:
                    module = importlib.import_module(f"{package_name}.{name}")
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        # Ensure it's a class, a subclass of BaseAgent, but not the abstract base itself
                        if isinstance(attr, type) and issubclass(attr, BaseAgent) and attr is not BaseAgent:
                            self.register(attr)
        except ImportError:
            logger.warning(f"Could not discover agents in '{package_name}'. Package may not exist yet.")

# Singleton registry
agent_registry = AgentRegistry()
