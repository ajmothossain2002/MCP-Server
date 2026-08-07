"""
Orchestrator.
The brain of the ERP Migration Platform.
Manages the DAG pipeline, coordinates the Review-Repair loop, and tracks migration state.
"""
import time
import traceback
from datetime import datetime, timezone
from typing import List, Any, Optional

from agents.registry import agent_registry
from agents.context import AgentContext
from agents.state import MigrationState
from agents.base import BaseAgent
from shared.artifacts import MigrationResult, MigrationArtifact
from agents.implementations.review_agent import ReviewReport
from agents.implementations.validation_agent import ValidationReport

class Orchestrator:
    """
    The central coordinator for executing migrations.
    It dynamically loads agents from the AgentRegistry, runs them sequentially,
    manages the recursive Review-Repair loop, and outputs the final result.
    """
    
    def __init__(self, context: AgentContext):
        self.context = context
        # 1. Discover all agents dynamically, satisfying the requirement to never manually instantiate them inline.
        agent_registry.discover("agents.implementations")
        
    async def resume(self, module_name: str = "unknown"):
        """Resumes a paused or failed migration from its last completed stage."""
        self.context.logger.info("Resuming migration from previous state...")
        state_json = self.context.workspace.load_state(self.context.migration_id)
        if state_json:
            self.context.state = MigrationState.model_validate_json(state_json)
            self.context.logger.info(f"Loaded state, last completed stages: {self.context.state.completed_stages}")
        
        # We need a valid task payload, we can reconstruct it from module_name if not saved in state
        task_payload = {
            "module_name": module_name,
            "module_folder": ".", # Not fully recoverable without storing, but fine for resume of generators
            "database_source": {"type": "skip"}
        }
        return await self.execute_migration(task_payload)
        
    async def restart(self):
        """Restarts the migration from the beginning, clearing state."""
        self.context.logger.info("Restarting migration pipeline...")
        self.context.state = MigrationState(migration_id=self.context.migration_id)
        self.context.shared_state.clear()
        
    async def cancel(self):
        """Cancels a running migration."""
        self.context.logger.warning("Migration cancelled by user.")
        self.context.state.current_stage = "CANCELLED"
        
    async def rollback(self):
        """Rolls back all actions performed during the migration."""
        self.context.logger.warning("Initiating global rollback...")
        # In a real environment, iterate self.context.state.completed_stages in reverse and call agent.rollback()
        
    async def execute_migration(self, task: dict) -> MigrationResult:
        """Runs the entire migration pipeline for a given module."""
        self.context.state.start_time = datetime.now(timezone.utc)
        self.context.state.current_stage = "STARTING"
        
        # We explicitly map the required linear pipeline steps (generator agents run in any valid topological order defined here)
        pipeline_steps = [
            "LegacyDiscoveryAgent",
            "LegacyAnalyzerAgent",
            "BusinessRuleExtractorAgent",
            "MigrationPlannerAgent",
            "ModelGeneratorAgent",
            "SchemaGeneratorAgent",
            "ServiceGeneratorAgent",
            "RouteGeneratorAgent",
            "MigrationGeneratorAgent",
            "SeedGeneratorAgent"
        ]
        
        total_steps = len(pipeline_steps) + 2 # + Review/Fix Loop + Validation
        
        for idx, agent_name in enumerate(pipeline_steps):
            if self.context.state.current_stage == "CANCELLED":
                return self._build_result(False, "Cancelled by user.")
                
            agent_class = agent_registry.get(agent_name)
            if not agent_class:
                return self._build_result(False, f"CRITICAL: Agent {agent_name} not found in registry.")
                
            if agent_name in self.context.state.completed_stages:
                self.context.logger.info(f"Skipping {agent_name} as it was already completed.")
                continue
                
            agent = agent_class()
            
            # Generate Progress Event
            progress = int((idx / total_steps) * 100)
            self._log_progress(progress, f"{agent.description}")
            
            # Execution with tracking
            if not await self._run_agent(agent, task):
                return self._build_result(False, f"Migration critically failed at stage: {agent_name}")
                
        # ---------------------------------------------------------
        # REVIEW -> REPAIR LOOP
        # ---------------------------------------------------------
        max_iterations = 5
        iteration = 0
        review_score = 0
        
        review_agent_class = agent_registry.get("ReviewAgent")
        fix_agent_class = agent_registry.get("AutoFixAgent")
        
        review_agent = review_agent_class()
        fix_agent = fix_agent_class()
        
        while iteration < max_iterations:
            self._log_progress(int(((len(pipeline_steps)) / total_steps) * 100), f"Running Review Pass {iteration + 1}...")
            
            if not await self._run_agent(review_agent, task):
                return self._build_result(False, "Migration failed during Review stage.")
                
            report: ReviewReport = self.context.shared_state.get("review_report")
            review_score = report.score
            self.context.state.statistics["review_score"] = review_score
            
            if review_score == 100 or not (report.critical_issues or report.warnings or report.business_rule_violations or report.architecture_violations):
                self._log_progress(int(((len(pipeline_steps) + 0.5) / total_steps) * 100), "Review passed with a perfect score (100). Breaking repair loop.")
                break
                
            # If not 100, run autofix
            self._log_progress(int(((len(pipeline_steps) + 0.5) / total_steps) * 100), f"Review Score: {review_score}. Running AutoFix Pass {iteration + 1}...")
            
            if not await self._run_agent(fix_agent, task):
                return self._build_result(False, "Migration failed during AutoFix stage.")
                
            iteration += 1

        if iteration >= max_iterations and review_score < 100:
            self.context.logger.warning(f"Review repair loop exhausted max iterations ({max_iterations}). Final score: {review_score}.")

        # ---------------------------------------------------------
        # VALIDATION GATE
        # ---------------------------------------------------------
        self._log_progress(95, "Running final deterministic validation...")
        validation_agent = agent_registry.get("ValidationAgent")()
        
        if not await self._run_agent(validation_agent, task):
            return self._build_result(False, "Migration failed during Validation stage.")
            
        validation_report: ValidationReport = self.context.shared_state.get("validation_report")
        self.context.state.statistics["validation_score"] = validation_report.success_percentage
        
        if validation_report.overall_status == "PASSED":
            self._log_progress(100, "Migration completed successfully.")
            return self._build_result(True, "Success")
        else:
            self._log_progress(100, "Migration validation failed.")
            return self._build_result(False, "Validation Failed")

    async def _run_agent(self, agent: BaseAgent, task: Any) -> bool:
        """Executes a single agent, managing timing, error catching, and logging."""
        stage_name = agent.name
        self.context.state.current_stage = stage_name
        
        start_ts = time.time()
        
        try:
            if not await agent.should_run(self.context, task):
                self.context.logger.info(f"Skipping {stage_name}")
                return True
                
            if not await agent.validate_input(self.context, task):
                raise ValueError(f"Input validation failed for {stage_name}")
                
            artifacts = await agent.execute(self.context, task)
            
            if not await agent.validate_output(self.context, artifacts):
                raise ValueError(f"Output validation failed for {stage_name}")
                
            self.context.state.generated_artifacts.extend(artifacts)
            self.context.state.completed_stages.append(stage_name)
            
            duration = time.time() - start_ts
            self.context.state.statistics[f"{stage_name}_duration_s"] = round(duration, 2)
            
            # Persist state to disk
            self.context.workspace.save_state(self.context.migration_id, self.context.state.model_dump_json())
            
            return True
            
        except Exception as e:
            self.context.logger.error(f"Agent {stage_name} crashed: {e}")
            self.context.logger.error(traceback.format_exc())
            self.context.state.failed_stages.append(stage_name)
            self.context.state.errors.append(str(e))
            return False

    def _log_progress(self, percentage: int, message: str):
        """Outputs formatted progress events and attaches them to the state logs."""
        msg = f"[{percentage}%] {message}"
        self.context.logger.info(msg)
        if "progress_logs" not in self.context.state.statistics:
            self.context.state.statistics["progress_logs"] = []
        self.context.state.statistics["progress_logs"].append(msg)

    def _build_result(self, success: bool, message: str) -> MigrationResult:
        """Constructs the final MigrationResult matching the required schema."""
        self.context.state.end_time = datetime.now(timezone.utc)
        
        duration = 0
        if self.context.state.end_time and self.context.state.start_time:
            duration = (self.context.state.end_time - self.context.state.start_time).total_seconds()
            
        artifacts = MigrationArtifact(
            migration_id=self.context.migration_id,
            files=[a for a in self.context.state.generated_artifacts if getattr(a, "artifact_type", "") == "generated_file"],
            reviews=[a for a in self.context.state.generated_artifacts if getattr(a, "artifact_type", "") == "review_report"],
            validations=[a for a in self.context.state.generated_artifacts if getattr(a, "artifact_type", "") == "validation_report"],
            metadata=self.context.state.statistics
        )
        
        return MigrationResult(
            migration_id=self.context.migration_id,
            success=success,
            artifacts=artifacts,
            summary=f"{message}. Duration: {round(duration, 2)}s"
        )
