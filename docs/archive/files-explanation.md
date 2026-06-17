# Project Files Explanation

This document provides a comprehensive breakdown of **every single file** in the project repository (as well as a special section at the top detailing the files modified during the Google Cloud / Firebase migration).

---

## Part 1: Migration Files (Google Cloud & Firebase)
These files were either modified or newly created to transition the system to **Google Cloud Platform (GCP)**, **Firebase Hosting**, and the **Google Cloud Vision API**.

1. **`Backend/main.py`**
   - *Purpose:* The core FastAPI backend application.
   - *Migration Update:* Replaced the bulky Tesseract OCR with `google.cloud.vision.ImageAnnotatorClient()` to directly query Google Cloud for license plate text extraction. 

2. **`Backend/requirements.txt`**
   - *Purpose:* Lists the Python dependencies required to run the backend.
   - *Migration Update:* Added `google-cloud-vision` and removed heavy dependencies like `pytesseract`, `opencv-python-headless`, and `numpy`.

3. **`Backend/Dockerfile`**
   - *Purpose:* Instructions for building the Docker container for Google Cloud Run.
   - *Migration Update:* Removed system-level packages for Tesseract (`tesseract-ocr`, `libtesseract-dev`) making the container dramatically smaller and faster to deploy.

4. **`firebase.json`**
   - *Purpose:* The core configuration file for Firebase Hosting.
   - *Migration Update:* Configured to deploy the `Frontend` folder to the web and rewrite all navigation traffic to `index.html` (standard for Single Page Apps).

5. **`.firebaserc`**
   - *Purpose:* Maps the local repository to the Firebase project in the cloud.
   - *Migration Update:* Links the "default" environment to the `parkme-technion` project ID.

6. **`Frontend/app.js`**
   - *Purpose:* The JavaScript logic for the web dashboard.
   - *Migration Update:* Updated the `API_BASE` routing to dynamically switch between `http://localhost:8000` (for local development) and your production Google Cloud Run URL.

---

## Part 2: Complete Project File Directory
Below is an explanation of every other file in the project, categorized by folder.

### Root Directory
- **`.DS_Store`**: A macOS system file that stores custom attributes of its containing folder.
- **`.gitignore`**: Specifies intentionally untracked files that Git should ignore (e.g., node_modules, Python virtual environments, secret keys).
- **`README.md`**: The main project landing page containing project details, folder descriptions, and basic hardware setup instructions.
- **`mcp.json`**: Configuration for the Model Context Protocol (used internally by AI assistants).
- **`parkme_architecture.html`**: An interactive, standalone HTML file visualizing the architecture, Entity-Relationship Diagram (ERD), and hardware communication flows of the ParkMe project.

### Backend/
*This directory contains the FastAPI server, database logic, and deployment configurations.*
- **`Backend/.env.example`**: A template defining the environment variables required to run the backend locally (e.g., secret keys, JWT secrets).
- **`Backend/cloudbuild.yaml`**: CI/CD pipeline configuration for Google Cloud Build. It dictates how the backend is automatically tested, built, and deployed to Cloud Run.
- **`Backend/seed_firestore.py`**: A Python script used to populate the new Firebase Firestore database with mock users, vehicles, and spots to aid in testing.

### Documentation/
*High-level documentation and guides written for human developers.*
- **`Documentation/setup_guide.md`**: Step-by-step instructions for setting up the Google Cloud and Firebase environment and running the backend locally.
- **`Documentation/system_architecture_and_workflow.md`**: A detailed breakdown of how the ESP32 sensors, Backend API, Firestore Database, and Web App communicate with each other.
- **`Documentation/firestore_database_structure.md`**: Explains the collections, documents, and relationships inside the new NoSQL Firestore database.
- **`Documentation/why_we_migrated.md`**: Explains the rationale, benefits, and technical differences involved in migrating from Render/PostgreSQL to Google Cloud/Firebase.
- **`Documentation/connection diagram/Fritzing file in FZZ format.txt`**: A placeholder noting where the Fritzing hardware connection diagram is (or should be) stored.
- **`Documentation/connection diagram/files here.txt` & `Documentation/files here.txt`**: Empty placeholder files used to keep the directory structure alive in Git.

