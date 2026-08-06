"""
Seed Generator Agent.
Generates RBAC, Record Series seeds, and application registration snippets.
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

class SeedGeneratorAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "SeedGeneratorAgent"
        
    @property
    def description(self) -> str:
        return "Generates RBAC permissions, Record Series seeds, app.py registration, and __init__.py exports."
        
    @property
    def version(self) -> str:
        return "1.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["generate_seeds"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        if "migration_plan" not in context.shared_state: return False
        plan: MigrationPlan = context.shared_state["migration_plan"]
        return any(f.filename == "seed.py" for f in plan.generate_files) or len(plan.modify_files) > 0

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        return all(k in context.shared_state for k in ["legacy_analysis", "business_rules", "migration_plan"])

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        analysis: LegacyModuleAnalysis = context.shared_state["legacy_analysis"]
        rules: BusinessRuleSet = context.shared_state["business_rules"]
        module_name = analysis.module_name
        
        context.logger.info(f"Generating seeds and registry snippets for module: {module_name}")
        
        bundle = context.knowledge.build_context("Company Leave Employee RBAC Record Series app.py registration __init__.py", max_tokens=20000)
        existing_context = bundle.format_as_text()
        
        analysis_content = analysis.model_dump_json(indent=2)
        rules_content = rules.model_dump_json(indent=2)
        
        try:
            system_prompt = prompt_manager.render_prompt("seed_generator_system", {})
        except Exception:
            system_prompt = (
                "You are an expert Python ERP developer. "
                "Your task is to generate EXACTLY the following files/snippets:\n"
                "1. RBAC permissions (seed.py)\n"
                "2. Record Series configuration\n"
                "3. app.py router registration snippet\n"
                "4. __init__.py exports\n"
                "CRITICAL REQUIREMENTS:\n"
                "- Do NOT generate migrations.\n"
                "- Output each snippet in a separate ```python block with a `# FILENAME: <path>` comment at the top.\n"
                "- Add comments explaining WHY permissions were seeded based on legacy logic."
            )

        try:
            user_prompt = prompt_manager.render_prompt("seed_generator_user", {
                "module_name": module_name, "analysis_content": analysis_content, "rules_content": rules_content, "existing_context": existing_context
            })
        except Exception:
            user_prompt = (
                f"Generate the seeds and integration snippets for the ERP module: {module_name}\n\n"
                f"=== EXISTING PROJECT CONVENTIONS (MUST FOLLOW) ===\n{existing_context}\n\n"
                f"=== LEGACY ANALYSIS ===\n{analysis_content}\n\n"
                f"=== BUSINESS RULES ===\n{rules_content}\n\n"
                f"Provide separate ```python blocks for seed.py, app.py (modifications), and __init__.py."
            )

        context.logger.info("Calling LLM to generate seeds...")
        response = await context.llm.generate(user_prompt=user_prompt, system_prompt=system_prompt, temperature=0.1)
        
        code_artifacts = extract_code_blocks(response.text, language="python")
        if not code_artifacts:
            raise ValueError("LLM failed to produce valid code blocks for the seeds")
            
        generated_artifacts = []
        safe_name = module_name.lower().replace(" ", "_")
        
        for idx, block in enumerate(code_artifacts):
            # Extract a filename from the comment if present, otherwise guess based on index
            lines = block.content.split('\n')
            filename = f"snippet_{idx}.py"
            if lines and "FILENAME:" in lines[0]:
                filename = lines[0].split("FILENAME:")[1].strip()
            
            logical_path = os.path.join("src", "erp", "modules", safe_name, filename)
            
            artifact = GeneratedFile(
                name=f"seed_snippet_{safe_name}_{idx}", path=logical_path, language="python", content=block.content,
                source=self.name, metadata={"module_name": module_name}
            )
            context.workspace.write_artifact(context.migration_id, "output", artifact)
            generated_artifacts.append(artifact)
        
        return generated_artifacts

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) > 0

    async def rollback(self, context: AgentContext, task: Any) -> None: pass
    async def health_check(self, context: AgentContext) -> bool: return True
