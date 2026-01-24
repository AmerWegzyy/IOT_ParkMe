from pathlib import Path
from collections import deque
import threading
import joblib
import numpy as np
import warnings
from ..paths import get_models_dir

# Suppress "X does not have valid feature names" warning from LightGBM/Sklearn
warnings.filterwarnings("ignore", category=UserWarning, message=".*X does not have valid feature names.*")


class LGBMPredictor:
    """
    LightGBM-based next-step predictor using lag features.
    Loads the base model artifact exported by server/utils/prediction_model/train_lgbm.py
    (expects keys: model, scaler, window_size).
    """

    def __init__(self, model_path=None, run_type=None):
        default = get_models_dir() / "lgbm_model.joblib"
        self.model_path = Path(model_path or default)
        self.model = None
        self.scaler = None
        self.calibrator = None  # For user head personalization
        self.is_user_head = False
        self.window = None
        self.extra_feature_names = ["smoothing_window", "stride", "run_type"]
        self.run_type_mapping: dict[str, float] | None = None
        self.run_type = run_type
        self.buffer = None  # deque of tuples: (walking_bpm, instant_bpm)
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        
        payload = joblib.load(self.model_path)
        
        # Check if this is a user head model
        if isinstance(payload, dict) and "calibrator" in payload:
            self.is_user_head = True
            self.calibrator = payload["calibrator"]
            self.window = int(payload["window_size"])
            
            # Load the base model
            base_path = Path(payload["base_model_path"])
            if not base_path.exists():
                raise FileNotFoundError(f"Base model not found: {base_path}")
            
            base_artifact = joblib.load(base_path)
            self.model = base_artifact["model"]
            self.scaler = base_artifact["scaler"]
            
            schema = base_artifact.get("feature_schema")
            if schema and "extra" in schema:
                self.extra_feature_names = schema["extra"]
                self.run_type_mapping = schema.get("run_type_mapping")
        
        # Original base model loading
        elif isinstance(payload, dict) and "model" in payload and "scaler" in payload and "window_size" in payload:
            self.is_user_head = False
            self.model = payload["model"]
            self.scaler = payload["scaler"]
            self.window = int(payload["window_size"])
            
            schema = payload.get("feature_schema")
            if schema and "extra" in schema:
                self.extra_feature_names = schema["extra"]
                self.run_type_mapping = schema.get("run_type_mapping")
        else:
            raise ValueError("Invalid LightGBM model file")
        
        self.buffer = deque(maxlen=self.window)

    def set_run_type(self, run_type):
        """Set or update the run type (dynamic/manual/hybrid) used for inference."""
        self.run_type = run_type

    def _encode_run_type(self, run_type_value):
        if run_type_value is None:
            run_type_value = self.run_type
        if run_type_value is None:
            return 0.0
        try:
            return float(run_type_value)
        except Exception:
            pass
        if isinstance(run_type_value, str):
            if self.run_type_mapping and run_type_value in self.run_type_mapping:
                return float(self.run_type_mapping[run_type_value])
            if self.run_type_mapping and "dynamic" in self.run_type_mapping:
                return float(self.run_type_mapping["dynamic"])
        return 0.0

    def add_step(self, walking_bpm, instant_bpm=None):
        if self.buffer is None:
            return
        with self._lock:
            if instant_bpm is None:
                instant_bpm = walking_bpm
            self.buffer.append((float(walking_bpm), float(instant_bpm)))

    def predict_next(self, smoothing_window: float | int = 3, stride: float | int = 1, run_type=None):
        if not self.model or self.buffer is None:
            return None
        with self._lock:
            if len(self.buffer) < self.window:
                return None
            buf = list(self.buffer)
        extras_map = {
            "smoothing_window": float(smoothing_window),
            "stride": float(stride),
            "run_type": self._encode_run_type(run_type),
        }
        extras = [float(extras_map.get(name, 0.0)) for name in self.extra_feature_names]
        # Flatten: walk lags then instant lags
        walk_lags = [p[0] for p in buf]
        inst_lags = [p[1] for p in buf]
        X = np.array([walk_lags + inst_lags + extras], dtype=float)
        X_scaled = self.scaler.transform(X)
        
        # Base prediction
        base_pred = float(self.model.predict(X_scaled)[0])
        
        # If using user head, apply calibration
        if self.is_user_head and self.calibrator is not None:
            calib_input = np.concatenate([[base_pred], X_scaled[0]]).reshape(1, -1)
            return float(self.calibrator.predict(calib_input)[0])
        
        return base_pred

    def warmup(self, initial_bpm: float | None = None, run_type=None):
        """
        Run a single inference on a synthetic window to pay model/scaler warm-up
        costs upfront. Does not mutate the live buffer.
        """
        if not self.model or self.window is None or self.scaler is None:
            return
        bpm = float(initial_bpm) if initial_bpm is not None else 0.0
        walk = np.full((self.window,), bpm, dtype=float)
        inst = np.full((self.window,), bpm, dtype=float)
        extras_map = {
            "smoothing_window": 3.0,
            "stride": 1.0,
            "run_type": self._encode_run_type(run_type),
        }
        extras = np.array([float(extras_map.get(name, 0.0)) for name in self.extra_feature_names], dtype=float)
        row = np.concatenate([walk, inst, extras])
        X_scaled = self.scaler.transform(row.reshape(1, -1))
        
        # Warm up base model
        base_pred = self.model.predict(X_scaled)[0]
        
        # If user head, also warm up calibrator
        if self.is_user_head and self.calibrator is not None:
            calib_input = np.concatenate([[base_pred], X_scaled[0]]).reshape(1, -1)
            _ = self.calibrator.predict(calib_input)

