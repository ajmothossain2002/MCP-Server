"""
Settings manager for the application.
Loads configuration from environment variables and .env file.
Exposes a singleton `settings` instance.
"""
import sys
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, ValidationError

from config.models import OpenAIConfig, PathConfig, LoggingConfig, ProjectConfig

class Settings(BaseSettings):
    """
    Main settings configuration.
    Fields are automatically loaded from environment variables or .env file.
    Case-insensitive matching is applied (e.g., openai_api_key matches OPENAI_API_KEY).
    """
    # OpenAI Settings
    openai_api_key: str = Field(..., description="Required OpenAI API Key")
    openai_model: str = Field(default="gpt-4o", description="OpenAI Model")

    # Path Settings
    project_root: str = Field(..., description="Required project root path")
    erp_cpp_path: str = Field(..., description="Required C++ ERP path")
    erp_python_path: str = Field(..., description="Required Python ERP path")
    docs_path: str = Field(..., description="Documentation path")
    output_path: str = Field(..., description="Output path")
    temp_path: str = Field(..., description="Temporary path")

    # Logging Settings
    log_level: str = Field(default="INFO", description="Application log level")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def openai(self) -> OpenAIConfig:
        """Returns typed OpenAI configuration."""
        return OpenAIConfig(api_key=self.openai_api_key, model=self.openai_model)

    @property
    def paths(self) -> PathConfig:
        """Returns typed Path configuration."""
        return PathConfig(
            project_root=self.project_root,
            erp_cpp_path=self.erp_cpp_path,
            erp_python_path=self.erp_python_path,
            docs_path=self.docs_path,
            output_path=self.output_path,
            temp_path=self.temp_path
        )

    @property
    def logging(self) -> LoggingConfig:
        """Returns typed Logging configuration."""
        return LoggingConfig(log_level=self.log_level)

    @property
    def project(self) -> ProjectConfig:
        """Returns typed Project configuration."""
        return ProjectConfig()

# Expose a singleton instance of the settings
try:
    settings = Settings()
except ValidationError as e:
    # Validate required fields and raise descriptive errors if missing
    print("Configuration Error: Missing required environment variables or .env values.", file=sys.stderr)
    for error in e.errors():
        # Get the field name and format a clean error message
        field = error["loc"][0] if error["loc"] else "Unknown Field"
        print(f" - {str(field).upper()}: {error['msg']}", file=sys.stderr)
    sys.exit(1)
