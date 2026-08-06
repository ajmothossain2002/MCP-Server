"""
CLI Progress Tracking.
Provides live updating progress bars via Rich Progress.
"""
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn

def create_progress_context():
    """Returns a Rich Progress context manager with customized columns."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        transient=False
    )
