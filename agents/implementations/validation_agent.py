"""
Validation Agent.
Deterministically verifies that the generated (or repaired) module is technically 
valid via syntax checks, linting, typing, and regex convention checks 
before it can be merged into the ERP.
"""
import os
import shutil
import tempfile
import subprocess
import re
from typing import List, Any, Dict
from pydantic import BaseModel, Field
from pathlib import Path

from agents.base import BaseAgent
from agents.context import AgentContext
from shared.artifacts import BaseArtifact, GeneratedFile

# ---------------------------------------------------------------------------
# Models for Validation Output
# ---------------------------------------------------------------------------

class ValidationError(BaseModel):
    file: str = Field(description="Name of the file containing the error")
    issue: str = Field(description="Type of issue")
    details: str = Field(description="Raw traceback or rule violation details")

class ValidationReport(BaseArtifact):
    artifact_type: str = Field(default="validation_report", frozen=True)
    module_name: str
    overall_status: str = Field(description="PASSED or FAILED")
    
    syntax_errors: List[ValidationError] = Field(default_factory=list)
    typing_errors: List[ValidationError] = Field(default_factory=list)
    lint_errors: List[ValidationError] = Field(default_factory=list)
    migration_errors: List[ValidationError] = Field(default_factory=list)
    architecture_errors: List[ValidationError] = Field(default_factory=list)
    warnings: List[ValidationError] = Field(default_factory=list)
    
    validated_files: List[str] = Field(default_factory=list)
    success_percentage: int = Field(default=0)


# ---------------------------------------------------------------------------
# Agent Implementation
# ---------------------------------------------------------------------------

