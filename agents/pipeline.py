"""
PipelineExecutor to run a sequence of agents over an AgentContext.
"""
import time
from datetime import datetime, timezone
from typing import List, Any
from agents.base import BaseAgent
from agents.context import AgentContext
from shared.artifacts import MigrationResult, MigrationArtifact
from config.logging import get_logger

logger = get_logger(__name__)

class PipelineExecutor:
    """
    Executes a series of agents sequentially.
    Handles telemetry, input/output validation, error catching, and atomic rollbacks.
    """
    
    def __init__(self, agents: List[BaseAgent]):
        self.agents = agents
        
    async def run(self, context: AgentContext, task: Any) -> MigrationResult:
        """
        Runs the registered agents in sequence over the provided task.
        
        Args:
            context (AgentContext): The dependency-injected context.
            task (Any): The arbitrary task definition for this pipeline.
            
        Returns:
            MigrationResult: The final serialized summary of the run.
        """
        context.state.start_time = datetime.now(timezone.utc)
        executed_agents: List[BaseAgent] = []
        success = True
        
        for agent in self.agents:
            stage_name = agent.name
            context.state.current_stage = stage_name
            
            try:
                # 1. Check if the agent is needed
                if not await agent.should_run(context, task):
                    context.logger.info(f"Skipping agent: {stage_name}")
                    continue
                    
                # 2. Pre-flight input validation
                context.logger.info(f"Validating input for: {stage_name}")
                if not await agent.validate_input(context, task):
                    raise ValueError(f"Input validation failed for {stage_name}")
                    
                # 3. Execution (The core LLM / parsing work)
                context.logger.info(f"Executing: {stage_name}")
                start_ts = time.time()
                artifacts = await agent.execute(context, task)
                duration = time.time() - start_ts
                
                context.state.statistics[f"{stage_name}_duration_seconds"] = round(duration, 2)
                
                # 4. Post-flight output validation
                context.logger.info(f"Validating output for: {stage_name}")
                if not await agent.validate_output(context, artifacts):
                    raise ValueError(f"Output validation failed for {stage_name}")
                    
                # Record artifacts and move forward
                context.state.generated_artifacts.extend(artifacts)
                context.state.completed_stages.append(stage_name)
                executed_agents.append(agent)
                
            except Exception as e:
                context.logger.error(f"Pipeline crashed at stage {stage_name}: {e}")
                context.state.failed_stages.append(stage_name)
                context.state.errors.append(str(e))
                success = False
                break
                
        # Handle Rollbacks if the pipeline failed partway through
        if not success:
            context.logger.warning("Initiating rollback sequence for completed agents...")
            # Rollback in reverse order
            for agent in reversed(executed_agents):
                try:
                    await agent.rollback(context, task)
                    context.logger.info(f"Rollback successful for {agent.name}")
                except Exception as rollback_err:
                    context.logger.error(f"Rollback CRITICALLY failed for {agent.name}: {rollback_err}")
                    
        # Finalize State
        context.state.end_time = datetime.now(timezone.utc)
        context.state.current_stage = "COMPLETED" if success else "FAILED"
        
        # Assemble final result
        files = [a for a in context.state.generated_artifacts if getattr(a, "artifact_type", "") in ["generated_file", "modified_file", "deleted_file"]]
        reviews = [a for a in context.state.generated_artifacts if getattr(a, "artifact_type", "") == "review_report"]
        validations = [a for a in context.state.generated_artifacts if getattr(a, "artifact_type", "") == "validation_report"]
        
        return MigrationResult(
            migration_id=context.migration_id,
            success=success,
            artifacts=MigrationArtifact(
                migration_id=context.migration_id,
                files=files,
                reviews=reviews,
                validations=validations,
                metadata=context.state.statistics
            ),
            summary=f"Pipeline finished with success={success}. Errors: {len(context.state.errors)}"
        )
