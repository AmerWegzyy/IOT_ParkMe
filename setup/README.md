# 🔧 Brain Music Sync - Build & Setup Guide

This folder contains everything needed to build the standalone application or run from source.

---

## 🚀 Quick Start

### 🪟 **Windows**
```batch
cd setup\Windows
build_app.bat           # Build portable .exe
```

### 🐧 **Linux** / 🍎 **macOS**
```bash
cd setup/Linux_Mac
chmod +x build_app.sh
./build_app.sh          # Build portable executable
```

**Output:** Portable application in `dist/BrainMusicSync/`

---

## 📦 Building Standalone Application

Build a portable executable that can run on any machine **without Python installed**.

### 🪟 **Windows Build**

#### **Build Command:**
```batch
cd setup\Windows
build_app.bat
```

#### **What It Does:**
- ✅ Sets up Python virtual environment (if needed)
- ✅ Installs all dependencies
- ✅ Builds executable with PyInstaller
- ✅ Copies MIDI files and 266 Default training sessions
- ✅ Asks if you want to create a desktop shortcut
- ✅ Launches the application

#### **Output:**
`dist\BrainMusicSync\BrainMusicSync.exe` (~200-300 MB)

#### **Requirements:**
- **Python 3.8+** installed and in PATH
- **pip** (comes with Python)

#### **Distribution:**
Share the entire `dist\BrainMusicSync\` folder:
- Compress to ZIP
- Copy to USB drive
- Upload to cloud storage

**Recipients can run `BrainMusicSync.exe` directly!**

---

### 🐧 **Linux Build** / 🍎 **macOS Build**

#### **Build Command:**
```bash
cd setup/Linux_Mac
chmod +x build_app.sh   # Only needed once
./build_app.sh
```

#### **What It Does:**
- ✅ Sets up Python virtual environment (if needed)
- ✅ Installs all dependencies
- ✅ Builds executable with PyInstaller
- ✅ Copies MIDI files and 266 Default training sessions
- ✅ Creates portable application
- ✅ Launches the application

#### **Output:**
`dist/BrainMusicSync/BrainMusicSync` (~200-300 MB)

#### **Requirements:**

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv python3-tk
```

**Fedora:**
```bash
sudo dnf install python3 python3-pip python3-tkinter
```

**Arch Linux:**
```bash
sudo pacman -S python python-pip tk
```

---

**🍎 macOS:**

