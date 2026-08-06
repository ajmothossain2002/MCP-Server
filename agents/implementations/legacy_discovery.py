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
        module_name = task["module_name"]
        context.logger.info(f"Discovering files for module: {module_name}")
        
        safe_name = module_name.lower().replace(' ', '_')
        result = DiscoveryResult(
            name=f"discovery_{safe_name}",
            path=f"discovery_{safe_name}.json",
            source=self.name,
            module_name=module_name
        )
        
        variants = self._generate_variants(module_name)
        matched_paths = set()
        
        # 1. Use ContextManager to request semantic context and test knowledge engine
        bundle = context.knowledge.build_context(module_name, max_tokens=100000)
        for doc in bundle.documents:
            matched_paths.add(doc.path)
        for sym in bundle.code_symbols:
            matched_paths.add(sym.path)
            
        # 2. Use Search Engine dynamically
        for variant in variants:
            search_results = context.knowledge.search_engine.search(variant, limit=100)
            for res in search_results:
                matched_paths.add(res.path)
                
        # 3. Use FileLoader directly for broad filesystem scans (since not everything is indexed)
        cpp_path = context.settings.paths.erp_cpp_path
        py_path = context.settings.paths.erp_python_path
        docs_path = context.settings.paths.docs_path
        
        all_files = []
        if os.path.exists(cpp_path):
            all_files.extend(load_files(cpp_path))
        if os.path.exists(py_path):
            all_files.extend(load_files(py_path))
        if os.path.exists(docs_path):
            all_files.extend(load_files(docs_path))
            
        for file_obj in all_files:
            if self._matches_variants(file_obj.path, variants) or self._matches_variants(file_obj.filename, variants):
                matched_paths.add(file_obj.path)
                result.total_estimated_tokens += file_obj.estimated_tokens
                
        # Classify discovered files
        for p in matched_paths:
            ext = os.path.splitext(p)[1].lower()
            if ext in {".cpp", ".hpp", ".h", ".proto"}:
                result.legacy_files.append(p)
            elif ext in {".py", ".alembic"}:
                result.python_files.append(p)
            elif ext in {".md", ".txt"}:
                result.documentation_files.append(p)
            elif ext in {".sql"}:
                result.database_files.append(p)
            elif ext in {".json", ".yaml", ".yml", ".ini"}:
                result.configuration_files.append(p)
                
        # Heuristics for missing files
        if not result.legacy_files:
            result.warnings.append("No legacy C++ or Proto files found for this module.")
            
        py_names = [os.path.basename(f) for f in result.python_files]
        for expected in ["models.py", "schemas.py", "service.py", "router.py"]:
            if expected not in py_names:
                result.missing_files.append(expected)

        # Statistics
        result.statistics = {
            "total_files": len(matched_paths),
            "legacy_count": len(result.legacy_files),
            "python_count": len(result.python_files),
            "docs_count": len(result.documentation_files),
            "db_count": len(result.database_files)
        }
        
        result.content = f"Discovered {len(matched_paths)} files for module {module_name}."
        
        # Write Output
        context.workspace.write_artifact(context.migration_id, "output", result)
        
        # Feed the discovery result back into the shared state for downstream agents
        context.shared_state["discovery_result"] = result
        
        return [result]

    def _generate_variants(self, name: str) -> List[str]:
        """Generates fuzzy match strings. Example: 'Sales Activity' -> ['sales activity', 'SalesActivity', ...]"""
        base = name.lower()
        parts = base.split()
        return [
            base,
            "_".join(parts),
            "".join(parts),
            "-".join(parts),
            "".join(p.capitalize() for p in parts)
        ]
        
    def _matches_variants(self, text: str, variants: List[str]) -> bool:
        """Checks if text contains any of the fuzzy match variants."""
        text_lower = text.lower()
        for variant in variants:
            if variant.lower() in text_lower:
                return True
        return False

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) == 1 and isinstance(artifacts[0], DiscoveryResult)

    async def rollback(self, context: AgentContext, task: Any) -> None:
        # Discovery agent doesn't mutate legacy code, no complex rollback needed.
        pass

    async def health_check(self, context: AgentContext) -> bool:
        return True
