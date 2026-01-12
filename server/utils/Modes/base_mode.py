from abc import ABC, abstractmethod

class BaseMode(ABC):
    def __init__(self, context):
        """
        :param context: The BPM_estimation instance (provides access to player, logger, state).
        """
        self.context = context
        self.logger = context.logger

    @abstractmethod
    def handle_step(self, now_ts, current_bpm, dt):
        """
        Called on every step computation.
        Should return (target_bpm, next_instant_bpm).
        """
        pass

    def activate(self):
        """Called when switching to this mode."""
        self.logger.log(f"Mode Activated: {self.__class__.__name__}")

    def deactivate(self):
        """Called when leaving this mode."""
        pass

    def on_step(self, bpm, now_ts):
        """Called when a step is detected."""
        pass

    def _smooth_towards(self, current_bpm, target_bpm, dt, alpha_up=None, alpha_down=None):
        """Standard smoothing logic utilized by all modes."""
        diff = abs(target_bpm - current_bpm)
        if diff < 0.1:
            return target_bpm

        # Resolve Alphas
        if alpha_up is None:
            alpha_up = getattr(self.context, 'smoothing_alpha_up', 0.1)
        if alpha_down is None:
            alpha_down = getattr(self.context, 'smoothing_alpha_down', 1.0)

        step = 0.0
        if target_bpm > current_bpm:
            # Acceleration
            step = (target_bpm - current_bpm) * (alpha_up * 25.0) * dt
        else:
            # Deceleration
            step = (target_bpm - current_bpm) * (alpha_down * 25.0) * dt
        
        # Clamp step to not overshoot
        if abs(step) > diff:
            return target_bpm
        
        return current_bpm + step
