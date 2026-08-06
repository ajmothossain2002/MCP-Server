"""
MCP Tools Implementation.
Exposes migration capabilities via the FastMCP protocol.
"""
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Fallback to standalone fastmcp if official sdk path is different
    from fastmcp import FastMCP

from mcp.session import session_manager
from mcp.registry import run_single_agent

mcp = FastMCP("ERP Migration Server")

@mcp.tool()
async def create_session() -> str:
    """Create a new isolated migration session."""
    return session_manager.create_session()

@mcp.tool()
async def discover_module(session_id: str, module_name: str) -> dict:
    """Discover an ERP module."""
    await run_single_agent(session_id, "LegacyDiscoveryAgent", {"module_name": module_name})
    orch = session_manager.get_orchestrator(session_id)
    return orch.context.state.generated_artifacts[-1].model_dump()

@mcp.tool()
async def analyze_module(session_id: str, module_name: str) -> dict:
    """Analyze a legacy C++ module."""
    await run_single_agent(session_id, "LegacyAnalyzerAgent", {"module_name": module_name})
    orch = session_manager.get_orchestrator(session_id)
    return orch.context.shared_state["legacy_analysis"].model_dump()

@mcp.tool()
async def extract_business_rules(session_id: str, module_name: str) -> dict:
    """Extract business logic constraints."""
    await run_single_agent(session_id, "BusinessRuleExtractorAgent", {"module_name": module_name})
    orch = session_manager.get_orchestrator(session_id)
    return orch.context.shared_state["business_rules"].model_dump()

@mcp.tool()
async def plan_migration(session_id: str, module_name: str) -> dict:
    """Blueprint the python migration."""
    await run_single_agent(session_id, "MigrationPlannerAgent", {"module_name": module_name})
    orch = session_manager.get_orchestrator(session_id)
    return orch.context.shared_state["migration_plan"].model_dump()

@mcp.tool()
async def generate_module(session_id: str, module_name: str) -> list[dict]:
    """Generates all configured Python files."""
    agents = [
        "ModelGeneratorAgent", "SchemaGeneratorAgent", "ServiceGeneratorAgent",
        "RouteGeneratorAgent", "MigrationGeneratorAgent", "SeedGeneratorAgent"
    ]
    for agent_name in agents:
        await run_single_agent(session_id, agent_name, {"module_name": module_name})
        
    orch = session_manager.get_orchestrator(session_id)
    return [a.model_dump() for a in orch.context.state.generated_artifacts if getattr(a, "artifact_type", "") == "generated_file"]

@mcp.tool()
async def review_module(session_id: str, module_name: str) -> dict:
    """Runs the architectural ReviewAgent."""
    await run_single_agent(session_id, "ReviewAgent", {"module_name": module_name})
    orch = session_manager.get_orchestrator(session_id)
    return orch.context.shared_state["review_report"].model_dump()

@mcp.tool()
async def fix_module(session_id: str, module_name: str) -> list[dict]:
    """Runs the AutoFixAgent based on review results."""
    await run_single_agent(session_id, "AutoFixAgent", {"module_name": module_name})
    orch = session_manager.get_orchestrator(session_id)
    return [a.model_dump() for a in orch.context.state.generated_artifacts if getattr(a, "artifact_type", "") == "generated_file" and "fixed" in a.name]

@mcp.tool()
async def validate_module(session_id: str, module_name: str) -> dict:
    """Runs the ValidationAgent."""
    await run_single_agent(session_id, "ValidationAgent", {"module_name": module_name})
    orch = session_manager.get_orchestrator(session_id)
    return orch.context.shared_state["validation_report"].model_dump()

@mcp.tool()
async def migrate_module(session_id: str, module_name: str) -> dict:
    """Runs the complete end-to- natural loop Orchestrator."""
    orch = session_manager.get_orchestrator(session_id)
    result = await orch.execute_migration(module_name)
    return result.model_dump()

@mcp.tool()
async def status(session_id: str) -> dict:
    """Returns Current migration status."""
    return session_manager.get_session_info(session_id).model_dump()

@mcp.tool()
async def resume(session_id: str) -> dict:
    """Resume a migration."""
    orch = session_manager.get_orchestrator(session_id)
    await orch.resume()
    return session_manager.get_session_info(session_id).model_dump()

@mcp.tool()
async def cancel(session_id: str) -> dict:
    """Cancel a migration."""
    orch = session_manager.get_orchestrator(session_id)
    await orch.cancel()
    return session_manager.get_session_info(session_id).model_dump()

@mcp.tool()
async def sessions() -> list[dict]:
    """List migration sessions."""
    return [s.model_dump() for s in session_manager.list_sessions()]
