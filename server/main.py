"""
Brain-Music Sync - Main Engine

This module orchestrates the real-time BPM synchronization loop:
1. Connects to ESP32 sensor via serial
2. Reads step data and calculates walking tempo
3. Adjusts MIDI playback speed to match user's pace
4. Logs session data for analysis

Usage:
    python main.py [midi_path] [--manual] [--bpm N] [--serial-port COMX]
"""
import sys
import time
import serial
import argparse
import threading
from pathlib import Path
from utils.hardware.midi_player import MidiBeatSync
from utils.session.logger import Logger
from utils.engine.BPM_estimation import BPM_estimation
from utils.hardware.comms import session_handshake, handle_engine_command, handle_step, send_calibration_command
from utils.prediction_model.LGBM_predictor import LGBMPredictor
# from utils.safety import safe_execute

#parse the arguments
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Brain-music demo player")
    # TWEAK: Change the default MIDI file here if you want a different song by default.
    parser.add_argument(
        "midi_path",
        nargs="?",
        default="midi_files\Technion_March1.mid",
        help="Path to the MIDI file to play",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Enable manual tempo mode (music tempo will not change based on steps)",
    )
    parser.add_argument(
        "--bpm",
        type=float,
        help="Set a fixed BPM for manual mode (optional, defaults to song BPM)",
    )
    parser.add_argument(
        "--smoothing",
        type=int,
        default=3,
        help="Set the smoothing window size (number of steps to average)",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=1,
        help="Set the BPM update stride (update BPM every N steps)",
    )
    parser.add_argument(
        "--session-name",
        type=str,
        default=None,
        help="Custom name for the session log directory",
    )
    parser.add_argument(
        "--serial-port",
        type=str,
        default="COM3",
        help="Serial port for the ESP32 (default: COM3)",
    )
    parser.add_argument(
        "--alpha-up",
        type=float,
        default=None,
        help="Optional attack smoothing alpha override",
    )
    parser.add_argument(
        "--alpha-down",
        type=float,
        default=None,
        help="Optional decay smoothing alpha override",
    )
    parser.add_argument(
        "--disable-prediction-model",
        "--disable-prediction",
        dest="disable_prediction",
        action="store_true",
        help="Disable prediction model for this run",
    )
    parser.add_argument(
        "--model-path",
        type=str,
        default=None,
        help="Path to prediction model (.joblib). If not specified, uses default base model.",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Enable hybrid mode (starts dynamic, locks if steady)",
    )
    parser.add_argument(
        "--random",
        action="store_true",
        help="Enable Random Drift Mode",
    )
    parser.add_argument(
        "--random-span",
        type=float,
        default=0.20,
        help="Difficulty span for Random Mode (0.0-0.5)",
    )
    parser.add_argument(
        "--random-gamified",
        type=int,
        default=0,
        help="Enable gamified (time-based) random mode (1=True, 0=False)",
    )
    parser.add_argument(
        "--random-simple-threshold",
        type=float,
        default=5.0,
        help="BPM spread to match in simple mode",
    )
    parser.add_argument(
        "--random-simple-steps",
        type=int,
        default=20,
        help="Consecutive steps to match in simple mode",
    )
    parser.add_argument(
        "--random-simple-timeout",
        type=float,
        default=30.0,
        help="Timeout (seconds) to fallback in simple mode",
    )
    parser.add_argument(
        "--hybrid-lock-steps",
        type=int,
        default=5,
        help="Steps needed to lock in hybrid mode",
    )
    parser.add_argument(
        "--hybrid-unlock-time",
        type=float,
        default=1.5,
        help="Seconds of deviation to unlock in hybrid mode",
    )
    parser.add_argument(
        "--hybrid-stability-threshold",
        type=float,
        default=3.0,
        help="BPM spread to consider stable in hybrid mode",
    )
    parser.add_argument(
        "--hybrid-unlock-threshold",
        type=float,
        default=15.0,
        help="BPM deviation to trigger unlock in hybrid mode",
    )
    parser.add_argument(
        "--calibrate-weight",
        type=int,
        default=None,
        help="Run weight calibration only (provide margin), then exit",
    )
    parser.add_argument(
        "--walk-first",
        action="store_true",
        help="Wait for user to walk N steps before starting music",
    )
    parser.add_argument(
        "--walk-steps",
        type=int,
        default=10,
        help="Number of steps to collect before starting music in walk-first mode (default: 10)",
    )
    return parser.parse_args()

def start_stdin_listener(command_queue):
    """
    Reads from stdin in a separate thread and puts lines into the command queue.
    Needed for SubprocessManager communication.
    """
    import threading
    import sys
    
    def _listen():
        for line in sys.stdin:
            command_queue.put(line.strip())
    
    t = threading.Thread(target=_listen, daemon=True)
    t.start()

def _notify(status_callback, message):
    """Send notification to GUI and log."""
    status_callback(message)
    print(f"NOTIFICATION:{message}")
    sys.stdout.flush()

