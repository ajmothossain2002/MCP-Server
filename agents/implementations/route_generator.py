"""
Route Generator Agent.
Generates the `routes.py` target file using Litestar and injecting existing auth rules.
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

class RouteGeneratorAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "RouteGeneratorAgent"
        
    @property
    def description(self) -> str:
        return "Generates routes.py using Litestar controllers, DTOs, and RBAC authentication."
        
    @property
    def version(self) -> str:
        return "1.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["generate_routes"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        if "migration_plan" not in context.shared_state: return False
        plan: MigrationPlan = context.shared_state["migration_plan"]
        return any(f.filename == "routes.py" for f in plan.generate_files)

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        return all(k in context.shared_state for k in ["legacy_analysis", "business_rules", "migration_plan"])

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        analysis: LegacyModuleAnalysis = context.shared_state["legacy_analysis"]
        rules: BusinessRuleSet = context.shared_state["business_rules"]
        module_name = analysis.module_name
        
        context.logger.info(f"Generating routes.py for module: {module_name}")
        
        bundle = context.knowledge.build_context("Company Leave Employee routes.py Litestar controller DTO authentication authorization pagination", max_tokens=20000)
        existing_context = bundle.format_as_text()
        
        analysis_content = analysis.model_dump_json(indent=2)
        rules_content = rules.model_dump_json(indent=2)
        
        try:
            system_prompt = prompt_manager.render_prompt("route_generator_system", {})
        except Exception:
            system_prompt = (
                "You are an expert Litestar developer migrating a legacy C++ ERP to Python. "
                "Write ONLY the routes.py file for the new module. "
                "CRITICAL REQUIREMENTS:\n"
                "- Follow Litestar Controller structure.\n"
                "- Use DTO patterns for request and response mapping.\n"
                "- Include Litestar authentication, authorization, and pagination dependencies.\n"
                "- Do NOT generate services. Do NOT invent architecture.\n"
                "- Output ONLY valid Python code inside a ```python block.\n"
                "- Add comments explaining WHY specific RBAC scopes were assigned based on legacy rules."
            )

        try:
            user_prompt = prompt_manager.render_prompt("route_generator_user", {
                "module_name": module_name, "analysis_content": analysis_content, "rules_content": rules_content, "existing_context": existing_context
            })
        except Exception:
            user_prompt = (
                f"Generate the `routes.py` for the ERP module: {module_name}\n\n"
                f"=== EXISTING PROJECT CONVENTIONS (MUST FOLLOW) ===\n{existing_context}\n\n"
                f"=== LEGACY ANALYSIS ===\n{analysis_content}\n\n"
                f"=== BUSINESS RULES ===\n{rules_content}\n\n"
                f"Write the complete `routes.py` inside a ```python block."
            )

        context.logger.info("Calling LLM to generate routes...")
        response = await context.llm.generate(user_prompt=user_prompt, system_prompt=system_prompt, temperature=0.1)
        
        code_artifacts = extract_code_blocks(response.text, language="python")
        if not code_artifacts:
            raise ValueError("LLM failed to produce a valid ```python code block for routes.py")
            
        generated_code = code_artifacts[0].content
        
        safe_name = module_name.lower().replace(" ", "_")
        logical_path = os.path.join("src", "erp", "modules", safe_name, "routes.py")
        
        generated_file = GeneratedFile(
            name=f"routes_{safe_name}", path=logical_path, language="python", content=generated_code,
            source=self.name, metadata={"module_name": module_name}
        )
        context.workspace.write_artifact(context.migration_id, "output", generated_file)
        
        return [generated_file]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return len(artifacts) == 1 and isinstance(artifacts[0], GeneratedFile)

    async def rollback(self, context: AgentContext, task: Any) -> None: pass
    async def health_check(self, context: AgentContext) -> bool: return True
