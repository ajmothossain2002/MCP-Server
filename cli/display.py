"""
CLI Display Layer.
Leverages Rich Console and Rich Tables for formatted terminal output.
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def print_header(text: str):
    console.print(Panel(f"[bold cyan]{text}[/bold cyan]"))

def print_success(text: str):
    console.print(f"[bold green]✔[/bold green] {text}")
    
def print_error(text: str):
    console.print(f"[bold red]✖[/bold red] {text}")
    
def print_warning(text: str):
    console.print(f"[bold yellow]![/bold yellow] {text}")

def print_summary(duration: float, review_score: int, val_score: int, files: int, fixed: int, workspace: str):
    table = Table(title="Migration Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", justify="left")
    table.add_column("Value", style="green", justify="right")
    
    table.add_row("Duration", f"{duration}s")
    table.add_row("Review Score", f"{review_score}/100")
    table.add_row("Validation Score", f"{val_score}%")
    table.add_row("Generated Files", str(files))
    table.add_row("Fixed Files", str(fixed))
    table.add_row("Workspace Location", workspace)
    
    console.print(table)
