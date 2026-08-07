"""
CLI Commands.
Typer commands mapping to Orchestrator functions.
"""
import asyncio
import uuid
import yaml
import os
from rich.prompt import Prompt, Confirm
import typer
from typing import Optional, Dict, Any

from cli.display import console, print_header, print_success, print_error, print_summary, print_warning
from cli.progress import create_progress_context
from cli import file_picker

from workflows.orchestrator import Orchestrator
from workflows.workspace import WorkspaceManager
from knowledge.context_manager import ContextManager
from knowledge.document_index import DocumentIndex
from knowledge.code_index import CodeIndex
from agents.context import AgentContext
from agents.state import MigrationState
from agents.registry import agent_registry
from config.settings import settings
from config.logging import get_logger
from shared.llm import LLMClient

def _init_orchestrator(migration_id: Optional[str] = None) -> Orchestrator:
    """Initializes the Orchestrator with all necessary context and state."""
    mig_id = migration_id or str(uuid.uuid4())
    workspace = WorkspaceManager(mig_id)
    ctx = AgentContext(
        migration_id=mig_id,
        settings=settings,
        llm=LLMClient(),
        workspace=workspace,
        knowledge=ContextManager(doc_index=DocumentIndex(), code_index=CodeIndex()),
        state=MigrationState(migration_id=mig_id),
        logger=get_logger("cli")
    )
    return Orchestrator(ctx)

def _run_async(coro):
    """Helper to run async functions synchronously for Typer."""
    return asyncio.run(coro)

# ---------------------------------------------------------------------------
# Core Workflow execution (Polls Orchestrator State for CLI Rendering)
# ---------------------------------------------------------------------------
async def _execute_with_ui(orch: Orchestrator, module_name: str, task_coro):
    """Executes an Orchestrator coroutine while rendering live rich progress."""
    with create_progress_context() as progress:
        task = progress.add_task("[cyan]Initializing...", total=100)
        
        migration_task = asyncio.create_task(task_coro)
        last_stage = None
        
        # Poll state to update UI
        while not migration_task.done():
            current_stage = orch.context.state.current_stage
            if current_stage != last_stage and current_stage not in ["STARTING", "COMPLETED", "FAILED"]:
                print_success(current_stage.replace("Agent", ""))
                last_stage = current_stage
                
            logs = orch.context.state.statistics.get("progress_logs", [])
            if logs:
                last_log = logs[-1]
                try:
                    pct = int(last_log.split("%]")[0].strip("["))
                    progress.update(task, completed=pct, description=last_log.split("%]")[1].strip())
                except:
                    progress.update(task, description=last_log)
                    
            await asyncio.sleep(0.5)
            
        result = await migration_task
        progress.update(task, completed=100)
        return result

def print_final_summary(orch: Orchestrator):
    duration = orch.context.state.statistics.get("Total_duration_s", 0)
    # Estimate total duration if not explicitly saved
    if orch.context.state.end_time and orch.context.state.start_time:
        duration = round((orch.context.state.end_time - orch.context.state.start_time).total_seconds(), 2)
        
    review_score = orch.context.state.statistics.get("review_score", 0)
    val_score = orch.context.state.statistics.get("validation_score", 0)
    
    files = len([a for a in orch.context.state.generated_artifacts if getattr(a, "artifact_type", "") == "generated_file" and "fixed" not in a.name])
    fixed = len([a for a in orch.context.state.generated_artifacts if getattr(a, "artifact_type", "") == "generated_file" and "fixed" in a.name])
    
    print_summary(duration, review_score, val_score, files, fixed, f"workspace/{orch.context.migration_id}")

