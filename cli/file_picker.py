"""
File Picker utility using native OS file dialogs via tkinter.
"""
import os
from typing import Optional
from tkinter import Tk
from tkinter.filedialog import askopenfilename

def _open_picker(title: str, filetypes: list[tuple[str, str]]) -> Optional[str]:
    """Helper to initialize Tk, hide the root window, and open a file picker."""
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    
    file_path = askopenfilename(
        title=title,
        filetypes=filetypes
    )
    
    root.destroy()
    
    if not file_path:
        return None
        
    return os.path.normpath(file_path)

def select_proto() -> Optional[str]:
    """Opens a native file picker for selecting a Protocol Buffer file."""
    return _open_picker(
        title="Select Proto File",
        filetypes=[("Proto Files", "*.proto"), ("All Files", "*.*")]
    )

def select_header() -> Optional[str]:
    """Opens a native file picker for selecting a C++ Header file."""
    return _open_picker(
        title="Select Header File",
        filetypes=[("C++ Headers", "*.hpp"), ("All Files", "*.*")]
    )

def select_source() -> Optional[str]:
    """Opens a native file picker for selecting a C++ Source file."""
    return _open_picker(
        title="Select Source File",
        filetypes=[("C++ Source", "*.cpp"), ("All Files", "*.*")]
    )

def select_database_initializer() -> Optional[str]:
    """Opens a native file picker for selecting the DatabaseInitializer.cpp file."""
    return _open_picker(
        title="Select DatabaseInitializer.cpp",
        filetypes=[("C++ Source", "*.cpp"), ("All Files", "*.*")]
    )
