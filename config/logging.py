"""
Logging configuration for the ERP Migration MCP project.
Uses Rich for colorful, beautiful terminal logging and also logs to a file.
"""
import logging
import os
from pathlib import Path
from rich.logging import RichHandler

from config.settings import settings

def get_logger(name: str) -> logging.Logger:
    """
    Creates and configures a logger with RichHandler and FileHandler.
    
    Args:
        name (str): The name of the logger (usually __name__).
        
    Returns:
        logging.Logger: A fully configured logger instance.
    """
    logger = logging.getLogger(name)
    
    # If the logger is already configured, return it to prevent duplicate logs
    if logger.hasHandlers():
        return logger
        
    log_level_str = settings.logging.log_level.upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    logger.setLevel(log_level)
    logger.propagate = False
    
    # Rich console handler for beautiful colored outputs
    rich_handler = RichHandler(
        level=log_level,
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_level=True,
        show_path=False
    )
    # The format string for rich doesn't need timestamp and level since RichHandler handles it
    rich_formatter = logging.Formatter("%(message)s")
    rich_handler.setFormatter(rich_formatter)
    logger.addHandler(rich_handler)
    
    # File handler for persistent logging
    log_dir = Path(settings.paths.temp_path) / "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    file_handler = logging.FileHandler(
        log_dir / "erp_migration.log", 
        encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    
    # File logs should include everything (timestamps, levels, module name)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger
