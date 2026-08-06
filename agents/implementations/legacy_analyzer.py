"""
Legacy Analyzer Agent.
Analyzes legacy files (C++, Proto, SQL) to extract business rules and schemas using OpenAI Structured Outputs.
Operates as the single source of truth for downstream code generation.
"""
import os
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from agents.base import BaseAgent
from agents.context import AgentContext
from shared.artifacts import BaseArtifact
from agents.implementations.legacy_discovery import DiscoveryResult
from shared.prompts import prompt_manager
from scripts.filesystem import read

# ---------------------------------------------------------------------------
# Models for Structured Output (Mapped to LLM JSON Schema)
# ---------------------------------------------------------------------------

class ColumnDef(BaseModel):
    name: str
    data_type: str
    is_nullable: bool = False
    is_primary_key: bool = False
    description: str = ""

class TableDef(BaseModel):
    name: str
    columns: List[ColumnDef] = Field(default_factory=list)
    foreign_keys: List[str] = Field(default_factory=list)
    relationships: List[str] = Field(default_factory=list)

class RpcDef(BaseModel):
    name: str
    request_message: str
    response_message: str
    description: str = ""

class ServiceDef(BaseModel):
    name: str
    rpcs: List[RpcDef] = Field(default_factory=list)

class MessageDef(BaseModel):
    name: str
    fields: Dict[str, str] = Field(default_factory=dict, description="Field name to type mapping")

class LLMExtraction(BaseModel):
    """Pydantic model used explicitly for LLM structured output parsing."""
    services: List[ServiceDef] = Field(default_factory=list)
    messages: List[MessageDef] = Field(default_factory=list)
    enums: Dict[str, List[str]] = Field(default_factory=dict)
    tables: List[TableDef] = Field(default_factory=list)
    business_rules: List[str] = Field(default_factory=list)
    validation_rules: List[str] = Field(default_factory=list)
    record_series_usage: List[str] = Field(default_factory=list)
    audit_usage: List[str] = Field(default_factory=list)
    permission_requirements: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)

class LegacyModuleAnalysis(BaseArtifact):
    """Strongly typed output artifact containing all extracted knowledge."""
    artifact_type: str = Field(default="legacy_analysis", frozen=True)
    module_name: str
    
    # Domain Knowledge
    services: List[ServiceDef] = Field(default_factory=list)
    messages: List[MessageDef] = Field(default_factory=list)
    enums: Dict[str, List[str]] = Field(default_factory=dict)
    tables: List[TableDef] = Field(default_factory=list)
    
    # Logic & Policies
    business_rules: List[str] = Field(default_factory=list)
    validation_rules: List[str] = Field(default_factory=list)
    record_series_usage: List[str] = Field(default_factory=list)
    audit_usage: List[str] = Field(default_factory=list)
    permission_requirements: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent Implementation
# ---------------------------------------------------------------------------

class LegacyAnalyzerAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "LegacyAnalyzerAgent"
        
    @property
    def description(self) -> str:
        return "Analyzes legacy code and extracts a strictly typed schema of business rules and definitions."
        
    @property
    def version(self) -> str:
        return "1.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["analyze_module"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        return "discovery_result" in context.shared_state

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        discovery = context.shared_state.get("discovery_result")
        return isinstance(discovery, DiscoveryResult)

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        discovery: DiscoveryResult = context.shared_state["discovery_result"]
        module_name = discovery.module_name
        
        context.logger.info(f"Analyzing legacy context for module: {module_name}")
        
        # 1. Read files discovered by the previous agent
        legacy_content = ""
        files_to_read = discovery.legacy_files + discovery.database_files + discovery.documentation_files
        
        for file_path in files_to_read:
            if os.path.exists(file_path):
                content = read(file_path)
                legacy_content += f"\n\n--- FILE: {os.path.basename(file_path)} ---\n"
                legacy_content += content
                
        # 2. Leverage ContextManager for overarching domain knowledge context
        bundle = context.knowledge.build_context(module_name, max_tokens=15000)
        domain_knowledge = bundle.format_as_text()
        
        # 3. Use PromptManager (Fallback to inline if templates aren't on disk yet)
        try:
            system_prompt = prompt_manager.render_prompt("legacy_analyzer_system", {})
        except Exception:
            system_prompt = (
                "You are an expert ERP reverse engineer. Analyze the provided legacy C++, Proto, and SQL files. "
                "Extract services, messages, tables, business rules, and constraints with high precision."
            )

        try:
            user_prompt = prompt_manager.render_prompt("legacy_analyzer_user", {
                "module_name": module_name,
                "legacy_content": legacy_content,
                "domain_knowledge": domain_knowledge
            })
        except Exception:
            user_prompt = (
                f"Analyze the ERP module: {module_name}\n\n"
                f"=== DOMAIN KNOWLEDGE ===\n{domain_knowledge}\n\n"
                f"=== LEGACY CODE ===\n{legacy_content}"
            )

        # 4. Call the LLM to perform Structured Output parsing
        context.logger.info("Calling LLM for structured analysis...")
        
        response = await context.llm.structured_generate(
            response_model=LLMExtraction,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0 # Deterministic analysis, no hallucinations
        )
        
        extracted: LLMExtraction = response.structured_output
        
        # 5. Pack into our standardized Artifact model
        safe_name = module_name.lower().replace(' ', '_')
        analysis = LegacyModuleAnalysis(
            name=f"analysis_{safe_name}",
            path=f"analysis_{safe_name}.json",
            source=self.name,
            module_name=module_name,
            
            services=extracted.services,
            messages=extracted.messages,
            enums=extracted.enums,
            tables=extracted.tables,
            
            business_rules=extracted.business_rules,
            validation_rules=extracted.validation_rules,
            record_series_usage=extracted.record_series_usage,
            audit_usage=extracted.audit_usage,
            permission_requirements=extracted.permission_requirements,
            dependencies=extracted.dependencies,
            
            # Persist raw JSON string as the artifact content for the Workspace
            content=extracted.model_dump_json(indent=2)
        )
        
        # 6. Save analysis artifact to the Workspace
        context.workspace.write_artifact(context.migration_id, "output", analysis)
        
        # 7. Provide analysis in shared_state for the downstream Python Generator
        context.shared_state["legacy_analysis"] = analysis
        
        return [analysis]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) == 1 and isinstance(artifacts[0], LegacyModuleAnalysis)

    async def rollback(self, context: AgentContext, task: Any) -> None:
        pass

    async def health_check(self, context: AgentContext) -> bool:
        return True
