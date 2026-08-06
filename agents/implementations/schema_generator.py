"""
Schema Generator Agent.
Generates the `schemas.py` target file based on the Migration Plan and Analysis.
Enforces Msgspec patterns, DTO logic, and UNSET semantics.
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

class SchemaGeneratorAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "SchemaGeneratorAgent"
        
    @property
    def description(self) -> str:
        return "Generates schemas.py using msgspec, UNSET logic, and project DTO conventions."
        
    @property
    def version(self) -> str:
        return "1.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["generate_schemas"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        if "migration_plan" not in context.shared_state: return False
        plan: MigrationPlan = context.shared_state["migration_plan"]
        return any(f.filename == "schemas.py" for f in plan.generate_files)

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        return all(k in context.shared_state for k in ["legacy_analysis", "business_rules", "migration_plan"])

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        analysis: LegacyModuleAnalysis = context.shared_state["legacy_analysis"]
        rules: BusinessRuleSet = context.shared_state["business_rules"]
        module_name = analysis.module_name
        
        context.logger.info(f"Generating schemas.py for module: {module_name}")
        
        # 1. Fetch exact examples of existing schemas
        bundle = context.knowledge.build_context("Company Leave Employee schemas.py msgspec UNSET PATCH pagination filters DTO", max_tokens=20000)
        existing_context = bundle.format_as_text()
        
        # 2. Serialize constraints
        analysis_content = analysis.model_dump_json(indent=2)
        rules_content = rules.model_dump_json(indent=2)
        
        # 3. Render Prompts
        try:
            system_prompt = prompt_manager.render_prompt("schema_generator_system", {})
        except Exception:
            system_prompt = (
                "You are an expert Python developer migrating a legacy C++ ERP to Python. "
                "Write ONLY the schemas.py file for the new module. "
                "CRITICAL REQUIREMENTS:\n"
                "- Follow msgspec style.\n"
                "- Support UNSET and PATCH semantics.\n"
                "- Include pagination, filters, detail DTOs, and request DTOs.\n"
                "- Never invent architecture. Mimic the Company, Leave, and Employee examples perfectly.\n"
                "- Output ONLY valid Python code inside a ```python block.\n"
                "- Add comments explaining WHY you generated specific schema rules based on the legacy analysis."
            )

        try:
            user_prompt = prompt_manager.render_prompt("schema_generator_user", {
                "module_name": module_name, "analysis_content": analysis_content, "rules_content": rules_content, "existing_context": existing_context
            })
        except Exception:
            user_prompt = (
                f"Generate the `schemas.py` for the ERP module: {module_name}\n\n"
                f"=== EXISTING PROJECT CONVENTIONS (MUST FOLLOW) ===\n{existing_context}\n\n"
                f"=== LEGACY ANALYSIS ===\n{analysis_content}\n\n"
                f"=== BUSINESS RULES ===\n{rules_content}\n\n"
                f"Write the complete `schemas.py` inside a ```python block."
            )

        # 4. Generate
        context.logger.info("Calling LLM to generate schemas...")
        response = await context.llm.generate(user_prompt=user_prompt, system_prompt=system_prompt, temperature=0.1)
        
        # 5. Extract
        code_artifacts = extract_code_blocks(response.text, language="python")
        if not code_artifacts:
            raise ValueError("LLM failed to produce a valid ```python code block for schemas.py")
            
        generated_code = code_artifacts[0].content
        
        # 6. Save Artifact
        safe_name = module_name.lower().replace(" ", "_")
        logical_path = os.path.join("src", "erp", "modules", safe_name, "schemas.py")
        
        generated_file = GeneratedFile(
            name=f"schemas_{safe_name}", path=logical_path, language="python", content=generated_code,
            source=self.name, metadata={"module_name": module_name}
        )
        context.workspace.write_artifact(context.migration_id, "output", generated_file)
        
        return [generated_file]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) == 1 and isinstance(artifacts[0], GeneratedFile)

    async def rollback(self, context: AgentContext, task: Any) -> None: pass
    async def health_check(self, context: AgentContext) -> bool: return True
