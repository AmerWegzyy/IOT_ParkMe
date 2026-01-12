import statistics
from utils.Modes.base_mode import BaseMode

class HybridMode(BaseMode):
    def __init__(self, context, lock_steps=5, unlock_time=1.5, stability_threshold=3.0, unlock_threshold=5.0):
        super().__init__(context)
        # State
        self.locked_bpm = None
        self.stability_buffer = [] 
        self.last_step_time = 0.0
        self.last_step_bpm = context.player.walkingBPM 
        
        # Configurable Settings (from init params)
        self.lock_steps = lock_steps
        self.unlock_time = unlock_time  # Not used anymore, kept for compatibility
        self.stability_threshold = stability_threshold
        self.unlock_threshold = unlock_threshold

    def reset(self):
        self.locked_bpm = None
        self.stability_buffer.clear()

    def set_lock_steps(self, steps: int):
        self.lock_steps = max(2, int(steps))
        self.logger.log(f"HYBRID: Lock steps set to {self.lock_steps}")

    def set_unlock_time(self, seconds: float):
        self.unlock_time = max(0.5, float(seconds))
        self.logger.log(f"HYBRID: Unlock time set to {self.unlock_time}s")

    def set_stability_threshold(self, bpm: float):
        self.stability_threshold = max(1.0, float(bpm))
        self.logger.log(f"HYBRID: Stability threshold set to {self.stability_threshold} BPM")

    def set_unlock_threshold(self, bpm: float):
        self.unlock_threshold = max(5.0, float(bpm))
        self.logger.log(f"HYBRID: Unlock threshold set to {self.unlock_threshold} BPM")

    def on_step(self, bpm, now_ts):
        """Called when a step is detected."""
        self.last_step_time = now_ts
        self.last_step_bpm = bpm 
        
        # If locked, check if this step deviates - unlock IMMEDIATELY if so
        if self.locked_bpm is not None:
            diff = abs(bpm - self.locked_bpm)
            
            if diff > self.unlock_threshold:
                # Immediate unlock on deviation
                self.logger.log(f"HYBRID: Unlocking! Walker {bpm:.1f} vs Locked {self.locked_bpm:.1f} (deviation: {diff:.1f} > threshold: {self.unlock_threshold:.1f})")
                self.locked_bpm = None
                self.stability_buffer.clear()
                # Don't start buffering on the same step that caused unlock
                return
        
        # If unlocked, buffer for potential lock
        if self.locked_bpm is None:
            self.stability_buffer.append(bpm)
            if len(self.stability_buffer) > self.lock_steps: 
                self.stability_buffer.pop(0)

            if len(self.stability_buffer) == self.lock_steps:
                delta = max(self.stability_buffer) - min(self.stability_buffer)
                if delta < self.stability_threshold:
                    self.locked_bpm = statistics.mean(self.stability_buffer)
                    self.logger.log(f"HYBRID: Locked at {self.locked_bpm:.1f} BPM (stability range: {delta:.1f} BPM)")

    def handle_step(self, now_ts, current_bpm, dt):
        """
        Returns (target, smoothed_next)
        """
        # 1. Determine Target
        if self.locked_bpm is not None:
            # Cruise control - use locked BPM
            target = self._handle_locked_check(now_ts, current_bpm)
        else:
            # Following mode - use last detected step BPM
            target = self.last_step_bpm
        
        # 2. Decay Logic (Safety)
        if self.last_step_time > 0:
            interval = now_ts - self.last_step_time
            if interval > 0:
                decay_limit = 60.0 / interval
                if decay_limit < target:
                    target = decay_limit

        # 3. Smoothing with Boost
        alpha_up = getattr(self.context, 'smoothing_alpha_up', 0.1)
        
        # Boost logic - accelerate faster when far from target
        bpm_diff = target - current_bpm
        if bpm_diff > 5.0:
            boost = 1.0 + (bpm_diff - 5.0) * 0.1
            alpha_up *= min(boost, 4.0)

        smoothed = self._smooth_towards(current_bpm, target, dt, alpha_up=alpha_up)
        
        return target, smoothed

    def _handle_locked_check(self, now_ts, current_bpm):
        """Return the target BPM (locked or following walker)."""
        if self.locked_bpm is not None:
            return self.locked_bpm
        return self.last_step_bpm
