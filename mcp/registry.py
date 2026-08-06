"""
MCP Internal Agent Registry Router.
Routes single-agent executions through the Orchestrator to ensure
we NEVER call agents directly and state is perfectly maintained.
"""
from mcp.session import session_manager
from agents.registry import agent_registry

async def run_single_agent(session_id: str, agent_name: str, task: dict):
    """
    Looks up the agent from the global registry and routes it strictly through 
    the Orchestrator's execution wrapper `_run_agent`.
    This guarantees isolated workspace persistence without modifying the Orchestrator.
    """
    orch = session_manager.get_orchestrator(session_id)
    agent_class = agent_registry.get(agent_name)
    if not agent_class:
        raise ValueError(f"Agent {agent_name} not found in registry.")
        
    agent = agent_class()
    # Execute through orchestrator
    success = await orch._run_agent(agent, task)
    if not success:
        raise RuntimeError(f"Agent {agent_name} execution failed.")
    return True
