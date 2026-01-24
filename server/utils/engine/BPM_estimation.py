import time
import threading
from ..hardware.midi_player import MidiBeatSync
from ..session.logger import Logger
from ..prediction_model.LGBM_predictor import LGBMPredictor

# Import Modes
from ..Modes.manual_mode import ManualMode
from ..Modes.random_mode import RandomMode
from ..Modes.dynamic_mode import DynamicMode
from ..Modes.hybrid_mode import HybridMode

class BPM_estimation:
    def __init__(self, player: MidiBeatSync, logger: Logger, initial_mode: str = "dynamic",
                manual_bpm: float = None, prediction_model: LGBMPredictor = None,
                random_span: float = 0.20, random_gamified: bool = False,
                hybrid_lock_steps: int = 5, hybrid_unlock_time: float = 1.5,
                hybrid_stability_threshold: float = 5.0, hybrid_unlock_threshold: float = 10.0,
                random_simple_threshold: float = 5.0, random_simple_steps: int = 20,
                random_simple_timeout: float = 30.0) -> None:
        
        # ------------ Context ------------
        self.player = player
        self.logger = logger
        self.prediction_model = prediction_model
        
        # ------------ State ------------
        self.step_count = 0
        self.last_msg_time = time.time()
        self.last_update_time = time.time()
        self.last_gui_log_time = time.time()
        
        # ------------ Modes ------------
        self.manual_mode_obj = ManualMode(self)
        self.random_mode_obj = RandomMode(self, span=random_span, gamified=random_gamified,
                                        simple_threshold=random_simple_threshold,
                                        simple_steps=random_simple_steps,
                                        simple_timeout=random_simple_timeout)
        self.dynamic_mode_obj = DynamicMode(self)
        self.hybrid_mode_obj = HybridMode(self, lock_steps=hybrid_lock_steps, 
                                        unlock_time=hybrid_unlock_time,
                                        stability_threshold=hybrid_stability_threshold,
                                        unlock_threshold=hybrid_unlock_threshold)
        
        # ------------ Active State ------------
        self.active_mode = initial_mode # "dynamic", "random", "manual", "hybrid"
        
        # ------------ Configuration ------------
        if manual_bpm: 
            self.set_manual_bpm(manual_bpm)
        
        # Apply specific configs if starting in that mode
        if self.active_mode == "random":
            self.set_random_span(random_span)
            self.set_random_gamified(random_gamified)
            self.set_random_simple_threshold(random_simple_threshold)
            self.set_random_simple_steps(random_simple_steps)
            self.set_random_simple_timeout(random_simple_timeout)
            self.random_mode_obj.activate()
        
        elif self.active_mode == "hybrid":
            self.set_hybrid_lock_steps(hybrid_lock_steps)
            self.set_hybrid_unlock_time(hybrid_unlock_time)
            self.set_hybrid_stability_threshold(hybrid_stability_threshold)
            self.set_hybrid_unlock_threshold(hybrid_unlock_threshold)
            self.hybrid_mode_obj.activate()
            
        elif self.active_mode == "manual": 
            self.manual_mode_obj.activate()
            
        elif self.active_mode == "dynamic": 
            self.dynamic_mode_obj.activate()

        # ------------ Smoothing Params ------------
        self.smoothing_alpha_up = 0.1
        self.smoothing_alpha_down = 0.05
        self.target_bpm = player.walkingBPM

        # ------------ ML Warmup ------------
        self._warmup_done = threading.Event()
        self._warmup_failed = False
        if self.prediction_model:
            threading.Thread(target=self._run_warmup, args=(player.walkingBPM,), daemon=True).start()

    # ----------- State Switches -----------
    
    # --- manual mode ---
    def set_manual_mode(self, enabled: bool):
        self.active_mode = "manual"
        self.manual_mode_obj.activate()

    def set_manual_bpm(self, bpm: float):
        self.manual_mode_obj.set_bpm(bpm)
    
    # --- random mode ---
    def set_random_mode(self, enabled: bool):
        self.active_mode = "random"
        self.random_mode_obj.activate()

    def set_random_span(self, span: float):
        self.random_mode_obj.set_span(span)

    def set_random_gamified(self, enabled: bool):
        self.random_mode_obj.set_gamified(enabled)

    def set_random_simple_threshold(self, threshold: float):
        self.random_mode_obj.set_simple_threshold(threshold)

    def set_random_simple_steps(self, steps: int):
        self.random_mode_obj.set_simple_steps(steps)

    def set_random_simple_timeout(self, seconds: float):
        self.random_mode_obj.set_simple_timeout(seconds)

    # --- hybrid mode ---
    def set_hybrid_mode(self, enabled: bool):
        self.active_mode = "hybrid"
        self.hybrid_mode_obj.activate()

    def set_hybrid_lock_steps(self, steps: int):
        self.hybrid_mode_obj.set_lock_steps(steps)

    def set_hybrid_unlock_time(self, seconds: float):
        self.hybrid_mode_obj.set_unlock_time(seconds)

    def set_hybrid_stability_threshold(self, bpm: float):
        self.hybrid_mode_obj.set_stability_threshold(bpm)

    def set_hybrid_unlock_threshold(self, bpm: float):
        self.hybrid_mode_obj.set_unlock_threshold(bpm)

    # --- dynamic mode ---
    def set_dynamic_mode(self, enabled: bool):
        self.active_mode = "dynamic"
        self.dynamic_mode_obj.activate()


    def _get_active_mode(self):
        if self.active_mode == "manual": return self.manual_mode_obj
        if self.active_mode == "random": return self.random_mode_obj
        if self.active_mode == "hybrid": return self.hybrid_mode_obj
        return self.dynamic_mode_obj

    def _run_warmup(self, initial_bpm):
        try: self.prediction_model.warmup(initial_bpm)
        except: self._warmup_failed = True
        finally: self._warmup_done.set()
    
    # ----------- Alpha control -----------
    def set_smoothing_alpha_up(self, a): self.smoothing_alpha_up = float(a)
    def set_smoothing_alpha_down(self, a): self.smoothing_alpha_down = float(a)


    # ----------- Input Handling -----------
    def register_step(self, new_bpm, instant_bpm=None):
        """Called when a new step is detected."""
        self.last_msg_time = time.time()
        self.step_count += 1
        
        # ML Prediction Hook
        if self.prediction_model and self._warmup_done.is_set() and not self._warmup_failed:
            try:
                self.prediction_model.add_step(new_bpm, instant_bpm)
                pred = self.prediction_model.predict_next()
                if pred: 
                    # Blending prediction
                     new_bpm = float(pred) * 0.65 + new_bpm * 0.35
            except: pass

        # Notify active mode
        mode = self._get_active_mode()
        mode.on_step(new_bpm, self.last_msg_time)

    def register_button_delta(self, delta: float):
        """Hardware button press."""
        # Force manual mode if button pressed?
        # Current logic: If in manual mode, adjust it.
        if self.active_mode == "manual":
            new_val = self.manual_mode_obj.adjust_bpm(delta)
            self.player.set_BPM(new_val)
            self.target_bpm = new_val
            
            # Notify GUI
            import sys
            print(f"GUI_SYNC:MANUAL_BPM:{new_val}")
            sys.stdout.flush()
            return new_val
        return None


    # ----------- Main Loop -----------
    def update_bpm(self):
        """Called ~10Hz by main loop."""
        now_ts = time.time()
        dt = now_ts - self.last_update_time
        self.last_update_time = now_ts
        
        current_bpm = self.player.walkingBPM
        
        # Determine Target & Next BPM from Active Mode
        mode = self._get_active_mode()
        target, next_bpm = mode.handle_step(now_ts, current_bpm, dt)

        # Apply
        self.target_bpm = target
        self.player.set_BPM(next_bpm)
        
        # Logging
        if now_ts - self.last_gui_log_time > 0.1:
            try:
                self.logger.log_data(now_ts, current_bpm, self.target_bpm, step_event=False)
            except: pass
            self.last_gui_log_time = now_ts
