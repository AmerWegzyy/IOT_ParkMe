"""
Data Filtering and Validation Module

Centralized filtering logic for LightGBM training pipeline.
Handles session validation, BPM filtering, and spike removal.
"""
import json
from pathlib import Path
import pandas as pd
import numpy as np


class DataFiltering:
    """
    Centralized data filtering and preprocessing for LightGBM training.
    Handles session validation, BPM filtering, and spike removal.
    """
    
    def __init__(self, 
                 min_steps: int = 20,
                 spike_window: int = 5,
                 spike_threshold: float = 120):
        """
        Initialize filtering parameters.
        
        Args:
            min_steps: Minimum steps required per session
            spike_window: Rolling window size for spike detection
            spike_threshold: Max deviation from rolling median (used by remove_spikes)
        """
        self.min_steps = min_steps
        self.spike_window = spike_window
        self.spike_threshold = spike_threshold
    
    @staticmethod
    def filter_true_steps(df: pd.DataFrame) -> pd.DataFrame:
        """
        Keep only rows marked as true steps if the 'step_event' column exists.
        Accepts boolean or string 'True'/'False'. If column missing, returns df unchanged.
        """
        if "step_event" not in df.columns:
            return df
        mask = df["step_event"]
        if mask.dtype == object:
            mask = mask.astype(str).str.lower() == "true"
        return df[mask].copy()

    @staticmethod
    def filter_positive_bpm(df: pd.DataFrame, col: str = "walking_bpm") -> pd.DataFrame:
        """Drop rows with non-positive BPM values."""
        if col not in df.columns:
            return df
        return df[df[col] > 0].copy()
    
    def remove_spikes(self, df: pd.DataFrame, col: str = "walking_bpm", 
                    window: int = None, threshold: float = None) -> pd.DataFrame:
        """
        Remove values that deviate more than 'threshold' from rolling median.
        This catches sensor errors while allowing real transitions.
        
        Args:
            df: DataFrame to filter
            col: Column name to check for spikes
            window: Rolling window size (uses self.spike_window if None)
            threshold: Max deviation from median (uses self.spike_threshold if None)
        """
        if col not in df.columns:
            return df
        
        window = window if window is not None else self.spike_window
        threshold = threshold if threshold is not None else self.spike_threshold
        
        med = df[col].rolling(window=window, center=True, min_periods=1).median()
        mask = (df[col] - med).abs() <= threshold
        return df[mask].copy()

    def is_valid_session(self, csv_path: Path, min_steps: int = None) -> tuple:
        """
        Check if a session is valid for training.
        Validates metadata presence, required fields, and minimum step count.
        
        Args:
            csv_path: Path to session CSV file
            min_steps: Minimum number of step events required (uses self.min_steps if None)
        
        Returns:
            (is_valid: bool, reason: str)
        """
        min_steps = min_steps if min_steps is not None else self.min_steps
        
        if not csv_path.exists():
            return False, "no_csv"
        
        try:
            # Check metadata
            with open(csv_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                
                if not first_line.startswith("# meta:"):
                    return False, "no_metadata"
                
                meta_str = first_line.replace("# meta:", "").strip()
                metadata = json.loads(meta_str)
                
                # Check required fields
                required = ['run_type', 'stride', 'smoothing_window']
                missing = [f for f in required if f not in metadata]
                if missing:
                    return False, f"missing_{','.join(missing)}"
            
            # Check step count
            df = pd.read_csv(csv_path, comment="#")
            if df.empty:
                return False, "empty"
            
            step_count = (df['step_event'] == True).sum() if 'step_event' in df.columns else len(df)
            if step_count < min_steps:
                return False, f"too_short_{step_count}_steps"
            
            return True, "ok"
            
        except json.JSONDecodeError:
            return False, "invalid_json"
        except Exception as e:
            return False, f"error_{str(e)[:20]}"

    def process_walking_data(self, df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
        """
        Apply the standard LightGBM preprocessing pipeline:
        - true step events only (actual foot strikes, not interpolated data)
        - positive BPM only (filters out instant_bpm=0.0 from first steps)
        - rolling-median spike removal
        
        Args:
            df: Raw session DataFrame
            verbose: If True, print diagnostic information
        
        Returns:
            Cleaned DataFrame
        
        NOTE: We train only on actual step events because the data between steps
        is just interpolation - we only care about the BPM at each foot strike.
        """
        if df.empty:
            return df
        
        # Track data at each stage for diagnostics
        initial_count = len(df)
        
        # Filter to only true step events (actual foot strikes)
        cleaned = self.filter_true_steps(df)
        
        # Check if we have any step events
        if cleaned.empty:
            if verbose:
                print("WARNING: No step events found in data after filter_true_steps")
            return pd.DataFrame()
        
        # Check if walking_bpm column exists after filtering
        if "walking_bpm" not in cleaned.columns:
            if verbose:
                print(f"WARNING: walking_bpm column missing. Available: {list(cleaned.columns)}")
            return pd.DataFrame()
        
        # Filter positive BPM (removes instant_bpm=0.0 from first steps)
        cleaned = self.filter_positive_bpm(cleaned)
        
        if cleaned.empty:
            if verbose:
                print("WARNING: No data remaining after filtering positive BPM")
            return pd.DataFrame()
        
        after_basic = len(cleaned)
        
        # Remove spikes (+/-threshold BPM from rolling median of neighbors)
        # Allows real transitions (walk->jog, mode switches) while catching sensor errors
        cleaned = self.remove_spikes(cleaned, col="walking_bpm")
        after_spike_removal = len(cleaned)
        
        # Final cleanup - only apply if we still have data and the column
        if not cleaned.empty and "walking_bpm" in cleaned.columns:
            cleaned = cleaned.replace([np.inf, -np.inf], np.nan).dropna(subset=["walking_bpm"])
        
        final_count = len(cleaned)
        
        # Diagnostic logging
        if verbose:
            spike_removed = after_basic - after_spike_removal
            inf_nan_removed = after_spike_removal - final_count
            
            print(f"[DATA CLEANING] Initial: {initial_count} steps")
            print(f"   -> After basic filters (step_event, positive): {after_basic} (-{initial_count - after_basic})")
            print(f"   -> After spike removal (+/-{self.spike_threshold} BPM): {after_spike_removal} (-{spike_removed}, {100*spike_removed/max(after_basic,1):.2f}%)")
            if inf_nan_removed > 0:
                print(f"   -> After inf/nan cleanup: {final_count} (-{inf_nan_removed})")
            print(f"   OK Final: {final_count} clean steps ({100*final_count/max(initial_count,1):.1f}% retained)\n")
        
        return cleaned