> ## ⚠️ **HOMEBREW REQUIRED FOR macOS**
> 
> **macOS users MUST have [Homebrew](https://brew.sh) installed before building.**
> 
> The build script will automatically:
> - ✅ Verify Homebrew is installed (exits with instructions if not)
> - ✅ Check for tkinter availability
> - ✅ Auto-install `python-tk` if using Homebrew Python
> - ✅ Verify all dependencies before building

**Step-by-Step Installation:**

```bash
# Step 1: Install Homebrew (REQUIRED)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Step 2: Install Python via Homebrew
brew install python

# Step 3: Run the build script (it handles the rest automatically!)
cd setup/Linux_Mac
chmod +x build_app.sh
./build_app.sh
```

**Why Homebrew is Required:**
- **tkinter** (GUI library) is not included with Homebrew's Python by default
- **tkinter cannot be installed via pip** - it's a system package that requires Homebrew
- The build script will auto-install `python-tk@<version>` if needed
- Ensures all dependencies work correctly on macOS

**Alternative (Without Homebrew):**
If you prefer not to use Homebrew, install Python from [python.org](https://www.python.org/downloads/) which includes tkinter by default. **However, the build script will still check for Homebrew and may show a warning.**

#### **Distribution:**

**Create Archive (Linux):**
```bash
cd dist
tar -czf BrainMusicSync.tar.gz BrainMusicSync/
```

**Create Archive (macOS):**
```bash
cd dist
zip -r BrainMusicSync.zip BrainMusicSync/
```

**Recipients extract and run `./BrainMusicSync`**

---

## 🧹 Cleaning Build Artifacts

Remove all build files to start fresh or reclaim disk space.

### 🪟 **Windows**
```batch
cd setup\Windows
build_app.bat --clean   # or -c
```

### 🐧 **Linux** / 🍎 **macOS**
```bash
cd setup/Linux_Mac
./build_app.sh --clean  # or -c
```

**This removes:**
- ✅ `build/` directory
- ✅ `dist/` directory
- ✅ Python cache files (`__pycache__`, `*.pyc`)
- ✅ Desktop shortcut (Windows only)
- ✅ Terminates any running instances

---

## 👨‍💻 For Developers (Run from Source)

Run the application **directly from Python** without building an executable. Faster for development and testing.

### 🪟 **Windows Development**

#### **First Time Setup:**
```batch
cd setup\Windows\dev
setup_env.bat           # Create venv and install dependencies
```

#### **Run Application:**
```batch
cd setup\Windows\dev
start_app.bat           # Launch GUI from source
```

---

### 🐧 **Linux / macOS Development**

#### **First Time Setup:**
```bash
cd setup/Linux_Mac/dev
chmod +x setup_env.sh start_app.sh   # Only needed once
./setup_env.sh          # Create venv and install dependencies
```

#### **Run Application:**
```bash
cd setup/Linux_Mac/dev
./start_app.sh          # Launch GUI from source
```

**Benefits of running from source:**
- ⚡ Faster iteration (no rebuild needed)
- 🔍 Better debugging with full tracebacks
- 📝 Direct code editing and testing
- 💾 No disk space wasted on builds

---

## 🐛 Troubleshooting

### 🪟 **Windows Issues**

#### **"Python is not installed or not in PATH"**
- Install Python 3.8+ from [python.org](https://python.org)
- Make sure to check "Add Python to PATH" during installation

#### **"Access is denied" or "file is in use" during build**
```batch
taskkill /F /IM BrainMusicSync.exe
build_app.bat
```

#### **Build fails with "Failed to create virtual environment"**
```batch
python -m ensurepip
python -m pip install --upgrade pip
build_app.bat
```

---

### 🐧 **Linux Issues**

#### **"python3: command not found"**
```bash
# Ubuntu/Debian
sudo apt install python3 python3-pip python3-venv

# Fedora
sudo dnf install python3 python3-pip

# Arch
sudo pacman -S python python-pip
```

#### **"tkinter not found"**
```bash
# Ubuntu/Debian
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

#### **"Permission denied" when running scripts**
```bash
chmod +x build_app.sh
chmod +x dist/BrainMusicSync/BrainMusicSync
```

---

### 🍎 **macOS Issues**

#### **"command not found: brew"**
Homebrew is not installed. Install it:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then install Python:
```bash
brew install python
```

#### **"command not found: python3"**
```bash
brew install python
```

Or download from [python.org](https://www.python.org/downloads/) (includes tkinter by default).

#### **"tkinter not found" (Manual Fix)**
The build script should install this automatically for Homebrew Python, but if it fails:

```bash
# Find your Python version
python3 --version

# Install python-tk for your version (e.g., 3.14, 3.13, etc.)
brew install python-tk@3.14
```

**Why this happens:**
- Homebrew's Python doesn't include tkinter by default
- tkinter is required for the GUI interface
- The build script detects this and auto-installit, but you can install manually if needed

#### **Gatekeeper blocks app from running**
```bash
# Remove quarantine attribute
xattr -d com.apple.quarantine dist/BrainMusicSync.app/Contents/MacOS/BrainMusicSync
```

Or:
1. Right-click on `BrainMusicSync.app`
2. Select "Open"
3. Click "Open" in the dialog (first time only)

---

## 🖥️ Creating Desktop Shortcuts

### 🪟 **Windows**
A popup will appear after build completion asking if you want a shortcut.

Or manually:
1. Right-click on `dist\BrainMusicSync\BrainMusicSync.exe`
2. Select "Create shortcut"
3. Move shortcut to Desktop

---

### 🐧 **Linux**
Create `~/.local/share/applications/brain-music-sync.desktop`:
```ini
[Desktop Entry]
Name=Brain Music Sync
Exec=/full/path/to/dist/BrainMusicSync/BrainMusicSync
Icon=/full/path/to/setup/App.ico
Type=Application
Categories=Audio;Music;Science;
Terminal=false
```

Make executable:
```bash
chmod +x ~/.local/share/applications/brain-music-sync.desktop
```

---

### 🍎 **macOS**
1. Open Finder
2. Navigate to `dist/BrainMusicSync/`
3. Drag `BrainMusicSync` to Applications folder or Desktop
4. Right-click → Open (first time to bypass Gatekeeper)

---

## 📂 Project Structure

```
setup/
├── README.md              # This file
├── build.spec             # PyInstaller configuration
├── App.ico                # Application icon
│
├── Windows/               # Windows build scripts
│   ├── build_app.bat      # Build + clean script
│   └── dev/               # Development scripts
│       ├── setup_env.bat  # Setup Python environment
│       └── start_app.bat  # Run from source
│
└── Linux_Mac/             # Linux/macOS build scripts
    ├── build_app.sh       # Build + clean script
    └── dev/               # Development scripts
        ├── setup_env.sh   # Setup Python environment
        └── start_app.sh   # Run from source
```

---

## 📝 Build Notes

- **Build time:** 3-5 minutes (first time)
- **Rebuild time:** 1-2 minutes (cached dependencies)
- **Output size:** ~200-300 MB (includes ML models, MIDI files, and 266 training sessions)
- **Python version:** 3.8+ required
- **Virtual environment:** Created automatically in `.venv/`
- **Platform-specific:** Each platform requires its own build

---

## 🎯 What's Included in the Build

The standalone application includes:

- ✅ Python interpreter and all dependencies
- ✅ All source code and ML models
- ✅ 266 Default training sessions (for base model)
- ✅ All MIDI files
- ✅ GUI application with full features
- ✅ Model training and prediction capabilities
- ✅ Serial communication support
- ✅ Live BPM visualization

**External (writable after deployment):**
- User session logs (`server/logs/`)
- Trained models (`server/utils/prediction_model/results/models/`)
- Training plots (`server/utils/prediction_model/results/plots/`)
- MIDI files (can be added/modified)

---

## 🔗 Related Documentation

- **Main Project:** [`../README.md`](../README.md)
- **Build Spec:** [`build.spec`](build.spec)
- **Requirements:** [`../requirements.txt`](../requirements.txt)

---

## 💡 Tips

1. **Clean builds are rarely needed** - PyInstaller is smart about caching
2. **Keep the `dist/` folder intact** - distribute the entire folder, not just the executable
3. **Test on a clean machine** - ensure no dependencies are missing
4. **Use dev mode for rapid iteration** - only build for deployment
5. **The `.venv` folder is reused** - subsequent builds are faster

---

**Questions or issues?** Check the main [`README.md`](../README.md) or create an issue on GitHub.
