"""
Prompt manager for loading and rendering Jinja2 prompt templates.
Ensures prompts are not hardcoded inside Python logic.
"""
from pathlib import Path
from typing import Dict, Any
import jinja2

from config.settings import settings
from shared.response import PromptMetadata

class PromptManager:
    """Manages prompt templates loading and rendering."""
    
    def __init__(self):
        # We assume prompts live in <project_root>/prompts/
        self.prompts_dir = Path(settings.paths.project_root) / "prompts"
        
        # Ensure the prompts directory exists
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup Jinja2 environment for safe and clean rendering
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.prompts_dir)),
            autoescape=jinja2.select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

    def load_prompt(self, name: str) -> jinja2.Template:
        """
        Loads a Jinja2 template by name from the prompts directory.
        
        Args:
            name (str): The filename of the template (e.g., 'legacy_analyzer.jinja').
            
        Returns:
            jinja2.Template: The loaded template object.
        """
        if not name.endswith(".jinja") and not name.endswith(".txt") and not name.endswith(".md"):
            name = f"{name}.jinja"
            
        return self.env.get_template(name)

    def render_prompt(self, name: str, variables: Dict[str, Any]) -> str:
        """
        Loads and renders a prompt template with provided variables.
        
        Args:
            name (str): The filename of the template.
            variables (Dict[str, Any]): Variables to inject into the template context.
            
        Returns:
            str: The fully rendered prompt string.
        """
        template = self.load_prompt(name)
        return template.render(**variables)

    def get_metadata(self, name: str, variables: Dict[str, Any]) -> PromptMetadata:
        """
        Helper to return metadata for tracking prompts across the system.
        
        Args:
            name (str): The template name.
            variables (Dict[str, Any]): The variables used.
            
        Returns:
            PromptMetadata: Strongly typed tracking object.
        """
        return PromptMetadata(template_name=name, variables=variables)

# Expose a singleton manager
prompt_manager = PromptManager()
