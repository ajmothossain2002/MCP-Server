"""
Migration Planner Agent.
Consumes DiscoveryResult, LegacyModuleAnalysis, and BusinessRuleSet.
Produces a highly detailed, strongly typed MigrationPlan identifying what files to generate, 
modify, review, and validate, including topological generation orders.
"""
from typing import List, Any
from pydantic import BaseModel, Field

from agents.base import BaseAgent
from agents.context import AgentContext
from shared.artifacts import BaseArtifact
from agents.implementations.legacy_discovery import DiscoveryResult
from agents.implementations.legacy_analyzer import LegacyModuleAnalysis
from agents.implementations.business_rule_extractor import BusinessRuleSet
from shared.prompts import prompt_manager

# ---------------------------------------------------------------------------
# Models for Structured Output
# ---------------------------------------------------------------------------

class FileTarget(BaseModel):
    filename: str = Field(description="Name of the file to generate (e.g., models.py, schemas.py)")
    purpose: str = Field(description="Brief explanation of why this file is needed")
    dependencies: List[str] = Field(default_factory=list, description="Other files that must be generated before this one")

class ModificationTarget(BaseModel):
    filename: str = Field(description="Name of the existing file to modify (e.g., app.py, RBAC seed)")
    purpose: str = Field(description="Brief explanation of why it needs modification")
    changes_required: str = Field(description="What needs to change")

class LLMExtraction(BaseModel):
    """Pydantic model used explicitly for LLM structured output parsing."""
    generate_files: List[FileTarget] = Field(default_factory=list)
    modify_files: List[ModificationTarget] = Field(default_factory=list)
    
    generation_order: List[str] = Field(default_factory=list, description="Strict topological ordering of filenames to generate")
    review_order: List[str] = Field(default_factory=list, description="Sequence of manual/agent review steps")
    validation_order: List[str] = Field(default_factory=list, description="Sequence of validation steps (Docker, Alembic, Swagger, Tests)")

class MigrationPlan(BaseArtifact):
    """Strongly typed output artifact containing the blueprint for the generation phase."""
    artifact_type: str = Field(default="migration_plan", frozen=True)
    module_name: str
    
    generate_files: List[FileTarget] = Field(default_factory=list)
    modify_files: List[ModificationTarget] = Field(default_factory=list)
    
    generation_order: List[str] = Field(default_factory=list)
    review_order: List[str] = Field(default_factory=list)
    validation_order: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent Implementation
# ---------------------------------------------------------------------------

class MigrationPlannerAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "MigrationPlannerAgent"
        
    @property
    def description(self) -> str:
        return "Determines the required target files, modifications, and exact sequence for generation and validation."
        
    @property
    def version(self) -> str:
        return "2.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["plan_migration"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        return all(key in context.shared_state for key in ["discovery_result", "legacy_analysis", "business_rules"])

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        discovery = context.shared_state.get("discovery_result")
        analysis = context.shared_state.get("legacy_analysis")
        rules = context.shared_state.get("business_rules")
        
        return (
            isinstance(discovery, DiscoveryResult) and
            isinstance(analysis, LegacyModuleAnalysis) and
            isinstance(rules, BusinessRuleSet)
        )

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        discovery: DiscoveryResult = context.shared_state["discovery_result"]
        analysis: LegacyModuleAnalysis = context.shared_state["legacy_analysis"]
        rules: BusinessRuleSet = context.shared_state["business_rules"]
        module_name = analysis.module_name
        
        context.logger.info(f"Planning migration generation phase for module: {module_name}")
        
        # 1. Fetch project conventions from Knowledge engine
        bundle = context.knowledge.build_context("Python Architecture Conventions Review Guidelines", max_tokens=10000)
        project_conventions = bundle.format_as_text()
        
        # 2. Serialize inputs
        discovery_content = discovery.model_dump_json(indent=2)
        analysis_content = analysis.model_dump_json(indent=2)
        rules_content = rules.model_dump_json(indent=2)
        
        # 3. Render Prompts
        try:
            system_prompt = prompt_manager.render_prompt("migration_planner_system", {})
        except Exception:
            system_prompt = (
                "You are the Lead Software Architect. Given the discovery results, module analysis, business rules, and project conventions, "
                "determine the exact list of Python files to generate (e.g., models.py, schemas.py, service.py, routes.py, migration.py, seed.py, tests) "
                "and files to modify (e.g., app.py, __init__.py). Provide strict generation, review, and validation orders (Docker, Alembic, Swagger, Tests)."
            )

        try:
            user_prompt = prompt_manager.render_prompt("migration_planner_user", {
                "module_name": module_name,
                "discovery_content": discovery_content,
                "analysis_content": analysis_content,
                "rules_content": rules_content,
                "project_conventions": project_conventions
            })
        except Exception:
            user_prompt = (
                f"Design the generation plan for the ERP module: {module_name}\n\n"
                f"=== DISCOVERY ===\n{discovery_content}\n\n"
                f"=== LEGACY ANALYSIS ===\n{analysis_content}\n\n"
                f"=== BUSINESS RULES ===\n{rules_content}\n\n"
                f"=== ARCHITECTURE CONVENTIONS ===\n{project_conventions}"
            )

        # 4. Call the LLM with structured output
        context.logger.info("Calling LLM to generate architectural Migration Plan...")
        
        response = await context.llm.structured_generate(
            response_model=LLMExtraction,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0 # Strict determinism for architectural plans
        )
        
        extracted: LLMExtraction = response.structured_output
        
        # 5. Pack into Artifact
        safe_name = module_name.lower().replace(' ', '_')
        plan = MigrationPlan(
            name=f"migration_plan_{safe_name}",
            path="migration_plan.json", # Standardized exact output name required by prompt
            source=self.name,
            module_name=module_name,
            
            generate_files=extracted.generate_files,
            modify_files=extracted.modify_files,
            generation_order=extracted.generation_order,
            review_order=extracted.review_order,
            validation_order=extracted.validation_order,
            
            content=extracted.model_dump_json(indent=2)
        )
        
        # 6. Save directly to the workspace output directory
        context.workspace.write_artifact(context.migration_id, "output", plan)
        
        # Expose to downstream code generators
        context.shared_state["migration_plan"] = plan
        
        return [plan]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) == 1 and isinstance(artifacts[0], MigrationPlan)

    async def rollback(self, context: AgentContext, task: Any) -> None:
        pass

    async def health_check(self, context: AgentContext) -> bool:
        return True
