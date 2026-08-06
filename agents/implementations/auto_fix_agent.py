"""
Auto Fix Agent.
Automatically repairs generated artifacts based on the ReviewReport.
"""
import os
from typing import List, Any
from pydantic import BaseModel, Field

from agents.base import BaseAgent
from agents.context import AgentContext
from shared.artifacts import BaseArtifact, GeneratedFile
from agents.implementations.legacy_analyzer import LegacyModuleAnalysis
from agents.implementations.business_rule_extractor import BusinessRuleSet
from agents.implementations.review_agent import ReviewReport, Issue
from shared.prompts import prompt_manager
from shared.parser import extract_code_blocks

# ---------------------------------------------------------------------------
# Models for Structured Output
# ---------------------------------------------------------------------------

class LLMFixResult(BaseModel):
    """Pydantic model used explicitly for LLM structured output parsing."""
    repaired_code: str = Field(description="The fully repaired file content. MUST contain the full Python code.")
    confidence_score: int = Field(description="0 to 100 confidence that the issues were completely and safely resolved")
    issues_repaired: List[str] = Field(description="List of issues successfully addressed")
    remaining_issues: List[str] = Field(description="Issues that could not be safely repaired without rewriting the whole file")

class FixReport(BaseArtifact):
    """Strongly typed output artifact containing the summary of all repairs."""
    artifact_type: str = Field(default="fix_report", frozen=True)
    module_name: str
    files_repaired: List[str] = Field(default_factory=list)
    issues_repaired: List[str] = Field(default_factory=list)
    remaining_issues: List[str] = Field(default_factory=list)
    confidence_score: int = Field(default=0)
    files_skipped: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent Implementation
# ---------------------------------------------------------------------------

class AutoFixAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "AutoFixAgent"
        
    @property
    def description(self) -> str:
        return "Automatically repairs code generation issues based on the ReviewAgent's report."
        
    @property
    def version(self) -> str:
        return "1.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["auto_fix"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        if "review_report" not in context.shared_state:
            return False
            
        report: ReviewReport = context.shared_state["review_report"]
        # Run if there are issues reported across any critical category
        return bool(report.critical_issues or report.warnings or report.business_rule_violations or report.architecture_violations)

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        return all(k in context.shared_state for k in ["legacy_analysis", "business_rules", "review_report"])

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        analysis: LegacyModuleAnalysis = context.shared_state["legacy_analysis"]
        rules: BusinessRuleSet = context.shared_state["business_rules"]
        review: ReviewReport = context.shared_state["review_report"]
        module_name = analysis.module_name
        
        context.logger.info(f"Initiating auto-fix loop for module: {module_name}")
        
        # 1. Group issues by file (we only fix files that actually failed review)
        issues_by_file = {}
        all_issues = review.critical_issues + review.warnings + review.business_rule_violations + review.architecture_violations
        
        for issue in all_issues:
            if issue.file not in issues_by_file:
                issues_by_file[issue.file] = []
            issues_by_file[issue.file].append(issue)
            
        # 2. Extract generated files directly from pipeline state
        generated_files = {a.name: a for a in context.state.generated_artifacts if getattr(a, "artifact_type", "") == "generated_file"}
        
        fix_report = FixReport(
            name=f"fix_report_{module_name.lower().replace(' ', '_')}",
            path="fix_report.json",
            source=self.name,
            module_name=module_name
        )
        
        repaired_artifacts = []
        
        # 3. Process repairs file by file
        for file_ref, issues in issues_by_file.items():
            
            # Find the actual artifact (fuzzy match in case of minor naming differences)
            target_artifact = None
            for art in generated_files.values():
                if file_ref in art.path or file_ref in art.name:
                    target_artifact = art
                    break
                    
            if not target_artifact:
                context.logger.warning(f"Could not locate original artifact for file {file_ref}. Skipping.")
                fix_report.files_skipped.append(file_ref)
                continue
                
            context.logger.info(f"Attempting to repair {target_artifact.path}...")
            
            # Fetch context explicitly relevant to this specific file type
            if "models" in file_ref:
                query = "Company Leave Employee models.py SQLAlchemy 2.0"
            elif "schemas" in file_ref:
                query = "Company Leave Employee schemas.py msgspec"
            elif "service" in file_ref:
                query = "Company Leave Employee service.py"
            elif "routes" in file_ref:
                query = "Company Leave Employee routes.py Litestar"
            elif "migration" in file_ref:
                query = "alembic migration downgrade"
            else:
                query = "Company Leave Employee ERP"
                
            bundle = context.knowledge.build_context(query, max_tokens=15000)
            ground_truth = bundle.format_as_text()
            
            issues_dump = "\n".join([f"- [{i.rule_violated}] {i.description}" for i in issues])
            
            # 4. Render Prompts
            try:
                system_prompt = prompt_manager.render_prompt("auto_fix_system", {})
            except Exception:
                system_prompt = (
                    "You are an expert Senior Python Developer. Your task is to repair the provided source code "
                    "so that it passes architectural review. You must preserve all working code, formatting, imports, and comments. "
                    "Make ONLY the smallest safe modifications needed to fix the listed issues. "
                    "Provide your structured JSON response."
                )

            try:
                user_prompt = prompt_manager.render_prompt("auto_fix_user", {
                    "file_ref": file_ref,
                    "issues": issues_dump,
                    "ground_truth": ground_truth,
                    "original_code": target_artifact.content
                })
            except Exception:
                user_prompt = (
                    f"Repair the {file_ref} file.\n\n"
                    f"=== ISSUES TO FIX ===\n{issues_dump}\n\n"
                    f"=== GROUND TRUTH EXAMPLES ===\n{ground_truth}\n\n"
                    f"=== ORIGINAL CODE ===\n{target_artifact.content}\n\n"
                    "Place the fully repaired code inside the 'repaired_code' field."
                )

            # 5. Call LLM
            response = await context.llm.structured_generate(
                response_model=LLMFixResult,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.0 # Deterministic
            )
            
            result: LLMFixResult = response.structured_output
            
            # 6. Safety Check
            if result.confidence_score < 90:
                context.logger.warning(f"Confidence score {result.confidence_score} < 90% for {file_ref}. Skipping repair.")
                fix_report.files_skipped.append(file_ref)
                fix_report.remaining_issues.extend(result.remaining_issues)
                continue
                
            # 7. Unpack and Save Valid Repair
            raw_code = result.repaired_code
            code_blocks = extract_code_blocks(raw_code, language="python")
            
            if code_blocks:
                final_code = code_blocks[0].content
            else:
                final_code = raw_code.strip()
                if final_code.startswith("```python"):
                    final_code = final_code[9:].strip("`\n")
            
            # Create a new artifact, do NOT overwrite the original
            # Logical path includes 'fixed/' to segregate it
            logical_path = os.path.join("fixed", target_artifact.path)
            
            fixed_file = GeneratedFile(
                name=f"fixed_{target_artifact.name}",
                path=logical_path,
                language="python",
                content=final_code,
                source=self.name,
                metadata={"original_artifact": target_artifact.name, "confidence": result.confidence_score}
            )
            
            # Save into workspace output directory
            # We use "output/fixed" as the folder name
            context.workspace.write_artifact(context.migration_id, "output/fixed", fixed_file)
            
            repaired_artifacts.append(fixed_file)
            
            fix_report.files_repaired.append(file_ref)
            fix_report.issues_repaired.extend(result.issues_repaired)
            fix_report.remaining_issues.extend(result.remaining_issues)
            
        # Finalize report
        total = len(fix_report.files_repaired) + len(fix_report.files_skipped)
        if total > 0:
            fix_report.confidence_score = 100 if len(fix_report.files_skipped) == 0 else int((len(fix_report.files_repaired) / total) * 100)
            
        fix_report.content = fix_report.model_dump_json(indent=2)
        context.workspace.write_artifact(context.migration_id, "output", fix_report)
        context.shared_state["fix_report"] = fix_report
        
        return repaired_artifacts + [fix_report]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return any(isinstance(a, FixReport) for a in artifacts)

    async def rollback(self, context: AgentContext, task: Any) -> None:
        pass

    async def health_check(self, context: AgentContext) -> bool:
        return True