class ValidationAgent(BaseAgent):
    
    @property
    def name(self) -> str:
        return "ValidationAgent"
        
    @property
    def description(self) -> str:
        return "Deterministically validates generated python artifacts using py_compile, ruff, mypy, and convention checks."
        
    @property
    def version(self) -> str:
        return "1.0.0"
        
    @property
    def supported_tasks(self) -> List[str]:
        return ["validate_module"]

    async def should_run(self, context: AgentContext, task: Any) -> bool:
        # Run if any files were generated
        return len([a for a in context.state.generated_artifacts if getattr(a, "artifact_type", "") == "generated_file"]) > 0

    async def validate_input(self, context: AgentContext, task: Any) -> bool:
        return True # Always safe to run as long as artifacts exist

    async def execute(self, context: AgentContext, task: Any) -> List[BaseArtifact]:
        context.logger.info("Initiating strict deterministic validation phase...")
        
        # 1. Determine which artifacts to validate (prefer fixed over original)
        artifacts_to_validate: Dict[str, GeneratedFile] = {}
        for art in context.state.generated_artifacts:
            if getattr(art, "artifact_type", "") == "generated_file":
                # If it's a fixed artifact, it overrides the original
                original_name = getattr(art, "metadata", {}).get("original_artifact")
                if original_name:
                    artifacts_to_validate[original_name] = art
                else:
                    if art.name not in artifacts_to_validate:
                        artifacts_to_validate[art.name] = art
                        
        files_to_check = list(artifacts_to_validate.values())
        if not files_to_check:
            context.logger.warning("No files found to validate.")
            return []

        module_name = files_to_check[0].metadata.get("module_name", "unknown")
        report = ValidationReport(
            name=f"validation_report_{module_name.lower().replace(' ', '_')}",
            path="validation_report.json",
            source=self.name,
            module_name=module_name,
            overall_status="PENDING"
        )
        
        # 2. Create isolated temporary workspace
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Copy files into temp workspace
            for file_art in files_to_check:
                file_dest = temp_path / os.path.basename(file_art.path)
                file_dest.parent.mkdir(parents=True, exist_ok=True)
                file_dest.write_text(file_art.content, encoding='utf-8')
                report.validated_files.append(os.path.basename(file_art.path))
                
            # 3. Syntax Validation
            for file_art in files_to_check:
                filename = os.path.basename(file_art.path)
                file_dest = temp_path / filename
                
                try:
                    subprocess.run(
                        ["python", "-m", "py_compile", str(file_dest)],
                        check=True, capture_output=True, text=True
                    )
                except subprocess.CalledProcessError as e:
                    report.syntax_errors.append(ValidationError(
                        file=filename,
                        issue="Syntax Error",
                        details=e.stderr.strip()
                    ))
                    
            # 4. Import Validation (Static via Ruff)
            try:
                ruff_res = subprocess.run(
                    ["ruff", "check", str(temp_path)],
                    capture_output=True, text=True
                )
                if ruff_res.returncode != 0:
                    for line in ruff_res.stdout.splitlines():
                        if ".py:" in line:
                            parts = line.split(":", 2)
                            if len(parts) >= 3:
                                f_name = os.path.basename(parts[0])
                                report.lint_errors.append(ValidationError(
                                    file=f_name,
                                    issue="Lint/Import Issue",
                                    details=line.strip()
                                ))
            except FileNotFoundError:
                report.warnings.append(ValidationError(file="system", issue="Ruff Missing", details="Ruff not installed in environment"))

            # 5. MyPy Validation
            try:
                mypy_res = subprocess.run(
                    ["mypy", str(temp_path), "--ignore-missing-imports"],
                    capture_output=True, text=True
                )
                if mypy_res.returncode != 0:
                    for line in mypy_res.stdout.splitlines():
                        if ".py:" in line:
                            parts = line.split(":", 2)
                            if len(parts) >= 3:
                                f_name = os.path.basename(parts[0])
                                report.typing_errors.append(ValidationError(
                                    file=f_name,
                                    issue="Typing Error",
                                    details=line.strip()
                                ))
            except FileNotFoundError:
                report.warnings.append(ValidationError(file="system", issue="MyPy Missing", details="MyPy not installed in environment"))
                
            # 6. Architecture & Convention Regex Validation
            for file_art in files_to_check:
                filename = os.path.basename(file_art.path)
                content = file_art.content
                
                if "models.py" in filename:
                    if "AuditMixin" not in content:
                        report.architecture_errors.append(ValidationError(file=filename, issue="Missing AuditMixin", details="Models must inherit AuditMixin."))
                
                if "schemas.py" in filename:
                    if "msgspec" not in content:
                        report.architecture_errors.append(ValidationError(file=filename, issue="Missing msgspec", details="Schemas must use msgspec structs."))
                    if "UNSET" not in content and "Struct" in content:
                        report.warnings.append(ValidationError(file=filename, issue="Missing UNSET", details="PATCH schemas typically require UNSET."))
                        
                if "service.py" in filename:
                    if "session.commit()" in content:
                        report.architecture_errors.append(ValidationError(file=filename, issue="Explicit Commit", details="Services must use flush(), not commit()."))
                    if "AsyncSession" not in content:
                        report.architecture_errors.append(ValidationError(file=filename, issue="Missing AsyncSession", details="Services must use AsyncSession."))
                        
                if "migration" in filename:
                    if "def upgrade" not in content or "def downgrade" not in content:
                        report.migration_errors.append(ValidationError(file=filename, issue="Invalid Migration", details="Migration missing upgrade/downgrade methods."))
                        
                if "routes.py" in filename:
                    if "Controller" not in content:
                        report.architecture_errors.append(ValidationError(file=filename, issue="Missing Controller", details="Routes must use Litestar Controller inheritance."))
                        
        # 7. Finalize Report Status
        total_errors = len(report.syntax_errors) + len(report.typing_errors) + len(report.lint_errors) + len(report.migration_errors) + len(report.architecture_errors)
        
        if total_errors > 0:
            report.overall_status = "FAILED"
            # Calculate arbitrary success % based on files passed vs failed
            failed_files = set()
            for err_list in [report.syntax_errors, report.typing_errors, report.lint_errors, report.migration_errors, report.architecture_errors]:
                for err in err_list:
                    failed_files.add(err.file)
            
            report.success_percentage = int(((len(files_to_check) - len(failed_files)) / len(files_to_check)) * 100) if len(files_to_check) > 0 else 0
        else:
            report.overall_status = "PASSED"
            report.success_percentage = 100
            
        context.logger.info(f"Validation finished with status: {report.overall_status}")
        
        # 8. Save explicitly to the workspace 'validation' directory
        context.workspace.write_artifact(context.migration_id, "validation", report)
        context.shared_state["validation_report"] = report
        
        return [report]

    async def validate_output(self, context: AgentContext, artifacts: List[BaseArtifact]) -> bool:
        return any(isinstance(a, ValidationReport) for a in artifacts)

    async def rollback(self, context: AgentContext, task: Any) -> None:
        pass

    async def health_check(self, context: AgentContext) -> bool:
        return True
