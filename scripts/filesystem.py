"""
Reusable filesystem helpers for safe, atomic, and reliable disk operations.
"""
import os
import shutil
import hashlib
import tempfile
from pathlib import Path
from typing import Optional
from filecmp import dircmp

def calculate_hash(content: str) -> str:
    """Calculates SHA-256 hash of a string."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def create_directory(path: str) -> None:
    """Creates a directory safely (does nothing if it already exists)."""
    os.makedirs(path, exist_ok=True)

def delete_directory(path: str) -> None:
    """Deletes a directory and all its recursive contents safely."""
    if os.path.exists(path) and os.path.isdir(path):
        shutil.rmtree(path)

def copy(src: str, dst: str) -> None:
    """Copies a file or an entire directory."""
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        # Ensures destination directory exists before copying
        create_directory(os.path.dirname(dst))
        shutil.copy2(src, dst)

def move(src: str, dst: str) -> None:
    """Moves a file or directory."""
    create_directory(os.path.dirname(dst))
    shutil.move(src, dst)

def rename(src: str, dst: str) -> None:
    """Renames a file or directory."""
    os.rename(src, dst)

def backup(path: str, backup_dir: str) -> str:
    """Creates a timestamp-independent backup of a file or directory."""
    create_directory(backup_dir)
    basename = os.path.basename(path)
    dst = os.path.join(backup_dir, f"{basename}.bak")
    copy(path, dst)
    return dst

def restore(backup_path: str, original_path: str) -> None:
    """Restores a backup over the original path."""
    if os.path.exists(original_path):
        if os.path.isdir(original_path):
            delete_directory(original_path)
        else:
            os.remove(original_path)
    copy(backup_path, original_path)

def read(path: str) -> str:
    """Reads text content from a file."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_atomic(path: str, content: str) -> None:
    """
    Writes content to a file atomically.
    This prevents race conditions or partial file corruption if the process crashes mid-write.
    """
    directory = os.path.dirname(path)
    if directory:
        create_directory(directory)
    
    # Create temp file in same directory to ensure it's on the same filesystem
    fd, temp_path = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        # Atomic replace operation
        os.replace(temp_path, path)
    except Exception as e:
        os.remove(temp_path)
        raise e

def safe_overwrite(path: str, content: str, backup_dir: Optional[str] = None) -> None:
    """Backs up an existing file (if requested) before overwriting it atomically."""
    if os.path.exists(path) and backup_dir:
        backup(path, backup_dir)
    write_atomic(path, content)

def get_temp_file() -> str:
    """Creates a temporary file and returns its absolute path."""
    fd, path = tempfile.mkstemp()
    os.close(fd)
    return path

def directory_diff(dir1: str, dir2: str) -> dircmp:
    """Returns a native directory comparison object for identifying altered files."""
    return dircmp(dir1, dir2)
