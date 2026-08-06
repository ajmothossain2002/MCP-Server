"""
Review Agent.
Quality gate that strictly evaluates generated Python code against 
enterprise architectural conventions and legacy business rules.
"""
from typing import List, Any
from pydantic import BaseModel, Field

from agents.base import BaseAgent
from agents.context import AgentContext
from shared.artifacts import BaseArtifact, GeneratedFile
from agents.implementations.legacy_analyzer import LegacyModuleAnalysis
from agents.implementations.business_rule_extractor import BusinessRuleSet
from shared.prompts import prompt_manager

# ---------------------------------------------------------------------------
# Models for Structured Output
# ---------------------------------------------------------------------------

class Issue(BaseModel):
    file: str = Field(description="Name of the file containing the issue")
    description: str = Field(description="Detailed explanation of the problem")
    rule_violated: str = Field(description="The specific architectural or business rule violated")

class LLMReviewExtraction(BaseModel):
    """Pydantic model used explicitly for LLM structured output parsing."""
    score: int = Field(ge=0, le=100, description="Overall quality score out of 100")
    critical_issues: List[Issue] = Field(default_factory=list, description="Must fix issues preventing migration")
    warnings: List[Issue] = Field(default_factory=list)
    suggestions: List[Issue] = Field(default_factory=list)
    business_rule_violations: List[Issue] = Field(default_factory=list, description="Failures to implement legacy logic")
    architecture_violations: List[Issue] = Field(default_factory=list, description="Failures to follow project conventions")
    files_reviewed: List[str] = Field(default_factory=list)

class ReviewReport(BaseArtifact):
    """Strongly typed output artifact containing the final review."""
    artifact_type: str = Field(default="review_report", frozen=True)
    module_name: str
    
    score: int
    critical_issues: List[Issue] = Field(default_factory=list)
    warnings: List[Issue] = Field(default_factory=list)
    suggestions: List[Issue] = Field(default_factory=list)
    business_rule_violations: List[Issue] = Field(default_factory=list)
    architecture_violations: List[Issue] = Field(default_factory=list)
    files_reviewed: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent Implementation
# ---------------------------------------------------------------------------

class ReviewAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "ReviewAgent"
        
    @property
    def description(self) -> str:
        return "Strictly reviews all generated artifacts against architectural rules and business requirements."
        
    @property
    def version(self) -> str:
        return "1.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["review_generation"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        # Run if any files were generated in the pipeline
        return len([a for a in context.state.generated_artifacts if getattr(a, "artifact_type", "") == "generated_file"]) > 0

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        return "legacy_analysis" in context.shared_state and "business_rules" in context.shared_state

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        analysis: LegacyModuleAnalysis = context.shared_state["legacy_analysis"]
        rules: BusinessRuleSet = context.shared_state["business_rules"]
        module_name = analysis.module_name
        
        context.logger.info(f"Initiating comprehensive architectural code review for module: {module_name}")
        
        # 1. Fetch all generated code from the pipeline state
        generated_files = [a for a in context.state.generated_artifacts if getattr(a, "artifact_type", "") == "generated_file"]
        if not generated_files:
            context.logger.warning("No generated files found to review.")
            return []
            
        generated_code_dump = "\n".join([f"--- FILE: {f.name} ({f.path}) ---\n{f.content}" for f in generated_files])
        
        # 2. Fetch GROUND TRUTH architecture (Company, Leave, Employee, Record Series)
        # We explicitly never compare generated code against itself, only against proven production references
        bundle = context.knowledge.build_context("Company Leave Employee Record Series architecture standards rules", max_tokens=25000)
        ground_truth = bundle.format_as_text()
        
        # 3. Serialize logic constraints
        analysis_content = analysis.model_dump_json(indent=2)
        rules_content = rules.model_dump_json(indent=2)
        
        # 4. Render Prompts
        try:
            system_prompt = prompt_manager.render_prompt("review_agent_system", {})
        except Exception:
            system_prompt = (
                "You are the Senior Principal ERP Architect. Your job is to strictly review generated Python code "
                "against existing production modules (Company, Leave, Employee) and legacy business rules. "
                "Do NOT modify or fix the code. ONLY review it. "
                "Check explicitly for:\n"
                "- models.py: SQLAlchemy 2.0, UUID, AuditMixin, relationships, cascades, nullable, indexes, constraints, soft delete\n"
                "- schemas.py: msgspec, UNSET, PATCH semantics, pagination, DTO naming, default_factory\n"
                "- service.py: AsyncSession, flush only, no commits, business rule preservation, exceptions\n"
                "- routes.py: Litestar controllers, DTO usage, RBAC permissions, authentication, pagination\n"
                "- migration.py: downgrades, FKs, UUIDs, server defaults\n"
                "- seed.py: permissions, record series, app registration, __init__.py exports\n"
                "Provide a strict structured JSON review."
            )

        try:
            user_prompt = prompt_manager.render_prompt("review_agent_user", {
                "module_name": module_name, 
                "analysis_content": analysis_content, 
                "rules_content": rules_content, 
                "ground_truth": ground_truth, 
                "generated_code": generated_code_dump
            })
        except Exception:
            user_prompt = (
                f"Perform a strict architectural review for the generated ERP module: {module_name}\n\n"
                f"=== GROUND TRUTH PRODUCTION MODULES (MUST FOLLOW) ===\n{ground_truth}\n\n"
                f"=== LEGACY ANALYSIS ===\n{analysis_content}\n\n"
                f"=== BUSINESS RULES ===\n{rules_content}\n\n"
                f"=== GENERATED CODE FOR REVIEW ===\n{generated_code_dump}"
            )

        context.logger.info("Calling LLM to perform structural code review...")
        
        response = await context.llm.structured_generate(
            response_model=LLMExtraction,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0 # Absolute determinism for code review
        )
        
        extracted: LLMExtraction = response.structured_output
        
        # 5. Pack into Artifact
        safe_name = module_name.lower().replace(' ', '_')
        report = ReviewReport(
            name=f"review_report_{safe_name}",
            path="review_report.json",
            source=self.name,
            module_name=module_name,
            
            score=extracted.score,
            critical_issues=extracted.critical_issues,
            warnings=extracted.warnings,
            suggestions=extracted.suggestions,
            business_rule_violations=extracted.business_rule_violations,
            architecture_violations=extracted.architecture_violations,
            files_reviewed=extracted.files_reviewed,
            
            content=extracted.model_dump_json(indent=2)
        )
        
        # 6. Save explicitly to the workspace 'review' directory
        context.workspace.write_artifact(context.migration_id, "review", report)
        
        context.shared_state["review_report"] = report
        
        return [report]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) == 1 and isinstance(artifacts[0], ReviewReport)

    async def rollback(self, context: AgentContext, task: Any) -> None:
        pass

    async def health_check(self, context: AgentContext) -> bool:
        return True
