"""
Workspace Manager for orchestrating isolated migration environments.
"""
import os
import uuid
from pathlib import Path
from typing import List, Optional

from config.settings import settings
from shared.artifacts import BaseArtifact
from scripts import filesystem

class WorkspaceManager:
    """
    Manages isolated workspaces for each concurrent migration run.
    Ensures safe operations, tracks backups, and isolates generated artifacts.
    """
    
    def __init__(self, base_workspace_dir: Optional[str] = None):
        # Resolve the root workspace directory from configuration
        self.base_dir = Path(base_workspace_dir or os.path.join(settings.paths.temp_path, "workspace"))
        self.runs_dir = self.base_dir / "runs"
        filesystem.create_directory(str(self.runs_dir))
        
    def create_workspace(self, custom_id: Optional[str] = None) -> str:
        """
        Creates a new, highly isolated workspace for a migration run.
        
        Args:
            custom_id (Optional[str]): Optional ID, generates UUIDv4 if None.
            
        Returns:
            str: The unique migration ID representing the workspace.
        """
        migration_id = custom_id or str(uuid.uuid4())
        workspace_path = self.runs_dir / migration_id
        
        # Standardized subfolder structure per run
        folders = ["input", "context", "prompts", "output", "review", "logs", "reports"]
        for folder in folders:
            filesystem.create_directory(str(workspace_path / folder))
            
        return migration_id

    def get_workspace_path(self, migration_id: str) -> Path:
        """Helper to get the absolute root path for a specific run."""
        return self.runs_dir / migration_id

    def write_artifact(self, migration_id: str, folder: str, artifact: BaseArtifact) -> str:
        """
        Writes an artifact and its serialized metadata to the workspace atomically.
        
        Args:
            migration_id (str): The run ID.
            folder (str): The target subfolder (e.g., 'output', 'review').
            artifact (BaseArtifact): The Pydantic artifact to save.
            
        Returns:
            str: The absolute path to the saved artifact's text file.
        """
        target_dir = self.get_workspace_path(migration_id) / folder
        
        # Resolve the specific file path inside the folder
        content_path = target_dir / artifact.path
        
        # Guarantee checksum is set before saving
        if not artifact.checksum:
            artifact.checksum = filesystem.calculate_hash(artifact.content)
            
        # Write the raw code/content atomically
        filesystem.write_atomic(str(content_path), artifact.content)
        
        # Save the full Pydantic metadata payload alongside the file
        meta_path = str(content_path) + ".meta.json"
        filesystem.write_atomic(meta_path, artifact.model_dump_json(indent=2))
        
        return str(content_path)

    def read_artifact(self, migration_id: str, folder: str, path: str) -> str:
        """Reads raw content of an artifact file from a specific workspace."""
        target_path = self.get_workspace_path(migration_id) / folder / path
        return filesystem.read(str(target_path))

    def list_artifacts(self, migration_id: str, folder: str) -> List[str]:
        """Lists all files in a specific workspace folder, ignoring JSON metadata files."""
        target_dir = self.get_workspace_path(migration_id) / folder
        if not target_dir.exists():
            return []
        
        results = []
        for root, _, files in os.walk(target_dir):
            for file in files:
                if not file.endswith(".meta.json"):
                    results.append(os.path.relpath(os.path.join(root, file), target_dir))
        return results

    def backup_original(self, migration_id: str, original_path: str) -> str:
        """Backs up an original ERP file into the workspace's input folder before modifying it."""
        backup_dir = str(self.get_workspace_path(migration_id) / "input")
        return filesystem.backup(original_path, backup_dir)

    def restore_backup(self, migration_id: str, original_path: str) -> None:
        """Restores a previously backed up file from the workspace, overriding the active file."""
        basename = os.path.basename(original_path)
        backup_path = str(self.get_workspace_path(migration_id) / "input" / f"{basename}.bak")
        filesystem.restore(backup_path, original_path)

    def archive(self, migration_id: str, archive_path: str) -> str:
        """
        Archives the entire workspace run into a zip file.
        Useful for exporting migration results, debugging, or CI/CD upload.
        """
        import shutil
        target_dir = str(self.get_workspace_path(migration_id))
        
        # make_archive appends .zip automatically, so we strip it if provided
        base_name = archive_path
        if base_name.endswith('.zip'):
            base_name = base_name[:-4]
            
        return shutil.make_archive(base_name, 'zip', target_dir)

    def cleanup(self, migration_id: str) -> None:
        """Deletes a workspace completely to free up disk space."""
        target_dir = str(self.get_workspace_path(migration_id))
        filesystem.delete_directory(target_dir)
