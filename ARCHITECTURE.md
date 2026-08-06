# ERP Migration MCP - Architectural Blueprint

This document serves as the foundational architectural blueprint for the **ERP Migration MCP** project. This project is a standalone developer tool designed to automate the migration of our legacy C++ ERP to the new Python ERP. 

## 1. Project Folder Structure

The project is structured to be modular, scalable, and separation-of-concerns oriented.

```text
erp-migration-mcp/
├── agents/             # AI agent implementations (e.g., C++ Reader, Python Generator, Reviewer)
├── mcp/                # MCP Servers exposing legacy codebase and Python codebase tools
├── workflows/          # Orchestration logic (LangGraph or custom state machines)
├── prompts/            # Centralized prompt templates for all agents
├── knowledge/          # Documentation, context, style guides for the target ERP
├── config/             # Configuration files (LLM settings, paths, DB credentials)
├── shared/             # Shared utilities (logging, models, errors)
├── cli/                # CLI entrypoints and UI (Typer/Rich)
├── tests/              # Unit and integration tests for the migration tooling
├── scripts/            # Build, deploy, and automation scripts
├── pyproject.toml      # Dependency management via uv
└── README.md
```

## 2. Technology Stack

The stack is heavily Python-centric to maximize compatibility with the target ERP environment and rich AI ecosystem.

- **Python**: Primary language. The target ERP is Python, making it seamless to share models, database connections, and test scripts.
- **OpenAI Responses API (Structured Outputs)**: Enforces strict adherence to schemas (via Pydantic) when generating code, reviewing code, or extracting business rules. This is crucial for predictable code generation.
- **MCP SDK (Model Context Protocol)**: Provides a standardized, secure way for agents to interact with file systems, run tests, and query databases without hardcoding context retrieval logic.
- **Typer**: For building the `erp-migrate` CLI tool. It is clean, modern, and type-safe.
- **Rich**: For building beautiful, readable terminal outputs. A long-running migration tool requires clear status bars, tables, and logging.
- **Docker SDK for Python**: Spin up isolated containers programmatically to safely run `alembic`, compile generated Python, and execute tests without polluting the host machine.
- **GitPython**: Automates branching, committing generated Python code, and managing the migration Git workflow natively from the tool.
- **SQLAlchemy & PostgreSQL**: For interacting with the target database to validate schemas, and potentially managing the internal state of the migration process.
- **Pydantic**: Essential for data validation and defining the structured outputs requested from the LLMs.
- **uv**: Extremely fast Python package management and virtual environment management, ensuring developers can bootstrap the tool quickly.

*(Note: FastAPI is intentionally omitted from the core tool as this is currently a CLI-driven developer tool, not a web service. However, it can be added later if a remote orchestration API is required.)*

## 3. Architecture

The system uses an **Orchestrator-Agent** pattern communicating over **MCP**.

### Components

1. **Orchestrator (`workflows/`)**: A state-machine (e.g., built on LangGraph or a custom workflow engine) that manages the lifecycle of migrating a module. It handles state, triggers agents in sequence, manages retries, and passes context.
2. **Agents (`agents/`)**:
   - **Legacy Analyzer**: Reads C++ code, extracts domain logic, data models, and business rules.
   - **Code Generator**: Takes the extracted rules and generates Python FastAPI endpoints, Pydantic models, and SQLAlchemy schemas.
   - **Reviewer**: Critiques the generated code against the `knowledge/` style guides.
   - **Integration Agent**: Modifies Swagger files, Alembic revisions, and configuration files.
   - **QA/Test Agent**: Generates Pytest test cases.
3. **MCP Servers (`mcp/`)**:
   - **Legacy MCP**: Exposes tools to read C++ files, search legacy git history, and parse C++ headers.
   - **Target MCP**: Exposes tools to read/write Python files, run `pytest`, run `alembic`, and interact with the Docker SDK.
4. **Prompt Library (`prompts/`)**: Version-controlled Jinja or format-string templates defining the persona and tasks for each agent.
5. **Knowledge Base (`knowledge/`)**: Markdown files defining "How we write Python", "Database conventions", and domain glossaries. Fed into the context of the agents by the Orchestrator.

### Communication
The Orchestrator dictates the flow. When an Agent is invoked, it is provided with tools exposed by the **MCP Servers**. The Agents do not directly access the file system; they request file contents or command execution through the MCP layer, ensuring strict boundaries and traceability.

## 4. Execution Flow: `erp-migrate task`

When a developer runs `erp-migrate task <module_name>`, the following flow executes until the module is fully migrated:

1. **CLI Invocation**: Typer parses the command. Rich initializes a live progress display.
2. **Analysis Phase**: The Orchestrator calls the *Legacy Analyzer Agent* via the *Legacy MCP Server* to read all C++ headers and source files related to `<module_name>`.
3. **Context Compilation**: The Orchestrator gathers the extracted business logic and pulls relevant guidelines from the *Knowledge Base*.
4. **Code Generation Phase**: The *Code Generator Agent* is invoked to produce SQLAlchemy models, Pydantic schemas, and FastAPI routers.
5. **Review Phase**: The *Reviewer Agent* checks the code. If flaws are found, the Orchestrator loops back to the Generation phase with the critique.
6. **Integration & DB Phase**: The *Integration Agent* generates Alembic migrations. The Orchestrator uses the *Docker SDK* to spin up an isolated PostgreSQL container and runs Alembic to verify the migration executes cleanly.
7. **Testing Phase**: The *QA Agent* writes tests. The Orchestrator runs them via the *Target MCP* in the isolated container.
8. **Finalization**: *GitPython* creates a new branch (e.g., `migration/<module_name>`), commits the generated files, and the CLI reports a successful migration with a summary table.