def _collect_calibration_steps(ser, player, logger, status_callback, stop_event, num_steps):
    """Collect calibration steps and return list of BPMs."""
    logger.log(f"WALK-FIRST MODE: Collecting {num_steps} calibration steps...")
    _notify(status_callback, f"Please begin walking. Collecting {num_steps} steps...")
    
    bpms = []
    ser.timeout = 0.2
    
    while len(bpms) < num_steps:
        if stop_event and stop_event.is_set():
            logger.log("Session stopped during calibration.")
            return None
            
        if raw_line := ser.readline():
            try:
                bpm, instant_bpm, _, _ = handle_step(raw_line, player.walkingBPM)
                bpms.append(bpm)
                logger.log_data(time.time(), 0, bpm, step_event=True, instant_bpm=instant_bpm)
                logger.log(f"Calibration step {len(bpms)}/{num_steps}: {bpm:.1f} BPM")
                status_callback(f"Calibrating... {len(bpms)}/{num_steps} steps")
            except ValueError:
                continue
    
    return bpms

def handle_startup_mode(args, ser, player, logger, bpm_estimation, status_callback, stop_event):
    """Handle startup: walk-first (calibrate then play) or music-first (play immediately)."""
    
    if getattr(args, 'walk_first', False):
        # Calibrate from walking steps
        bpms = _collect_calibration_steps(ser, player, logger, status_callback, stop_event, 
                                          getattr(args, 'walk_steps', 10))
        if not bpms:
            return False
        
        # Start music at calibrated BPM
        avg_bpm = sum(bpms) / len(bpms)
        player.set_BPM(avg_bpm)
        player.start()
        logger.log(f"Calibration complete. Starting music at {avg_bpm:.1f} BPM")
        
        # Pre-fill prediction model and seed graph data
        for bpm in bpms:
            bpm_estimation.register_step(bpm, bpm)
        logger.log_data(time.time(), player.walkingBPM, avg_bpm, step_event=False)
        
        _notify(status_callback, "Music started! Continue walking.")
    else:
        # Start music immediately at default BPM
        player.start()
        logger.log("Running main loop...")
        
        # Seed initial GUI data so graph starts immediately
        logger.log_data(time.time(), player.walkingBPM, player.walkingBPM, step_event=False)
        
        _notify(status_callback, "System ready - Please begin walking!")
    
    ser.timeout = 0  # Non-blocking for main loop
    return True

