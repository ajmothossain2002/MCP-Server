"""
Business Rule Extractor Agent.
Consumes the LegacyModuleAnalysis and extracts deep business rules,
state transitions, and lifecycle policies using OpenAI Structured Outputs.
Produces a highly detailed BusinessRuleSet artifact.
"""
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from agents.base import BaseAgent
from agents.context import AgentContext
from shared.artifacts import BaseArtifact
from agents.implementations.legacy_analyzer import LegacyModuleAnalysis
from shared.prompts import prompt_manager

# ---------------------------------------------------------------------------
# Models for Structured Output (Mapped to LLM JSON Schema)
# ---------------------------------------------------------------------------

class GeneralRules(BaseModel):
    module_purpose: str = Field(default="", description="High-level purpose of the module")
    functional_description: str = Field(default="", description="Detailed functional description")
    dependencies: List[str] = Field(default_factory=list, description="External modules or services this depends on")

class ValidationRules(BaseModel):
    required_fields: List[str] = Field(default_factory=list)
    nullable_fields: List[str] = Field(default_factory=list)
    length_restrictions: Dict[str, int] = Field(default_factory=dict, description="Field name to max length")
    enum_restrictions: Dict[str, List[str]] = Field(default_factory=dict, description="Field name to allowed enum strings")
    foreign_key_validation: List[str] = Field(default_factory=list, description="Rules about validating related records")
    duplicate_prevention: List[str] = Field(default_factory=list, description="Rules preventing duplicate entries")

class WorkflowRules(BaseModel):
    status_transitions: Dict[str, List[str]] = Field(default_factory=dict, description="State to valid next states mapping")
    approval_workflow: List[str] = Field(default_factory=list, description="Steps required for approval")
    assignment_workflow: List[str] = Field(default_factory=list, description="Rules regarding record assignment")
    completion_rules: List[str] = Field(default_factory=list, description="Conditions required to complete/close")
    cancellation_rules: List[str] = Field(default_factory=list, description="Rules around voiding or cancelling")

class DatabaseRules(BaseModel):
    soft_delete: bool = Field(default=False, description="Does the module use soft deletion?")
    audit_behavior: str = Field(default="", description="Rules for audit trails or logging")
    record_series: str = Field(default="", description="Rules for sequential record numbers (e.g., INV-001)")
    default_values: Dict[str, str] = Field(default_factory=dict, description="Field name to default value")
    cascade_rules: List[str] = Field(default_factory=list, description="On-delete cascade behaviors")
    unique_constraints: List[str] = Field(default_factory=list, description="Complex uniqueness rules")

class SecurityRules(BaseModel):
    permissions_required: List[str] = Field(default_factory=list, description="List of required RBAC permissions")
    role_restrictions: List[str] = Field(default_factory=list, description="Roles that are explicitly blocked or allowed")
    self_service_restrictions: List[str] = Field(default_factory=list, description="Rules about a user editing their own data")

class PythonArchitectureRules(BaseModel):
    existing_project_conventions: List[str] = Field(default_factory=list, description="Matched conventions this module must follow")
    existing_coding_patterns: List[str] = Field(default_factory=list, description="Matched coding patterns")
    required_reusable_components: List[str] = Field(default_factory=list, description="Standard components this module must import")

class LLMExtraction(BaseModel):
    """Pydantic model used explicitly for LLM structured output parsing."""
    general: GeneralRules
    validation: ValidationRules
    workflow: WorkflowRules
    database: DatabaseRules
    security: SecurityRules
    architecture: PythonArchitectureRules

class BusinessRuleSet(BaseArtifact):
    """Strongly typed output artifact containing strictly categorized business rules."""
    artifact_type: str = Field(default="business_rule_set", frozen=True)
    module_name: str
    
    general: GeneralRules
    validation: ValidationRules
    workflow: WorkflowRules
    database: DatabaseRules
    security: SecurityRules
    architecture: PythonArchitectureRules


# ---------------------------------------------------------------------------
# Agent Implementation
# ---------------------------------------------------------------------------

class BusinessRuleExtractorAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "BusinessRuleExtractorAgent"
        
    @property
    def description(self) -> str:
        return "Extracts structured business rules across Validation, Workflow, Database, and Security categories."
        
    @property
    def version(self) -> str:
        return "2.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["extract_business_rules"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        return "legacy_analysis" in context.shared_state

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        analysis = context.shared_state.get("legacy_analysis")
        return isinstance(analysis, LegacyModuleAnalysis)

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        analysis: LegacyModuleAnalysis = context.shared_state["legacy_analysis"]
        module_name = analysis.module_name
        
        context.logger.info(f"Extracting highly structured business rules for module: {module_name}")
        
        # 1. Use the previous legacy analysis as the source of truth
        analysis_content = analysis.model_dump_json(indent=2)
        
        # 2. Fetch overarching architectural conventions from the Knowledge Engine
        bundle = context.knowledge.build_context("Python Architecture Security Rules Validation", max_tokens=10000)
        domain_knowledge = bundle.format_as_text()
        
        # 3. Render Prompts
        try:
            system_prompt = prompt_manager.render_prompt("business_rule_system", {})
        except Exception:
            system_prompt = (
                "You are an expert ERP systems analyst. You must rigorously extract business rules "
                "from the provided module analysis into exactly six structured categories: General, Validation, "
                "Workflow, Database, Security, and Python Architecture. Do not invent rules; extract them strictly."
            )

        try:
            user_prompt = prompt_manager.render_prompt("business_rule_user", {
                "module_name": module_name,
                "analysis_content": analysis_content,
                "domain_knowledge": domain_knowledge
            })
        except Exception:
            user_prompt = (
                f"Extract comprehensive business rules for the ERP module: {module_name}\n\n"
                f"=== LEGACY ANALYSIS ===\n{analysis_content}\n\n"
                f"=== ENTERPRISE CONVENTIONS ===\n{domain_knowledge}"
            )

        # 4. Call the LLM with structured output mapping to our detailed schemas
        context.logger.info("Calling LLM for categorized business rule extraction...")
        
        response = await context.llm.structured_generate(
            response_model=LLMExtraction,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0 # Strict extraction
        )
        
        extracted: LLMExtraction = response.structured_output
        
        # 5. Pack into Artifact
        safe_name = module_name.lower().replace(' ', '_')
        rule_set = BusinessRuleSet(
            name=f"business_rules_{safe_name}",
            path=f"business_rules.json", # Fixed output filename to match requirements exactly
            source=self.name,
            module_name=module_name,
            
            general=extracted.general,
            validation=extracted.validation,
            workflow=extracted.workflow,
            database=extracted.database,
            security=extracted.security,
            architecture=extracted.architecture,
            
            content=extracted.model_dump_json(indent=2)
        )
        
        # 6. Save explicitly to the workspace output directory
        context.workspace.write_artifact(context.migration_id, "output", rule_set)
        
        # Provide for downstream code generation
        context.shared_state["business_rules"] = rule_set
        
        return [rule_set]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) == 1 and isinstance(artifacts[0], BusinessRuleSet)

    async def rollback(self, context: AgentContext, task: Any) -> None:
        pass

    async def health_check(self, context: AgentContext) -> bool:
        return True
