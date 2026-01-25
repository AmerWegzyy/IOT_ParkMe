# 🎵 Brain-Music Research Platform

**Real-time music synchronization system for gait cueing research**

A neuro-adaptive music controller that synchronizes music tempo to walking cadence in real-time, developed for investigating music-based gait cueing strategies and rhythmic auditory stimulation research.

**Developed by:** Sleeman Nabwani, Rund Subih & Samir Zarka  
**Supervised by:** Professor Eitan Globerson  
**Institution:** ICST - The Interdisciplinary Center for Smart Technologies, Technion  
**Course:** IoT Project 236333

---

## 📋 Table of Contents

- [Overview](#-overview)
- [System Architecture](#-system-architecture)
- [Key Features](#-key-features)
- [Hardware Components](#-hardware-components)
- [Software Modes](#-software-modes)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Usage Guide](#-usage-guide)
- [Machine Learning Pipeline](#-machine-learning-pipeline)
- [Project Structure](#-project-structure)

---

## 🎯 Overview

This system provides a **research platform** for investigating music-based gait cueing and rhythmic auditory stimulation. It enables tempo alignment between music and walking pace, supporting controlled evaluation of synchronization strategies and their potential therapeutic value.

### What It Does

1. **Detects Steps**: Force-sensitive resistors (FSRs) on each foot detect when steps occur
2. **Calculates BPM**: ESP32 microcontroller measures step intervals and computes walking cadence
3. **Adjusts Music**: Python backend modifies MIDI playback speed to match user's walking pace
4. **Predicts Smoothly**: LightGBM machine learning model anticipates tempo changes for jitter-free transitions
5. **Logs Everything**: Records high-resolution data for research analysis

### Use Cases

- **Gait Research**: Investigate rhythmic auditory cueing for gait improvement
- **Gait Analysis**: Study walking patterns and variability
- **Tempo Entrainment**: Research music-movement synchronization
- **Rehabilitation**: Provide real-time auditory feedback during walking therapy

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HARDWARE LAYER                                │
├─────────────────┬──────────────────┬────────────────────────────────┤
│  FSR Sensors    │   ESP32 Sender   │    ESP32 Receiver              │
│  (Left/Right)   │   (On Foot)      │    (Stationary)                │
│                 │                  │                                │
│  • Resistance   │  • Read voltage  │  • Receive via ESP-NOW         │
│    varies with  │  • Detect steps  │  • Calculate BPM               │
│    pressure     │  • ESP-NOW TX    │  • Serial → Python             │
└─────────────────┴──────────────────┴────────────────────────────────┘
                           ↓ ESP-NOW (Wireless)
                           ↓ Serial (USB)
┌─────────────────────────────────────────────────────────────────────┐
│                     PYTHON BACKEND (main.py)                         │
├─────────────────┬──────────────────┬────────────────────────────────┤
│  Serial Comms   │  BPM Engine      │    MIDI Player                 │
│                 │                  │                                │
│  • Read steps   │  • Mode logic    │  • Load MIDI files             │
│  • Parse data   │  • Smoothing     │  • Tempo scaling               │
│  • Commands     │  • ML prediction │  • Playback sync               │
└─────────────────┴──────────────────┴────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     GUI APPLICATION (gui_app.py)                     │
├─────────────────┬──────────────────┬────────────────────────────────┤
│  Live Monitor   │  Session Mgmt    │    Analysis & Training         │
│                 │                  │                                │
│  • Real-time    │  • Start/Stop    │  • View session plots          │
│    BPM graph    │  • Logging       │  • Train ML models             │
│  • Mode control │  • Export data   │  • Generate augmented data     │
└─────────────────┴──────────────────┴────────────────────────────────┘
```

### Communication Flow

1. **FSR Sensors** → Resistance changes with pressure → Voltage divider circuit → ESP32 reads voltage
2. **ESP32 Sender** → Detects steps, measures intervals → **ESP-NOW** (wireless, <10ms latency)
3. **ESP32 Receiver** → Calculates instant BPM → **Serial USB**
4. **Python Backend** → Processes BPM, runs mode logic, adjusts MIDI tempo
5. **GUI Application** → Real-time visualization and session management

---

## ✨ Key Features

### 🎵 **Real-Time Music Synchronization**
- Instant tempo adjustment to match walking cadence
- Multiple operational modes (Dynamic, Hybrid, Random, Manual)
- Smooth tempo transitions using exponential smoothing
- Sprint boost for rapid acceleration detection

### 🤖 **Machine Learning Prediction**
- **LightGBM** regression model for next-step BPM prediction
- Trained on 180+ real walking sessions
- Reduces jitter and anticipates tempo changes
- Optuna hyperparameter optimization for best performance
- User-specific calibration ("User Head") for personalized prediction per user

### 🎮 **Control Interface**
- Professional dark/light theme GUI
- Real-time BPM monitoring with live plot
- Manual tempo override with slider
- Session management (start, stop, calibrate)
- Mode configuration (Random, Hybrid, Dynamic, Manual)

### 📊 **Research Data Collection**
- High-resolution CSV logging (timestamp, BPM, step intervals)
- Automatic post-session visualization (PDF + PNG)
- Session metadata (run type, smoothing, stride)
- Batch analysis and training on multiple sessions

### 🔧 **Hardware Flexibility**
- Per-sensor calibration for FSR variability
- Adjustable pressure thresholds and hysteresis
- Serial port auto-detection
- Low-latency ESP-NOW wireless protocol

### 🧪 **Data Augmentation**
- Time warping (simulate speed variations)
- Gaussian noise (sensor variability)
- Parameter augmentation (generate new stride/window combinations)
- Expands training dataset for better model generalization

---

## 🔌 Hardware Components

### Required Components

| Component | Quantity | Purpose |
|-----------|----------|---------|
| **ESP32 DevKit** | 2 | Sender (foot) + Receiver (stationary) |
| **FSR 406** (Force Sensitive Resistor) | 2 | Left and right foot pressure detection |
| **2kΩ Resistors** | 2 | Voltage divider for FSR reading |
| **Jumper Wires** | ~10 | Connections |
| **Micro USB Cables** | 2 | Power and serial communication |
| **Power Bank** | 1 | Portable power for sender ESP32 |
| **Computer** | 1 | Python backend and GUI |

### Circuit Diagram

![Circuit Diagram](Documentation/connection%20diagram/circuit_image.png)

See `Documentation/connection diagram/circuit_image.png` for full wiring diagram.

### ESP-NOW Pairing

1. Upload `ESP32/Get_MAC_Address/Get_MAC_Address.ino` to both ESP32s
2. Note the MAC addresses
3. Update `step_detection_sketch.ino` line 7: `receiverMac[] = {0xfc, 0xb4, ...}`
4. Update `step_receiver_sketch.ino` line 16: `senderMac[] = {0xfc, 0xb4, ...}`

---

## Software Modes

The system supports **4 operational modes** + prediction configuration for different research scenarios:

### 1️⃣ **Dynamic Mode** (Default)
**Real-time walking synchronization**

- Music tempo **continuously follows** walking cadence
- Smooth acceleration and deceleration
- Sprint boost: Faster tempo increase when BPM spike detected
- Safety decay: Music slows if no steps detected

**Use Case:** Natural walking with responsive music feedback

---

### 2️⃣ **Hybrid Mode**
**Smart cruise control**

- Starts in **Dynamic Mode** (following walker)
- **Locks** to music BPM after detecting **stable pace** (5 consecutive steps within ±5 BPM)
- **Unlocks** immediately if walker deviates >10 BPM from locked tempo
- Returns to Dynamic Mode after unlock

**Configurable Parameters:**
- Lock Steps: 2-20 (default: 5)
- Stability Threshold: 1-10 BPM (default: 5)
- Unlock Threshold: 5-50 BPM (default: 10)

**Use Case:** Encourage steady-state walking while allowing freedom to change pace

---

### 3️⃣ **Random Mode**
**Gamified tempo challenges**

Two sub-modes:

#### **Simple Mode (Step-Based):**
- System picks random target BPM (±20% of song BPM)
- Walker must match within ±5 BPM for 5 consecutive steps
- Success → New random target assigned

#### **Gamified Mode (Time-Based):**
- 10-second timer per target
- Success = Match tempo before timeout
- Failure = Pick new target + reset timer

**Configurable Parameters:**
- Difficulty: ±10% to ±50% (default: ±20%)
- Match Steps: 2-50 (default: 5)
- Match Threshold: 1-10 BPM (default: 5)
- Timeout: 5-60 seconds (default: 15)

**Use Case:** Gait variability training, engagement, adherence

---

### 4️⃣ **Manual Mode**
**Therapist override**

- Music tempo set by therapist via GUI slider (40-240 BPM)
- Steps still recorded, but do NOT affect tempo
- Useful for controlled experiments or when walker cannot generate steps

**Use Case:** Baseline measurements, fixed-tempo trials

---

### ⚙️ **Prediction Configuration**
**ML-assisted smoothing with user personalization**

- LightGBM model predicts next-step BPM based on:
  - Last 4 walking BPM values (lag features)
  - Last 4 instant BPM values (raw step intervals)
  - Smoothing window, stride, run type metadata
- Reduces jitter and anticipates tempo changes
- Can be enabled/disabled per session
- **User Head**: Train a personalized model for specific users to improve prediction accuracy based on their walking patterns

**Use Case:** Smoother experience for users sensitive to tempo fluctuations

---

## 📦 Installation

### Prerequisites

**Required:**
- **Python 3.8+** installed and added to PATH

**macOS Additional Requirement:**
- **Homebrew** is required to install tkinter (GUI library)
```bash
# Install Homebrew first
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python with tkinter support
brew install python python-tk
```

---

### Option 1: 🚀 **Standalone Application (⚠️ Under Development)**

> **⚠️ WARNING**: Compiled/standalone mode is currently **under development** and **not ready for use**. Please use **Option 2 (Run from Source)** below.

Build scripts are available but the compiled application is not yet fully functional:

#### Windows:
```batch
cd setup\Windows
build_app.bat
```

#### Linux/macOS:
```bash
cd setup/Linux_Mac
chmod +x build_app.sh
./build_app.sh
```

**Status:** Work in progress. Use run from source instead.

---

### Option 2: 🐍 **Run from Source (✅ Recommended)**

**This is the primary and recommended way to run the application.**

#### Windows:
```batch
cd setup\Windows\dev
setup_env.bat      # First time: Create venv + install dependencies
start_app.bat      # Run the GUI application
```

#### Linux/macOS:
```bash
cd setup/Linux_Mac/dev
chmod +x setup_env.sh start_app.sh
./setup_env.sh     # First time: Create venv + install dependencies
./start_app.sh     # Run the GUI application
```

---

### Dependencies

**Python Libraries** (auto-installed by setup scripts):
```
pandas, matplotlib, pyserial, numpy, mido, python-rtmidi
scikit-learn, lightgbm, optuna, plotly, kaleido, joblib, Pillow
```

**Arduino Libraries** (for ESP32 firmware):
```
WiFi, esp_wifi, esp_now
```

---

## 🚀 Quick Start

### 1. **Flash ESP32 Firmware**

#### Sender ESP32 (On Foot):
1. Open `ESP32/step_detection_sketch/step_detection_sketch.ino` in Arduino IDE
2. Update `receiverMac[]` with receiver's MAC address (line 7)
3. Upload to ESP32 #1

#### Receiver ESP32 (Stationary):
1. Open `ESP32/step_receiver_sketch/step_receiver_sketch.ino` in Arduino IDE
2. Update `senderMac[]` with sender's MAC address (line 16)
3. Upload to ESP32 #2

### 2. **Connect Hardware**

1. Assemble FSR circuits (see [Circuit Diagram](#circuit-diagram))
2. Connect sender ESP32 to FSRs and power bank
3. Connect receiver ESP32 to computer via micro USB
4. Note the COM port (e.g., COM3 on Windows, /dev/ttyUSB0 on Linux)

### 3. **Launch GUI**

**Standalone:**
```bash
./dist/BrainMusicSync/BrainMusicSync.exe   # Windows
./dist/BrainMusicSync/BrainMusicSync       # Linux/Mac
```

**From Source:**
```bash
cd setup/Windows/dev && start_app.bat      # Windows
cd setup/Linux_Mac/dev && ./start_app.sh   # Linux/Mac
```

### 4. **Start a Session**

1. **Select MIDI File**: Click "Browse" in GUI (default: `Technion_March1.mid`)
2. **Select COM Port**: Choose receiver ESP32 port from dropdown
3. **Choose Mode**: Dynamic (default), Hybrid, Random, or Manual
4. **Configure Settings**:
   - Session Name: Custom folder name (default: timestamp)
   - Smoothing Window: 1-10 steps (default: 3)
   - Update Stride: 1-5 steps (default: 1)
5. **Calibrate Weight** (Optional): Click "Calibrate Weight" and stand on sensors for 3 seconds
6. **Click "START SESSION"**: Music begins, live BPM plot appears
7. **Walk**: Music adjusts to your pace in real-time
8. **Click "STOP SESSION"**: Data saved to `server/logs/[SessionName]/`

---

## 📖 Usage Guide

### GUI Overview

The application has **4 main tabs**:

#### 1. **Live Monitor Tab**
- **Real-time BPM plot**: Shows walking BPM (blue) and music tempo (orange) over time
- **Current BPM display**: Large numeric indicator
- **Session controls**: Start, Stop, Calibrate
- **Mode selector**: Choose operational mode
- **Manual slider**: Adjust tempo in Manual Mode

#### 2. **Mode Settings Tab**

**Random Mode Settings:**
- **Difficulty Span**: ±10% to ±50%
- **Gamified Mode**: Enable/disable time-based challenges
- **Match Steps**: 2-50 steps
- **Match Threshold**: 1-10 BPM
- **Timeout**: 5-60 seconds

**Hybrid Mode Settings:**
- **Lock Steps**: 2-20 consecutive stable steps
- **Stability Threshold**: 1-10 BPM variation to consider "stable"
- **Unlock Threshold**: 5-50 BPM deviation to trigger unlock

**Advanced Settings:**
- **Climbing (Speed Up)**: 0.01-1.0 (default: 0.10) - how fast music accelerates
- **Cascading (Slow Down)**: 0.01-1.0 (default: 0.05) - how fast music decelerates
- **Smoothing Window**: 1-10 steps (default: 3) - BPM averaging window
- **Update Stride**: 1-5 steps (default: 1) - update frequency
- **Prediction Model**: Select base model or user-specific calibration (User Head)
- **Calibration Margin**: Pressure threshold margin (default: 200)

#### 3. **Analysis Tab**
- **Session Browser**: View all recorded sessions by folder
- **Session Details**: Metadata (duration, steps, avg BPM, run type)
- **Post-Session Plot**: Zoomable, pannable BPM graph with step markers
- **Export**: Generate PDF report
- **Delete**: Remove sessions or entire folders

#### 4. **Model Learning Tab**
- **Training**: Select sessions and train LightGBM model (Fast, Deep, or Optuna presets)
- **Augmentation**: Generate synthetic training data (time warping, noise, parameter variation)
- **Results**: View learning curves, feature importance, parameter optimization
- **User Head Training**: Train personalized model for specific user

---

### Command-Line Interface

The backend engine can also run standalone:

```bash
python server/main.py [midi_file] [options]

Options:
  --serial-port COM3           Serial port for ESP32
  --manual                     Start in manual mode
  --bpm 120                    Set fixed BPM (manual mode)
  --smoothing 3                Smoothing window (steps)
  --stride 1                   Update stride (steps)
  --session-name "Test01"      Custom session name
  --alpha-up 0.1               Acceleration smoothing
  --alpha-down 0.05            Deceleration smoothing
  --disable-prediction         Disable ML model
  --model-path path/to/model   Custom model file
  --hybrid                     Enable hybrid mode
```

**Example:**
```bash
python server/main.py midi_files/Technion_March1.mid --serial-port COM5 --hybrid --smoothing 5
```

---

### Session Data Files

Each session creates a folder: `server/logs/[SessionName]/`

**Contents:**
- `session_data.csv`: Timestamped BPM data
  ```csv
  elapsed_time,instant_bpm,walking_bpm,current_bpm_music,interval,smoothing_window,stride,run_type
  0.234,125.3,124.1,122.5,0.479,3,1,dynamic
  ```
- `session_log.txt`: Event log (mode changes, calibrations, errors)
- `BPM_plot.png`: Post-session visualization
- `BPM_plot.pdf`: High-resolution PDF export

**Metadata Header (first 4 lines of CSV):**
```csv
# run_type: dynamic
# stride: 1
# smoothing_window: 3
# session_name: 2026-01-23_14-32-18
```

---

## 🧠 Machine Learning Pipeline

### Training Workflow

1. **Collect Data**: Run walking sessions, log to CSV
2. **Data Filtering**:
   - Remove sessions with <20 steps
   - Remove invalid BPM values (outliers, zeros)
3. **Feature Engineering**:
   - Create lag features: last 4 walking BPM values
   - Create lag features: last 4 instant BPM values
   - Add metadata: smoothing_window, stride, run_type (encoded)
4. **Data Augmentation** (optional):
   - Time warping: Stretch/compress time series (±10%)
   - Gaussian noise: Add sensor variability (σ=2)
   - Parameter augmentation: Generate new stride/window combinations
5. **Model Training**:
   - Split: 80% train, 20% test
   - Presets: Fast (200 trees), Deep (300 trees), Optuna (tuned)
   - Evaluation: RMSE, MAE, R² on held-out test set
6. **Model Selection**: Best model (by R²) automatically saved
7. **Deployment**: Model loaded by `LGBM_predictor.py` for real-time prediction

### Training via GUI

1. Navigate to **Model Learning** tab
2. Select training sessions (or folders)
3. Choose preset:
   - **Fast**: Quick training (~1 min)
   - **Deep**: More iterations (~3 min)
   - **Optuna**: Hyperparameter optimization (~10-30 min, 100 trials)
4. Click **"Start Training"**
5. View results: Learning curves, feature importance, predictions
6. Trained model saved to `server/utils/prediction_model/results/models/lgbm_model.joblib`

### Data Augmentation

**Generate Synthetic Sessions:**

**Via GUI:**
1. Navigate to **Model Learning** tab → **Data Augmentation** section
2. Select source sessions or folders
3. Click **"Generate Augmented Data"**
4. Progress bar shows augmentation status
5. Output: `server/logs/Augmented/` folder with synthetic sessions

**Via Command Line:**
```bash
python server/utils/prediction_model/generate_augmented_data.py --input server/logs/Default --output server/logs/Augmented
```

---

## 📂 Project Structure

```
IOT_REPO_BRAIN_MUSIC_RESEARCH/
│
├── README.md                          # This file
├── requirements.txt                    # Python dependencies
│
├── ESP32/                              # Embedded firmware
│   ├── step_detection_sketch/          # Sender (foot sensor)
│   │   └── step_detection_sketch.ino
│   ├── step_receiver_sketch/           # Receiver (stationary)
│   │   └── step_receiver_sketch.ino
│   ├── Get_MAC_Address/                # Utility to find ESP32 MAC
│   └── parameters.h                    # Hardware pin definitions
│
├── server/                             # Python backend
│   ├── main.py                         # CLI engine entry point
│   ├── gui_app.py                      # GUI application
│   │
│   ├── utils/
│   │   ├── engine/
│   │   │   ├── BPM_estimation.py       # Core BPM logic & mode orchestration
│   │   │   └── process_manager.py      # Subprocess management
│   │   │
│   │   ├── hardware/
│   │   │   ├── comms.py                # ESP32 serial communication
│   │   │   └── midi_player.py          # MIDI playback & tempo control
│   │   │
│   │   ├── session/
│   │   │   ├── logger.py               # CSV logging
│   │   │   └── plotter.py              # Live & post-session plots
│   │   │
│   │   ├── Modes/                      # Operational mode implementations
│   │   │   ├── base_mode.py            # Abstract base class
│   │   │   ├── dynamic_mode.py         # Follow walking pace
│   │   │   ├── hybrid_mode.py          # Cruise control
│   │   │   ├── random_mode.py          # Gamified challenges
│   │   │   └── manual_mode.py          # Therapist override
│   │   │
│   │   ├── prediction_model/           # Machine Learning
│   │   │   ├── train_lgbm.py           # Model training script
│   │   │   ├── train_user_head.py      # User-specific calibration
│   │   │   ├── analyze_data.py         # Data preprocessing
│   │   │   ├── data_filtering.py       # Session validation
│   │   │   ├── data_augmentation.py    # Synthetic data generation
│   │   │   ├── generate_augmented_data.py  # CLI augmentation
│   │   │   ├── LGBM_predictor.py       # Real-time prediction
│   │   │   ├── run_lgbm.bat            # Windows training script
│   │   │   └── results/
│   │   │       ├── models/             # Trained .joblib models
│   │   │       └── plots/              # Learning curves, feature importance
│   │   │
│   │   ├── paths.py                    # Path resolution utilities
│   │   └── safety.py                   # Error handling
│   │
│   └── logs/                           # Session recordings
│       ├── Default/                    # Default training dataset (180 sessions)
│       ├── Augmented/                  # Synthetic training data
│       └── [Custom]/                   # User-defined session folders
│
├── midi_files/                         # Music library
│   ├── Technion_March1.mid
│   └── Technion March no 2 MIDI.mid
│
├── setup/                              # Build & deployment
│   ├── build.spec                      # PyInstaller config
│   ├── README.md                       # Detailed setup guide
│   ├── Windows/
│   │   ├── build_app.bat               # Build standalone .exe
│   │   └── dev/
│   │       ├── setup_env.bat           # Create Python venv
│   │       └── start_app.bat           # Run from source
│   └── Linux_Mac/
│       ├── build_app.sh                # Build standalone app
│       └── dev/
│           ├── setup_env.sh            # Create Python venv
│           └── start_app.sh            # Run from source
│
├── Documentation/                      # Hardware specs
│   ├── 2010-10-26-DataSheet-FSR406-Layout2.pdf
│   ├── connection diagram/
│   │   └── circuit_image.png
│   └── optimal_resistor.xlsx
│
└── Unit Tests/                         # Hardware validation
    ├── fsr_comparison_test/            # FSR calibration test
    ├── fsr_testing/                    # FSR basic test
    ├── sender_sketch/                  # ESP-NOW sender test
    └── receiver_sketch/                # ESP-NOW receiver test
```

---

## 🙏 Acknowledgments

- **Professor Eitan Globerson**: Project supervision and domain expertise
- **ICST Technion**: Facilities and resources
- **IoT Course Staff**: Technical guidance

---

**IoT Project 236333, ICST - The Interdisciplinary Center for Smart Technologies, Technion**  
https://icst.cs.technion.ac.il/
