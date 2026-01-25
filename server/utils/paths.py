"""
Cross-platform path resolver for development and compiled (PyInstaller) modes.
Ensures logs, models, and plots are always saved next to the executable,
not inside the _internal folder.
"""
import sys
from pathlib import Path


def get_app_root():
    """
    Get the application root directory.
    Works in both development and PyInstaller compiled mode.
    
    Returns:
        Path: Root directory of the application
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable (PyInstaller)
        # sys.executable = "C:\Program Files\BrainMusicSync\BrainMusicSync.exe"
        return Path(sys.executable).parent
    else:
        # Running as Python script
        # __file__ = "C:\Project\server\utils\paths.py"
        return Path(__file__).resolve().parent.parent.parent


def get_logs_dir():
    """Get the logs directory (always external, writable)."""
    logs = get_app_root() / "server" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def get_models_dir():
    """Get the models directory (always external, writable)."""
    models = get_app_root() / "server" / "utils" / "prediction_model" / "results" / "models"
    models.mkdir(parents=True, exist_ok=True)
    return models


def get_plots_dir():
    """Get the plots directory (always external, writable)."""
    plots = get_app_root() / "server" / "utils" / "prediction_model" / "results" / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    return plots


def get_midi_dir():
    """
    Get the MIDI files directory (always external, writable).
    Users can add new MIDI files anytime.
    """
    midi = get_app_root() / "midi_files"
    midi.mkdir(parents=True, exist_ok=True)
    return midi


def get_research_dir():
    """Get the prediction model directory (legacy name for compatibility)."""
    prediction_model = get_app_root() / "server" / "utils" / "prediction_model"
    prediction_model.mkdir(parents=True, exist_ok=True)
    return prediction_model


def get_source_scripts_dir():
    """
    Get the directory containing Python source scripts for training/augmentation.
    In frozen mode, returns the actual source location (not dist folder).
    In development mode, returns the same as get_research_dir().
    """
    if getattr(sys, 'frozen', False):
        # In frozen mode, look for scripts in the source directory
        # The user should run the compiled app from the project root or keep source alongside
        exe_dir = Path(sys.executable).parent
        
        # Try to find the source directory relative to the executable
        # Case 1: Executable is in dist/BrainMusicSync/, source is at ../../server/utils/prediction_model/
        source_path = exe_dir.parent.parent / "server" / "utils" / "prediction_model"
        if source_path.exists():
            return source_path
        
        # Case 2: Executable is at project root, source is at server/utils/prediction_model/
        source_path = exe_dir / "server" / "utils" / "prediction_model"
        if source_path.exists():
            return source_path
        
        # Case 3: Fall back to app_root (might not have scripts, but at least consistent)
        return get_research_dir()
    else:
        # Development mode: same as get_research_dir()
        return get_research_dir()


def get_project_root():
    """Alias for get_app_root() for backwards compatibility."""
    return get_app_root()