def main(args, status_callback=print, stop_event=None, session_dir_callback=None, command_queue=None):
    midi_path = args.midi_path
    smoothing_window = getattr(args, 'smoothing', 3)
    stride = getattr(args, 'stride', 1)
    
    if args.manual:
        run_type = "manual"
    elif getattr(args, "hybrid", False):
        run_type = "hybrid"
    elif getattr(args, "random", False):
        run_type = "random"
    else:
        run_type = "dynamic"

    # Calibration-only flow: open serial, send CAL_WEIGHT, and exit.
    if getattr(args, "calibrate_weight", None) is not None:
        margin = int(args.calibrate_weight)
        class _Logger:
            def log(self_inner, msg): status_callback(msg)
        try:
            with serial.Serial(args.serial_port, 115200, timeout=1.0) as ser:
                ok = send_calibration_command(ser, _Logger(), margin=margin, retries=3)
                status_callback("Calibration completed." if ok else "Calibration failed.")
        except Exception as e:
            status_callback(f"Calibration error: {e}")
        return None, None, None

    # 1. Initialize Logger 
    logger = Logger(
        gui_callback=status_callback,
        session_name=getattr(args, 'session_name', None),
        smoothing_window=smoothing_window,
        stride=stride,
        run_type=run_type,
    )
    
    # OUTPUT SESSION DIR FOR GUI PARSING
    # The GUI listens for "SESSION_DIR:..." to know where to save the plot.
    print(f"SESSION_DIR:{logger.path}")
    sys.stdout.flush() # Ensure it sends immediately
    


    if session_dir_callback:
        session_dir_callback(logger.path)
        
    # 2. Initialize the midi player  
    logger.log("DEBUG: Attempting to initialize MidiBeatSync...")
    
    try:
        player = MidiBeatSync(midi_path)
        
        logger.log("DEBUG: MidiBeatSync initialized successfully.")
    except Exception as e:
        logger.log(f"CRITICAL ERROR: Failed to initialize MIDI Player: {e}")
        print(f"CRITICAL ERROR: {e}")
        sys.stdout.flush()
        return None, logger, None
    
    # 3. Log Mode
    if args.manual:
        logger.log("Starting in MANUAL MODE.")
        if args.bpm:
            logger.log(f"Setting fixed BPM to {args.bpm}")
            player.set_BPM(args.bpm)
        else:
            logger.log(f"Using default song BPM: {player.songBPM}")
    elif getattr(args, "random", False):
        logger.log("Starting in RANDOM DRIFT MODE.")
    else:
        logger.log("Starting in DYNAMIC MODE")
    logger.log(f"Run type: {run_type}")
    
    # 4. Initialize prediction model (currently LightGBM predictor)
    if args.disable_prediction:
        prediction_model = None
        logger.log("Prediction model disabled")
    else:
        model_path = args.model_path if hasattr(args, 'model_path') else None
        prediction_model = LGBMPredictor(model_path=model_path, run_type=run_type)
        model_name = Path(model_path).name if model_path else "default base model"
        logger.log(f"Prediction model enabled: {model_name}")
    
    # 5. Initialize BPM Estimation
    bpm_estimation = BPM_estimation(
        player,
        logger,
        initial_mode=run_type,
        manual_bpm=args.bpm,
        prediction_model=prediction_model,
        random_span=args.random_span,
        random_gamified=(args.random_gamified == 1),
        hybrid_lock_steps=args.hybrid_lock_steps,
        hybrid_unlock_time=args.hybrid_unlock_time,
        hybrid_stability_threshold=args.hybrid_stability_threshold,
        hybrid_unlock_threshold=args.hybrid_unlock_threshold,
        random_simple_threshold=args.random_simple_threshold,
        random_simple_steps=args.random_simple_steps,
        random_simple_timeout=args.random_simple_timeout,
    )
    if args.alpha_up is not None:
        bpm_estimation.set_smoothing_alpha_up(args.alpha_up)
    if args.alpha_down is not None:
        bpm_estimation.set_smoothing_alpha_down(args.alpha_down)
    logger.log("Session started")
    
    # 6. Open Serial Port
    port = args.serial_port
    ser = None
    logger.log(f"DEBUG: Attempting to open serial port {port}...")
    try:
        ser = serial.Serial(port, 115200, timeout=0.2)
        logger.log(f"DEBUG: Serial port {port} opened successfully.")
    except Exception as e:
        logger.log(f"Failed to open serial port {port}: {e}")
        return player, logger, bpm_estimation

    if not session_handshake(ser, logger, smoothing_window=smoothing_window, stride=stride):
        logger.log("Handshake failed; aborting session")
        return player, logger, bpm_estimation

    # runtime serial reads should be non-blocking to avoid slowing playback
    ser.timeout = 0
    
    # ------------------------------------------------------------------
    # STARTUP MODE: Walk-First vs Music-First
    # ------------------------------------------------------------------
    startup_success = handle_startup_mode(args, ser, player, logger, bpm_estimation, status_callback, stop_event)
    if not startup_success:
        if ser: ser.close()
        return player, logger, bpm_estimation
    
    # ------------------------------------------------------------------
    # STDIN LISTENER (For Subprocess Mode)
    # If no external queue is provided, we create one and listen to STDIN.
    # ------------------------------------------------------------------
    if command_queue is None:
        from queue import SimpleQueue
        
        command_queue = SimpleQueue()
        
        start_stdin_listener(command_queue)
    
    # ==================================================================================
    # MAIN LOOP
    # ==================================================================================
    while True:
        # CHECK STOP EVENT
        if stop_event and stop_event.is_set():
            logger.log("Session stopped by user.")
            break
            
        # PROCESS COMMAND QUEUE (From GUI Pipe or Thread)
        while not command_queue.empty():
            cmd = command_queue.get_nowait()
            
            quit =handle_engine_command(cmd, ser, logger, bpm_estimation, player)
            if quit:
                stop_event = threading.Event()
                stop_event.set()
                break
        
        # ANIMATION: Run update_bpm() every loop iteration (manual or dynamic).
        # In manual mode this still emits log packets each loop for plotting.
        bpm_estimation.update_bpm()
            
        # read the step from the serial port
        raw_line = ser.readline()
        if not raw_line:
            time.sleep(0.001)  # yield even when idle to avoid CPU/GIL starvation
            continue

        # handle the step
        # TWEAK: Check for BUTTON messages first (BTN,<delta>)
        try:
            line_str = raw_line.decode("utf-8", errors="ignore").strip()
            if line_str.startswith("BTN,"):
                parts = line_str.split(",")
                if len(parts) >= 2:
                    delta = float(parts[1])
                    logger.log(f"HARDWARE: Button Delta Received: {delta}")
                    
                    # Refactored to BPM_estimation
                    bpm_estimation.register_button_delta(delta)
                continue

            bpm, instant_bpm, sensor_ts, foot = handle_step(raw_line, player.walkingBPM)
        except ValueError:
            time.sleep(0.001)
            continue

        # Log using wall-clock processing time to keep CSV strictly monotonic.
        event_epoch = time.time()
        
        # register the step and log the data
        bpm_estimation.register_step(bpm, instant_bpm)
        logger.log_data(event_epoch, player.walkingBPM, bpm, step_event=True, instant_bpm=instant_bpm)
        logger.log(f"Processed: BPM={bpm}")

        # CPU Yield (Prevent 100% core usage)
        time.sleep(0.001)
        
    logger.log("Session ended")
    player.stop()
    player.close()
    if ser: ser.close()
    
    print("EXIT_CLEAN")
    return player, logger, bpm_estimation

if __name__ == "__main__":
    main(parse_args())