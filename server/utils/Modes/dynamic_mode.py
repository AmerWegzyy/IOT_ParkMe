from utils.Modes.base_mode import BaseMode

class DynamicMode(BaseMode):
    def __init__(self, context):
        super().__init__(context)
        self.last_step_time = 0.0
        self.last_step_bpm = context.player.walkingBPM  # Start at song BPM

    def on_step(self, bpm, now_ts):
        """Record detected walking BPM and timestamp."""
        self.last_step_time = now_ts
        self.last_step_bpm = bpm  # Store the detected BPM

    def handle_step(self, now_ts, current_bpm, dt):
        """
        Returns (target, smoothed_next)
        """
        # 1. Base Target = Last detected walking BPM
        target = self.last_step_bpm
        
        # 2. Decay Logic (Safety) - If no steps, slow down
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
