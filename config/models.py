"""
Typed configuration models for the ERP Migration MCP project.
"""
from pydantic import BaseModel, Field

class OpenAIConfig(BaseModel):
    """Configuration for OpenAI services."""
    api_key: str = Field(..., description="The API key for authenticating with OpenAI.")
    model: str = Field(default="gpt-4o", description="The default OpenAI model to use for generations.")

class PathConfig(BaseModel):
    """Project paths configuration."""
    project_root: str = Field(..., description="Absolute path to the root of the MCP tool project.")
    erp_cpp_path: str = Field(..., description="Path to the legacy C++ ERP repository.")
    erp_python_path: str = Field(..., description="Path to the target Python ERP repository.")
    docs_path: str = Field(..., description="Path to store or read documentation.")
    output_path: str = Field(..., description="Path for saving generated Python files and artifacts.")
    temp_path: str = Field(..., description="Path for temporary files generated during migration.")

class LoggingConfig(BaseModel):
    """Logging configuration."""
    log_level: str = Field(default="INFO", description="Log level (e.g., DEBUG, INFO, WARNING, ERROR).")

class ProjectConfig(BaseModel):
    """Aggregated project configurations."""
    name: str = Field(default="ERP Migration MCP", description="Project name.")
    version: str = Field(default="0.1.0", description="Project version.")
