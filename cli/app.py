"""
CLI Application.
Registers Typer commands and provides the main entry point.
"""
import typer
from cli import commands

app = typer.Typer(
    name="erp",
    help="ERP Migration Platform CLI. The single entry point for orchestrating Legacy C++ to Python migrations.",
    add_completion=False
)

@app.callback()
def main():
    from config.settings import settings
    from rich.console import Console
    from rich.panel import Panel
    
    console = Console()
    provider_name = settings.llm_provider.capitalize()
    if provider_name.lower() == "openai":
        model_name = settings.openai_model
    elif provider_name.lower() == "gemini":
        model_name = settings.gemini_model
    elif provider_name.lower() == "openrouter":
        model_name = settings.openai_model # Reusing openai_model for openrouter for now
    else:
        model_name = "Unknown"
        
    info = (
        f"[bold cyan]Software Migration Platform[/bold cyan]\n\n"
        f"[bold]LLM Provider:[/bold] {provider_name}\n"
        f"[bold]Model:[/bold] {model_name}"
    )
    console.print(Panel(info, border_style="cyan", expand=False))

app.command(name="migrate")(commands.migrate)
app.command(name="analyze")(commands.analyze)
app.command(name="review")(commands.review)
app.command(name="validate")(commands.validate)
app.command(name="resume")(commands.resume)
app.command(name="cancel")(commands.cancel)
app.command(name="status")(commands.status)
app.command(name="clean")(commands.clean)

if __name__ == "__main__":
    app()
