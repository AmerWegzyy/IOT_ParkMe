import subprocess
import sys
import threading
import json
from pathlib import Path
import os

class SubprocessManager:
    """
    Manages the 'main.py' engine process.
    - Launches it as a subprocess.
    - Writes commands to its STDIN.
    - Reads logs from its STDOUT.
    """
    def __init__(self, midi_path, serial_port, manual_mode, manual_bpm, smoothing_window, stride, log_callback, session_dir_callback, data_callback=None, gui_sync_callback=None, session_name=None, alpha_up=None, alpha_down=None, hybrid_mode=False, random_mode=False, random_span=None, 
                 hybrid_lock_steps=None, hybrid_unlock_time=None, hybrid_stability_threshold=None, hybrid_unlock_threshold=None, random_gamified=None,
                 random_simple_threshold=None, random_simple_steps=None, random_simple_timeout=None, model_path=None, startup_mode=None, walk_steps=None):
        self.log_callback = log_callback
        self.session_dir_callback = session_dir_callback
        self.data_callback = data_callback
        self.gui_sync_callback = gui_sync_callback
        self.process = None
        self.running = False
        
        # Build Command Arguments
        # Use absolute path to ensure main.py is found regardless of CWD
        
        # Revert to sys.executable as it maps to the active VENV
        cmd = [sys.executable, "main.py", midi_path]
        if manual_mode:
            cmd.append("--manual")
            if manual_bpm:
                cmd.extend(["--bpm", str(manual_bpm)])
        
        if serial_port:
             cmd.extend(["--serial-port", str(serial_port)]) 
        
        # We pass initial config via flags only if provided (engine has defaults)
        if smoothing_window is not None:
            cmd.extend(["--smoothing", str(smoothing_window)])
        if stride is not None:
            cmd.extend(["--stride", str(stride)])
        
        if alpha_up is not None:
            cmd.extend(["--alpha-up", str(alpha_up)])
        if alpha_down is not None:
            cmd.extend(["--alpha-down", str(alpha_down)])
        
        if session_name:
             cmd.extend(["--session-name", str(session_name)])
        
        if hybrid_mode:
            cmd.append("--hybrid")
            if hybrid_lock_steps is not None:
                cmd.extend(["--hybrid-lock-steps", str(hybrid_lock_steps)])
            if hybrid_unlock_time is not None:
                cmd.extend(["--hybrid-unlock-time", str(hybrid_unlock_time)])
            if hybrid_stability_threshold is not None:
                cmd.extend(["--hybrid-stability-threshold", str(hybrid_stability_threshold)])
            if hybrid_unlock_threshold is not None:
                cmd.extend(["--hybrid-unlock-threshold", str(hybrid_unlock_threshold)])

        if random_mode:
            cmd.append("--random")
            if random_span:
                cmd.extend(["--random-span", str(random_span)])
            if random_gamified is not None:
                val = 1 if random_gamified else 0
                cmd.extend(["--random-gamified", str(val)])
            if random_simple_threshold is not None:
                cmd.extend(["--random-simple-threshold", str(random_simple_threshold)])
            if random_simple_steps is not None:
                cmd.extend(["--random-simple-steps", str(random_simple_steps)])
            if random_simple_timeout is not None:
                cmd.extend(["--random-simple-timeout", str(random_simple_timeout)])
        
        if model_path:
            cmd.extend(["--model-path", str(model_path)])
        
        # Startup mode parameters
        if startup_mode == "walk_first":
            cmd.append("--walk-first")
            if walk_steps is not None:
                cmd.extend(["--walk-steps", str(walk_steps)])
        
        # Launch Process
        try:
            env = os.environ.copy()
            # We use bufsize=1 for line buffering
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, # Capture separately
                text=True,
                bufsize=1,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), # Execute INSIDE server/ folder (parent of utils)
                env=env,
            )
            self.running = True
            
            # Start Background Reader Threads
            self.reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
            self.reader_thread.start()
            
            self.stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
            self.stderr_thread.start()
            
        except Exception as e:
            self._log(f"Failed to start engine: {e}")

        # Debug logging of command (disabled for clean production)
        # self._log(f"Executing: {' '.join(cmd)}")

    def _log(self, msg):
        # print(f"[GUI_DEBUG] {msg}") # Debug print disabled
        if self.log_callback: self.log_callback(msg)

    def _read_stderr(self):
        """Reads lines from the subprocess STDERR and logs them as errors."""
        while self.running and self.process:
            try:
                line = self.process.stderr.readline()
                if not line: break
                line = line.strip()
                if line:
                    self._log(f"[Stderr] {line}")
            except Exception:
                break

    def _read_stdout(self):
        """Reads lines from the subprocess STDOUT and logs them."""
        while self.running and self.process:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                
                # Check for special signals
                if line.startswith("SESSION_DIR:"):
                     path_str = line.split(":", 1)[1]
                     if self.session_dir_callback:
                         self.session_dir_callback(Path(path_str))
                     continue # Don't log this protocol line
                
                # Check for Data Packet (RAM Pipe)
                if line.startswith("DATA_PACKET:"):
                     if self.data_callback:
                         try:
                             json_str = line.split(":", 1)[1]
                             data = json.loads(json_str)
                             self.data_callback(data)
                         except: pass
                     continue
                
                # Check for GUI Sync Packet
                if line.startswith("GUI_SYNC:"):
                    if self.gui_sync_callback:
                        try:
                            # Format: GUI_SYNC:KEY:VALUE
                            parts = line.split(":", 2)
                            if len(parts) == 3:
                                self.gui_sync_callback(parts[1], parts[2])
                        except: pass
                # Check for Notification messages
                if line.startswith("NOTIFICATION:"):
                    # Pass through with NOTIFICATION: prefix for GUI to handle
                    self._log(line)
                    continue

                if line == "EXIT_CLEAN":
                    self.running = False
                    break

                self._log(f"[Engine] {line}")
            except Exception:
                break
            
    def send_command(self, cmd_str):
        """Writes a line to the subprocess STDIN."""
        if self.process and self.running:
            try:
                self.process.stdin.write(cmd_str + "\n")
                self.process.stdin.flush()
            except Exception as e:
                self._log(f"Send Error: {e}")

    def update_manual_bpm(self, bpm):
        self.send_command(f"SET_MANUAL_BPM:{bpm}")

    def set_manual_mode(self, enabled):
        self.send_command("SET_MODE:manual")

    def set_random_mode(self, enabled):
        self.send_command("SET_MODE:random")

    def set_hybrid_mode(self, enabled):
        self.send_command("SET_MODE:hybrid")

    def set_dynamic_mode(self, enabled):
        self.send_command("SET_MODE:dynamic")

    def update_smoothing_alpha_up(self, alpha):
        self.send_command(f"SET_ALPHA_UP:{alpha}")

    def update_smoothing_alpha_down(self, alpha):
        self.send_command(f"SET_ALPHA_DOWN:{alpha}")

    def update_esp_config(self, cmd_type, value):
        if cmd_type == "window":
            self.send_command(f"SET_WINDOW:{value}")
        elif cmd_type == "stride":
            self.send_command(f"SET_STRIDE:{value}")

    def update_random_span(self, span):
        self.send_command(f"SET_RANDOM_SPAN:{span}")

    def update_random_gamified(self, enabled: bool):
        val = 1 if enabled else 0
        self.send_command(f"SET_RANDOM_GAMIFIED:{val}")

    def update_random_simple_threshold(self, threshold: float):
        self.send_command(f"SET_RANDOM_SIMPLE_THRESHOLD:{threshold}")

    def update_random_simple_steps(self, steps: int):
        self.send_command(f"SET_RANDOM_SIMPLE_STEPS:{steps}")

    def update_random_simple_timeout(self, seconds: float):
        self.send_command(f"SET_RANDOM_SIMPLE_TIMEOUT:{seconds}")

    def update_hybrid_lock_steps(self, steps: int):
        self.send_command(f"SET_HYBRID_LOCK_STEPS:{steps}")

    def update_hybrid_unlock_time(self, seconds: float):
        self.send_command(f"SET_HYBRID_UNLOCK_TIME:{seconds}")

    def update_hybrid_stability_threshold(self, bpm: float):
        self.send_command(f"SET_HYBRID_STABILITY_THRESHOLD:{bpm}")

    def update_hybrid_unlock_threshold(self, bpm: float):
        self.send_command(f"SET_HYBRID_UNLOCK_THRESHOLD:{bpm}")

    def stop(self):
        self.running = False
        if self.process:
            self.send_command("QUIT")
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
