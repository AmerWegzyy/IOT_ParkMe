# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build specification for Brain Music Sync.
This compiles the Python application into an executable for Windows/Linux/macOS.
"""

import os
import sys

# Since this spec is in setup/, we need to reference the project root
project_root = os.path.dirname(SPECPATH)

block_cipher = None

# Determine which icon to use based on platform
icon_path = None
if sys.platform == 'darwin':  # macOS
    icon_file = os.path.join(SPECPATH, 'App.icns')
    if os.path.exists(icon_file):
        icon_path = icon_file
elif sys.platform == 'win32':  # Windows
    icon_file = os.path.join(SPECPATH, 'App.ico')
    if os.path.exists(icon_file):
        icon_path = icon_file

# Analysis: Collect all dependencies
a = Analysis(
    [os.path.join(project_root, 'server/gui_app.py')],
    pathex=[],
    binaries=[],
    datas=[
        # No need to bundle MIDI files - they'll be external and writable
        # Include one default base model (optional)
        (os.path.join(project_root, 'server/utils/prediction_model/results/models/lgbm_model.joblib'), 'server/utils/prediction_model/results/models'),
    ],
    hiddenimports=[
        # Tkinter support (critical for macOS)
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        '_tkinter',
        # Scikit-learn internals (required for LightGBM/Ridge)
        'sklearn.utils._cython_blas',
        'sklearn.neighbors.typedefs',
        'sklearn.neighbors.quad_tree',
        'sklearn.tree._utils',
        'sklearn.utils._weight_vector',
        # ML libraries
        'lightgbm',
        'lightgbm.sklearn',
        'optuna',
        'optuna.storages',
        'joblib',
        # MIDI support
        'mido',
        'mido.backends',
        'mido.backends.rtmidi',
        'rtmidi',
        # Data science stack
        'pandas',
        'numpy',
        'matplotlib',
        'matplotlib.backends',
        'matplotlib.backends.backend_tkagg',
        'PIL',
        'PIL._tkinter_finder',
        # Serial communication
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        # Standard library (sometimes missed)
        'queue',
        'threading',
        'subprocess',
        'json',
        'shutil',  # For get_python_executable
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary packages to reduce size
        'pytest',
        'IPython',
        'jupyter',
        'sphinx',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BrainMusicSync',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app - no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,  # Custom app icon (platform-specific)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BrainMusicSync',
)

# macOS App Bundle (optional, creates .app structure)
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='BrainMusicSync.app',
        icon=icon_path,
        bundle_identifier='com.brainmusicsync.app',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSHighResolutionCapable': 'True',
            'CFBundleName': 'Brain Music Sync',
            'CFBundleDisplayName': 'Brain Music Sync',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
        },
    )