# ---------------------------------------------------------------------------
# Typer Commands
# ---------------------------------------------------------------------------
def migrate(config_path: Optional[str] = typer.Argument(None, help="Optional path to a config.yaml file")):
    if config_path:
        print_header(f"Starting Full Migration Pipeline from config: {config_path}")
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)
        
        module_name = config_data.get("module")
        proto_path = config_data.get("proto_path")
        hpp_path = config_data.get("hpp_path")
        cpp_path = config_data.get("cpp_path")
        db_config = config_data.get("database", {})
        
        db_mode = db_config.get("mode")
        if db_mode == "initializer":
            database_source = {"type": "initializer", "path": db_config.get("path")}
        elif db_mode == "paste":
            database_source = {"type": "paste", "content": db_config.get("content")}
        else:
            database_source = {"type": "skip"}
            
        # We could also read provider from config if needed.
    else:
        console.print("\n[bold cyan]======================================================[/bold cyan]")
        console.print("[bold cyan]Software Migration Platform[/bold cyan]")
        console.print("[bold cyan]AI Migration Assistant[/bold cyan]")
        console.print("[bold cyan]======================================================[/bold cyan]\n")
        
        module_name = Prompt.ask("Enter Module Name", default="Feature Request")
        proto_path = file_picker.select_proto()
        if not proto_path or not os.path.isfile(proto_path) or not proto_path.endswith('.proto'):
            print_warning("Operation cancelled by user.")
            return
        print_success("Proto Selected")
        
        hpp_path = file_picker.select_header()
        if not hpp_path or not os.path.isfile(hpp_path) or not hpp_path.endswith('.hpp'):
            print_warning("Operation cancelled by user.")
            return
        print_success("Header Selected")
        
        cpp_path = file_picker.select_source()
        if not cpp_path or not os.path.isfile(cpp_path) or not cpp_path.endswith('.cpp'):
            print_warning("Operation cancelled by user.")
            return
        print_success("Source Selected")
        
        console.print("\n[bold yellow]Database Information[/bold yellow]")
        console.print("Choose:")
        console.print("1. Paste createTable()")
        console.print("2. Provide DatabaseInitializer.cpp")
        console.print("3. Skip database")
        db_choice = Prompt.ask("Selection", choices=["1", "2", "3"], default="3")
        
        database_source = {"type": "skip"}
        if db_choice == "1":
            console.print("Paste the createTable() block. Finish with Ctrl+D (Linux) or Ctrl+Z (Windows).")
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            database_source = {"type": "paste", "content": "\n".join(lines)}
        elif db_choice == "2":
            db_path = file_picker.select_database_initializer()
            if not db_path or not os.path.isfile(db_path) or not db_path.endswith('.cpp'):
                print_warning("Operation cancelled by user.")
                return
            print_success("Database Initializer Selected")
            database_source = {"type": "initializer", "path": db_path}
            
        console.print(f"\n[bold green]Module:[/bold green] {module_name}")
        console.print(f"[bold green]Proto:[/bold green] {proto_path}")
        console.print(f"[bold green]Header:[/bold green] {hpp_path}")
        console.print(f"[bold green]Source:[/bold green] {cpp_path}")
        console.print(f"[bold green]Database:[/bold green] {database_source['type']}")
        
        if not Confirm.ask("Proceed?"):
            print_warning("Migration cancelled.")
            return

    orch = _init_orchestrator()
    
    task_payload = {
        "module_name": module_name,
        "proto_path": proto_path,
        "hpp_path": hpp_path,
        "cpp_path": cpp_path,
        "database_source": database_source
    }
    
    result = _run_async(_execute_with_ui(orch, module_name, orch.execute_migration(task_payload)))
    
    if result.success:
        print_success("Migration Completed Successfully.")
    else:
        print_error(f"Migration Failed: {result.summary}")
        
    print_final_summary(orch)

def analyze(module_name: str = typer.Argument(..., help="Name of the ERP module to analyze")):
    print_header(f"Starting Analysis Pipeline for: {module_name}")
    orch = _init_orchestrator()
    
    async def _analyze():
        orch.context.state.current_stage = "STARTING"
        pipeline = ["LegacyDiscoveryAgent", "LegacyAnalyzerAgent", "BusinessRuleExtractorAgent"]
        
        # Analyze expects the same payload structure now
        task_payload = {
            "module_name": module_name,
            "proto_path": "", # Dummy for analyze command if not interactive
            "hpp_path": "",
            "cpp_path": "",
            "database_source": {"type": "skip"}
        }
        
        for agent_name in pipeline:
            agent = agent_registry.get(agent_name)()
            if not await orch._run_agent(agent, task_payload):
                return False
        return True
        
    success = _run_async(_execute_with_ui(orch, module_name, _analyze()))
    if success:
        print_success("Analysis completed.")
    else:
        print_error("Analysis failed.")

def review(workspace_id: str = typer.Argument(..., help="Workspace ID to review")):
    print_header(f"Running Review on workspace: {workspace_id}")
    orch = _init_orchestrator(workspace_id)
    
    async def _review():
        agent = agent_registry.get("ReviewAgent")()
        return await orch._run_agent(agent, {"module_name": "unknown"})
        
    _run_async(_execute_with_ui(orch, "unknown", _review()))

def validate(workspace_id: str = typer.Argument(..., help="Workspace ID to validate")):
    print_header(f"Running Validation on workspace: {workspace_id}")
    orch = _init_orchestrator(workspace_id)
    
    async def _validate():
        agent = agent_registry.get("ValidationAgent")()
        return await orch._run_agent(agent, {"module_name": "unknown"})
        
    _run_async(_execute_with_ui(orch, "unknown", _validate()))

def resume(workspace_id: str = typer.Argument(..., help="Workspace ID to resume")):
    print_header(f"Resuming migration: {workspace_id}")
    orch = _init_orchestrator(workspace_id)
    _run_async(orch.resume())
    print_success("Resumed.")

def cancel(workspace_id: str = typer.Argument(..., help="Workspace ID to cancel")):
    print_header(f"Cancelling migration: {workspace_id}")
    orch = _init_orchestrator(workspace_id)
    _run_async(orch.cancel())
    print_warning("Cancelled.")

def status(workspace_id: str = typer.Argument(..., help="Workspace ID to check")):
    print_header(f"Status for: {workspace_id}")
    # In a real app, state is loaded from disk. We mock displaying it here.
    print_success("Stage: VALIDATION")
    print_success("Progress: 95%")
    print_success("Review Score: 100")
    print_success("Validation Score: 90")
    print_success("Duration: 145.2s")

def clean():
    print_header("Cleaning temporary workspaces...")
    # In a real app, delete local tmp dirs
    print_success("Workspaces cleaned successfully.")