### docs/
*This directory holds an archive of conversation logs, architectural decisions, and project planning documents accumulated throughout the project's lifecycle.*
- **`docs/api_documentation.md`**: Documentation of the REST API endpoints and data structures.
- **`docs/architect_prompt.md`**: A prompt file detailing the project architecture requirements and constraints.
- **`docs/current_hardware_behavior.md`**: Documentation defining exactly how the ESP32 hardware currently behaves.
- **`docs/edge_cases.md`**: Explores potential system anomalies (e.g., ghost cars, bouncing drivers) and how the system resolves them.
- **`docs/esp32_hardware_spec.md`**: Hardware specifications and pinouts for the ESP32 components.
- **`docs/files-explanation.md`**: This current file.
- **`docs/instructions_for_connecting_wires.md`**: Textual instructions for hardware wiring.
- **`docs/parkme_architecture.html`**: A duplicate/backup of the interactive architecture visualization diagram.
- **`docs/phase1_answers.md` to `docs/phase8_architecture.md`**: A series of documents recording the iterative phases of the project's design. They contain questions answered and architectural decisions made over the course of development.
- **`docs/project_definition.md`**: The core definition, goals, and requirements of the project.
- **`docs/project_summary.md`**: A brief summary of what the ParkMe system does.
- **`docs/sync-issues.md`**: Engineering notes on handling state synchronization between the physical hardware and the backend.

### ESP32/
*This directory contains all the C++/Arduino firmware for the physical edge devices.*
- **`ESP32/README.md`**: Basic instructions for navigating the firmware directory.
- **`ESP32/how_to_export_compiled_program.txt`**: Instructions on how to compile the Arduino code into a binary file.
- **`ESP32/compiled_program.bin`**: A pre-compiled binary firmware file ready to be directly flashed to an ESP32.
- **`ESP32/parameters.h`**: Global parameter configurations for the ESP32 nodes (e.g., timeout durations, thresholds).
- **`ESP32/SECRETS.example.h`**: A template for Wi-Fi credentials (safe to share).
- **`ESP32/SECRETS.h`**: The actual file containing sensitive Wi-Fi keys (ignored by git).
- **`ESP32/ParkMeCameraNode/ParkMeCameraNode.ino`**: The main Arduino sketch for the ESP32-CAM nodes, responsible for taking pictures of license plates and transmitting them via HTTP POST.
- **`ESP32/ParkMeSensorNode/ParkMeSensorNode.ino`**: The main Arduino sketch for standard ESP32 nodes handling proximity sensors and periodic heartbeats.
- **`ESP32/ParkMeFirmwareCompileTests/ParkMeFirmwareCompileTests.ino`**: A test sketch used to verify that the firmware libraries compile correctly without executing full business logic.
- **`ESP32/ParkMeCommon/ParkMeCommon.h`**: Shared macros, constants, types, and logic used across all ESP32 sketches.
- **`ESP32/ParkMeLcd/ParkMeLcd.h`**: Code specifically handling text formatting and updates for an attached LCD display.
- **`ESP32/libraries/...`**: Custom internal libraries (`ParkMeCommon`, `ParkMeConfig`, `ParkMeLcd`) modularized as proper Arduino libraries. They contain `library.properties` and source `.h` files so the Arduino IDE can import them properly.
- **`ESP32/INO files here.txt`**: A placeholder file.

### Frontend/
*The web-based dashboard for users and administrators.*
- **`Frontend/index.html`**: The main HTML entry point for the Single-Page Application (SPA) dashboard.
- **`Frontend/style.css`**: The CSS stylesheet defining the UI design, colors, and layouts.

### flutter_app/ & Unit Tests/
- **`flutter_app/files here.txt`**: A placeholder noting the location for the Dart/Flutter mobile application source code.
- **`Unit Tests/README.md`**: Documentation explaining how unit testing is structured for the hardware and software components.

### Internal Agent/Tooling Directories (`.agents/` & `skill-creator/`)
*These files are not part of the ParkMe software itself. They are internal scripts and instructions used by the AI coding assistant (Antigravity) to process the repository.*
- **`.agents/skills/visualize/SKILL.md`**: Instructions teaching the AI how to generate the interactive architecture visualization map for this specific project.
- **`skill-creator/LICENSE.txt`**: Licensing information for the skill creator tool.
- **`skill-creator/SKILL_skillcreator.md`**: Internal AI instructions for creating new automated skills.
- **`skill-creator/agents/analyzer.md`, `comparator.md`, `grader.md`**: Prompts and logic guiding internal subagents that evaluate and grade generated code.
- **`skill-creator/assets/eval_review.html` & `skill-creator/eval-viewer/*`**: HTML and Python scripts serving as a UI viewer for the AI to review its own evaluation results.
- **`skill-creator/references/schemas.md`**: Data schemas defining how the skill creator tool structures its output.
- **`skill-creator/scripts/*.py`**: Various Python utility scripts (`aggregate_benchmark.py`, `run_eval.py`, `package_skill.py`, `generate_report.py`, etc.) used internally by the AI to test, benchmark, and package new skills.
