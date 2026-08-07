"""
Legacy Discovery Agent.
Responsible for finding all files related to a specific ERP module.
Operates deterministically without calling the LLM.
"""
import os
import re
from typing import List, Any, Dict
from pydantic import Field

from agents.base import BaseAgent
from agents.context import AgentContext
from shared.artifacts import BaseArtifact
from knowledge.file_loader import load_files

class DiscoveryResult(BaseArtifact):
    artifact_type: str = Field(default="discovery_result", frozen=True)
    module_name: str
    legacy_files: List[str] = Field(default_factory=list)
    python_files: List[str] = Field(default_factory=list)
    documentation_files: List[str] = Field(default_factory=list)
    database_files: List[str] = Field(default_factory=list)
    configuration_files: List[str] = Field(default_factory=list)
    missing_files: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    statistics: Dict[str, Any] = Field(default_factory=dict)
    total_estimated_tokens: int = Field(default=0)

class LegacyDiscoveryAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "LegacyDiscoveryAgent"
        
    @property
    def description(self) -> str:
        return "Discovers and groups all legacy and target files related to an ERP module."
        
    @property
    def version(self) -> str:
        return "1.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["discover_module"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        return isinstance(task, dict) and "module_name" in task

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        return bool(task.get("module_name"))

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        import os
        
        module_name = task.get("module_name", "unknown")
        proto_path = task.get("proto_path", "")
        hpp_path = task.get("hpp_path", "")
        cpp_path = task.get("cpp_path", "")
        db_source = task.get("database_source", {})
        
        context.logger.info(f"Validating explicitly provided files for module: {module_name}")
        
        safe_name = module_name.lower().replace(' ', '_')
        result = DiscoveryResult(
            name=f"discovery_{safe_name}",
            path=f"discovery_{safe_name}.json",
            source=self.name,
            module_name=module_name
        )
        
        missing = []
        
        # Helper to process a file
        def _process_file(path: str, label: str):
            if path and os.path.isfile(path):
                context.logger.info(f"✔ {label} Found")
                result.legacy_files.append(path)
                try:
                    context.workspace.backup_original(context.migration_id, path)
                except Exception as e:
                    context.logger.warning(f"Could not copy {path} to workspace: {e}")
            else:
                missing.append(f"{label} ({path})")

        _process_file(proto_path, "Proto")
        _process_file(hpp_path, "Header")
        _process_file(cpp_path, "Source")
                
        if missing:
            error_msg = f"Missing required files for module '{module_name}': {', '.join(missing)}"
            context.logger.error(error_msg)
            raise ValueError(error_msg)
            
        if db_source.get("type") == "initializer":
            result.database_files.append(db_source.get("path"))
            
        # Build Context Explicitly
        # Pass the files to the ContextManager which now accepts explicit files
        explicit_files = result.legacy_files + result.database_files
        
        bundle = context.knowledge.build_context_explicit(module_name, explicit_files, db_source, max_tokens=100000)
        
        result.statistics = {
            "total_files": len(result.legacy_files) + len(result.python_files) + len(result.documentation_files) + len(result.database_files),
            "legacy_count": len(result.legacy_files),
            "python_count": len(result.python_files),
            "docs_count": len(result.documentation_files),
            "db_count": len(result.database_files)
        }
        
        result.content = f"Validated explicitly supplied files for module {module_name}."
        
        # Write Output
        context.workspace.write_artifact(context.migration_id, "output", result)
        
        # Feed the discovery result back into the shared state for downstream agents
        context.shared_state["discovery_result"] = result
        context.shared_state["context_bundle"] = bundle
        
        return [result]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) == 1 and isinstance(artifacts[0], DiscoveryResult)

    async def rollback(self, context: AgentContext, task: Any) -> None:
        # Discovery agent doesn't mutate legacy code, no complex rollback needed.
        pass

    async def health_check(self, context: AgentContext) -> bool:
        return True
