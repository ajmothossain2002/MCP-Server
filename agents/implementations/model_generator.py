"""
Model Generator Agent.
Generates the SQLAlchemy `models.py` target file based on the Migration Plan and Legacy Analysis.
Enforces project conventions by injecting existing modules as few-shot architectural examples,
ensuring strict adherence to SQLAlchemy 2.0, AuditMixin, and UUID conventions.
"""
import os
from typing import List, Any

from agents.base import BaseAgent
from agents.context import AgentContext
from shared.artifacts import BaseArtifact, GeneratedFile
from agents.implementations.legacy_analyzer import LegacyModuleAnalysis
from agents.implementations.business_rule_extractor import BusinessRuleSet
from agents.implementations.migration_planner import MigrationPlan
from shared.prompts import prompt_manager
from shared.parser import extract_code_blocks

class ModelGeneratorAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "ModelGeneratorAgent"
        
    @property
    def description(self) -> str:
        return "Generates ONLY the SQLAlchemy models.py file following strict 2.0 architectural project conventions."
        
    @property
    def version(self) -> str:
        return "2.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["generate_models"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        if "migration_plan" not in context.shared_state:
            return False
            
        plan: MigrationPlan = context.shared_state["migration_plan"]
        return any(f.filename == "models.py" for f in plan.generate_files)

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        return (
            "legacy_analysis" in context.shared_state and
            "business_rules" in context.shared_state and
            "migration_plan" in context.shared_state
        )

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        analysis: LegacyModuleAnalysis = context.shared_state["legacy_analysis"]
        rules: BusinessRuleSet = context.shared_state["business_rules"]
        
        module_name = analysis.module_name
        context.logger.info(f"Generating models.py for module: {module_name}")
        
        # 1. Fetch exact examples of existing models (Company, Leave, Employee)
        # This acts as a strict architectural few-shot prompt
        bundle = context.knowledge.build_context("Company Leave Employee models.py SQLAlchemy 2.0 AuditMixin UUID", max_tokens=20000)
        existing_models_context = bundle.format_as_text()
        
        # 2. Serialize constraints
        analysis_content = analysis.model_dump_json(indent=2)
        rules_content = rules.model_dump_json(indent=2)
        
        # 3. Render Prompts
        try:
            system_prompt = prompt_manager.render_prompt("model_generator_system", {})
        except Exception:
            system_prompt = (
                "You are an expert Python SQLAlchemy developer migrating a legacy C++ ERP to Python. "
                "Your task is to write ONLY the models.py file for the new module. "
                "CRITICAL REQUIREMENTS:\n"
                "- Follow SQLAlchemy 2.0 style (Mapped, mapped_column).\n"
                "- Follow AuditMixin patterns.\n"
                "- Follow UUID primary key conventions.\n"
                "- Follow existing relationship and cascade behaviors.\n"
                "- Follow strict naming conventions.\n"
                "- Never invent architecture. Mimic the provided Company, Leave, and Employee examples perfectly.\n"
                "Output ONLY valid Python code inside a ```python block."
            )

        try:
            user_prompt = prompt_manager.render_prompt("model_generator_user", {
                "module_name": module_name,
                "analysis_content": analysis_content,
                "rules_content": rules_content,
                "existing_models": existing_models_context
            })
        except Exception:
            user_prompt = (
                f"Generate the SQLAlchemy `models.py` for the ERP module: {module_name}\n\n"
                f"=== EXISTING PROJECT CONVENTIONS (MUST FOLLOW) ===\n{existing_models_context}\n\n"
                f"=== LEGACY ANALYSIS ===\n{analysis_content}\n\n"
                f"=== BUSINESS RULES ===\n{rules_content}\n\n"
                f"Write the complete `models.py` file inside a ```python block."
            )

        # 4. Call the LLM for standard generation
        context.logger.info("Calling LLM to generate SQLAlchemy models...")
        
        response = await context.llm.generate(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1 # Very low temperature for highly deterministic code generation
        )
        
        # 5. Parse the output to extract the Python block
        code_artifacts = extract_code_blocks(response.text, language="python")
        if not code_artifacts:
            raise ValueError("LLM failed to produce a valid ```python code block for models.py")
            
        generated_code = code_artifacts[0].content
        
        # 6. Pack into GeneratedFile Artifact
        # Note: We specify the logical path where it *should* go, but we DO NOT write to the ERP directly.
        safe_name = module_name.lower().replace(" ", "_")
        logical_path = os.path.join("src", "erp", "modules", safe_name, "models.py")
        
        generated_file = GeneratedFile(
            name=f"models_{safe_name}",
            path=logical_path, # Represents intended destination
            language="python",
            content=generated_code,
            source=self.name,
            metadata={
                "estimated_tokens": response.usage.completion_tokens,
                "module_name": module_name
            }
        )
        
        # 7. Save to the Workspace isolated environment (output folder)
        saved_path = context.workspace.write_artifact(context.migration_id, "output", generated_file)
        
        context.logger.info(f"Models successfully generated and saved to workspace at: {saved_path}")
        
        return [generated_file]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) == 1 and isinstance(artifacts[0], GeneratedFile)

    async def rollback(self, context: AgentContext, task: Any) -> None:
        pass

    async def health_check(self, context: AgentContext) -> bool:
        return True
