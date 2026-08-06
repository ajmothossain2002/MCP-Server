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
