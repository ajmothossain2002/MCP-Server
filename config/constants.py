"""
Application constants for the ERP Migration MCP project.
Contains immutable, non-configurable values such as supported types, stages, etc.
"""
from typing import Set, List

# Supported Languages
SUPPORTED_LANGUAGES: Set[str] = {"cpp", "python"}

# Supported ERP Modules
SUPPORTED_ERP_MODULES: List[str] = [
    "core",
    "auth",
    "finance",
    "inventory",
    "hr",
    "sales"
]

# Prompt template names
PROMPT_LEGACY_ANALYZER: str = "legacy_analyzer_prompt"
PROMPT_CODE_GENERATOR: str = "code_generator_prompt"
PROMPT_CODE_REVIEWER: str = "code_reviewer_prompt"
PROMPT_INTEGRATION: str = "integration_prompt"
PROMPT_QA: str = "qa_prompt"

# File extensions
EXT_CPP_HEADER: str = ".h"
EXT_CPP_SOURCE: str = ".cpp"
EXT_PYTHON: str = ".py"
EXT_MARKDOWN: str = ".md"

# Migration stages
STAGE_ANALYSIS: str = "ANALYSIS"
STAGE_GENERATION: str = "GENERATION"
STAGE_REVIEW: str = "REVIEW"
STAGE_INTEGRATION: str = "INTEGRATION"
STAGE_TESTING: str = "TESTING"
STAGE_FINALIZATION: str = "FINALIZATION"
