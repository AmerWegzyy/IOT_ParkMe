from csv import writer
from pathlib import Path
import datetime
import time
import sys
import json
from ..paths import get_logs_dir

def _format_elapsed(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

class Logger:
    # NOTE: This logger is used both for the console and for the GUI.
    #       It is initialized with a GUI callback if available.
    def __init__(
        self,
        gui_callback=None,
        session_name=None,
        smoothing_window: int | None = None,
        stride: int | None = None,
        run_type: str | None = None,
    ):
        # Don't start timer yet - wait for first data point (when music actually starts)
        self.start_time = None
        self._timer_started = False
        self.timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.gui_callback = gui_callback
        if session_name and session_name.strip():
            # Sanitize name
            safe_name = "".join([c for c in session_name if c.isalnum() or c in (' ', '_', '-')]).strip()
            # logs/NAME/session_TIMESTAMP (Patient History)
            self.parent_dir = get_logs_dir() / safe_name
            self.path = self.parent_dir / f"session_{self.timestamp}"
        else:
            # logs/Default/session_TIMESTAMP
            self.parent_dir = get_logs_dir() / "Default"
            self.path = self.parent_dir / f"session_{self.timestamp}"

        #setting the path to the logs directory
        self.path.mkdir(parents=True, exist_ok=True)
        
        self.file_path = self.path / "session_log.txt"
        self.csv_path = self.path / "session_data.csv"
        #creating the log file
        with self.file_path.open("w", encoding="utf-8") as handle:
            handle.write(f"Session log started at {self.timestamp} (t=0.000)\n")
        #creating the csv file (with meta header)
        meta = {
            "smoothing_window": int(smoothing_window) if smoothing_window is not None else 3,
            "stride": int(stride) if stride is not None else 1,
            "run_type": run_type if run_type is not None else "dynamic",
        }
        with self.csv_path.open("w", newline="", encoding="utf-8") as handle:
            handle.write(f"# meta: {json.dumps(meta)}\n")
            csv_writer = writer(handle)
            csv_writer.writerow(["time", "song_bpm", "walking_bpm", "step_event", "instant_bpm"])

    def _elapsed_str(self, timestamp: float | None = None) -> str:
        if timestamp is None:
            timestamp = time.time()
        
        # Start timer on first call (when session actually begins)
        if not self._timer_started:
            return _format_elapsed(0.0)
        
        elapsed = max(0.0, timestamp - self.start_time)
        return _format_elapsed(elapsed)

    def log(self, message: str):
        # Use current time for log messages
        elapsed_str = self._elapsed_str()
        stamped = f"[{elapsed_str}] {message}"
        with self.file_path.open("a", encoding="utf-8") as handle:
            handle.write(stamped + "\n")
        print(stamped)
        sys.stdout.flush()
        
        # Update GUI if callback is provided
        if self.gui_callback:
            self.gui_callback(message)
            
    def log_data(
        self, timestamp: float, song_bpm: float, walking_bpm: float, step_event: bool = False, instant_bpm: float | None = None):
        # Start timer on first data log (calibration or music start)
        if not self._timer_started:
            self.start_time = timestamp
            self._timer_started = True
            if song_bpm > 0:
                self.log("Session timer started - music is now playing")
            else:
                self.log("Session timer started - calibration phase")
        
        elapsed = self._elapsed_str(timestamp)
        ib = instant_bpm if step_event else ""
        with self.csv_path.open("a", newline="", encoding="utf-8") as handle:
            csv_writer = writer(handle)
            csv_writer.writerow([elapsed, song_bpm, walking_bpm, step_event, ib])
            
        # DUAL STREAMING: Broadcast to GUI via RAM (Stdout)
        # Format: DATA_PACKET:{"t": ..., "s": ..., "w": ..., "e": ...}
        import json
        packet = {
            "t": elapsed, # time string
            "s": song_bpm,
            "w": walking_bpm,
            "e": step_event,
        }
        if step_event and instant_bpm is not None:
            packet["i"] = instant_bpm
        print(f"DATA_PACKET:{json.dumps(packet)}")
        sys.stdout.flush()