"""
Data Augmentation for LightGBM Training

Generates synthetic training data while preserving physical realism.
Augmented data is stored separately and can be optionally included in training.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import json
from typing import List, Dict, Tuple
import shutil


class BPMDataAugmentor:
    """
    Augments BPM walking data with realistic variations.
    
    Augmentation strategies:
    1. Time warping: Simulate walking at different speeds
    2. Gaussian noise: Simulate sensor measurement variability
    3. Parameter variation: Simulate different stride and smoothing_window settings
    """
    
    def __init__(self, 
                 time_warp_factors: List[float] = [0.9, 1.1],
                 noise_std: float = 2.0,
                 stride_variants: List[int] = [1, 2, 3],
                 smoothing_variants: List[int] = [2, 3, 5, 7],
                 enable_parameter_augmentation: bool = True,
                 min_session_steps: int = 50,
                 bpm_min: float = 60.0,
                 bpm_max: float = 250.0,
                 random_seed: int = 42):
        """
        Initialize augmentation parameters.
        
        Args:
            time_warp_factors: Speed multipliers for time warping
                              (0.9 = slower walking, 1.1 = faster walking)
            noise_std: Standard deviation for Gaussian sensor noise (BPM)
            stride_variants: Different stride values to simulate [1, 2, 3]
            smoothing_variants: Different smoothing_window values to simulate [2, 3, 5, 7]
            enable_parameter_augmentation: Enable stride/smoothing augmentation
            min_session_steps: Minimum steps required to augment a session
            bpm_min: Minimum realistic BPM value
            bpm_max: Maximum realistic BPM value
            random_seed: Random seed for reproducibility
        """
        self.time_warp_factors = time_warp_factors
        self.noise_std = noise_std
        self.stride_variants = stride_variants
        self.smoothing_variants = smoothing_variants
        self.enable_parameter_augmentation = enable_parameter_augmentation
        self.min_session_steps = min_session_steps
        self.bpm_min = bpm_min
        self.bpm_max = bpm_max
        self.random_seed = random_seed
        np.random.seed(random_seed)
    
    def augment_session(self, csv_path: Path, output_base_dir: Path) -> List[Path]:
        """
        Create augmented versions of a single session.
        
        Args:
            csv_path: Path to original session CSV file
            output_base_dir: Base directory for augmented data (e.g., server/logs/Augmented)
        
        Returns:
            List of paths to generated augmented session CSVs
        """
        # Read original session
        try:
            df = pd.read_csv(csv_path, comment='#')
        except Exception as e:
            print(f"   WARNING: Could not read {csv_path}: {e}")
            return []
        
        # Read metadata
        metadata = {}
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith('# meta:'):
                    metadata = json.loads(first_line.replace('# meta:', ''))
        except Exception:
            pass
        
        # Check if session has minimum steps
        if 'step_event' in df.columns:
            step_count = (df['step_event'] == True).sum()
        else:
            step_count = len(df)
        
        if step_count < self.min_session_steps:
            return []  # Too short, don't augment
        
        augmented_paths = []
        
        # Determine original session path structure
        # e.g., "Default/session_2026-01-20_15-30-00" from full path
        session_name = csv_path.parent.name
        user_folder = csv_path.parent.parent.name
        
        # Time warp augmentation
        for factor in self.time_warp_factors:
            aug_df = self._time_warp(df, factor)
            aug_metadata = metadata.copy()
            aug_metadata['augmented'] = True
            aug_metadata['augmentation_type'] = 'time_warp'
            aug_metadata['time_warp_factor'] = factor
            aug_metadata['original_session'] = f"{user_folder}/{session_name}"
            
            aug_path = self._save_augmented(
                aug_df, aug_metadata, output_base_dir,
                user_folder, session_name, f"warp{factor:.1f}"
            )
            if aug_path:
                augmented_paths.append(aug_path)
        
        # Noise augmentation
        aug_df = self._add_noise(df)
        aug_metadata = metadata.copy()
        aug_metadata['augmented'] = True
        aug_metadata['augmentation_type'] = 'gaussian_noise'
        aug_metadata['noise_std'] = self.noise_std
        aug_metadata['original_session'] = f"{user_folder}/{session_name}"
        
        aug_path = self._save_augmented(
            aug_df, aug_metadata, output_base_dir,
            user_folder, session_name, f"noise{self.noise_std:.0f}"
        )
        if aug_path:
            augmented_paths.append(aug_path)
        
        # Parameter augmentation (stride and smoothing_window variants)
        if self.enable_parameter_augmentation and 'instant_bpm' in df.columns:
            original_stride = metadata.get('stride', 1)
            original_smoothing = metadata.get('smoothing_window', 3)
            
            # Create variants with different parameter combinations
            for new_stride in self.stride_variants:
                for new_smoothing in self.smoothing_variants:
                    # Skip if same as original
                    if new_stride == original_stride and new_smoothing == original_smoothing:
                        continue
                    
                    aug_df = self._change_parameters(df, new_stride, new_smoothing)
                    if aug_df is None or len(aug_df) < 20:  # Need minimum data points
                        continue
                    
                    aug_metadata = metadata.copy()
                    aug_metadata['augmented'] = True
                    aug_metadata['augmentation_type'] = 'parameter_variant'
                    aug_metadata['stride'] = new_stride
                    aug_metadata['smoothing_window'] = new_smoothing
                    aug_metadata['original_stride'] = original_stride
                    aug_metadata['original_smoothing_window'] = original_smoothing
                    aug_metadata['original_session'] = f"{user_folder}/{session_name}"
                    
                    aug_path = self._save_augmented(
                        aug_df, aug_metadata, output_base_dir,
                        user_folder, session_name, f"s{new_stride}w{new_smoothing}"
                    )
                    if aug_path:
                        augmented_paths.append(aug_path)
        
        return augmented_paths
    
    def _time_warp(self, df: pd.DataFrame, factor: float) -> pd.DataFrame:
        """
        Apply time warping to simulate different walking speeds.
        
        Args:
            df: Original session DataFrame
            factor: Speed multiplier (>1.0 = faster, <1.0 = slower)
        
        Returns:
            Augmented DataFrame
        """
        aug = df.copy()
        
        # Scale BPM values and clip to realistic range
        if 'walking_bpm' in aug.columns:
            aug['walking_bpm'] = (df['walking_bpm'] * factor).clip(self.bpm_min, self.bpm_max)
        
        if 'instant_bpm' in aug.columns:
            aug['instant_bpm'] = (df['instant_bpm'] * factor).clip(self.bpm_min, self.bpm_max)
        
        # Note: We don't modify timestamps to keep data format consistent
        # The BPM change already represents the speed change
        
        return aug
    
    def _add_noise(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add Gaussian sensor noise to BPM readings.
        
        Args:
            df: Original session DataFrame
        
        Returns:
            Augmented DataFrame with noise
        """
        aug = df.copy()
        
        # Add noise to BPM columns
        if 'walking_bpm' in aug.columns:
            noise = np.random.normal(0, self.noise_std, len(df))
            aug['walking_bpm'] = (df['walking_bpm'] + noise).clip(self.bpm_min, self.bpm_max)
        
        if 'instant_bpm' in aug.columns:
            noise = np.random.normal(0, self.noise_std, len(df))
            aug['instant_bpm'] = (df['instant_bpm'] + noise).clip(self.bpm_min, self.bpm_max)
        
        return aug
    
    def _change_parameters(self, df: pd.DataFrame, new_stride: int, new_smoothing: int) -> pd.DataFrame:
        """
        Simulate different stride and smoothing_window parameters using instant_bpm data.
        
        This recreates what the ESP32 would have produced with different parameters:
        - smoothing_window: Average N recent instant_bpm values
        - stride: Update walking_bpm every N steps
        
        Args:
            df: Original session DataFrame (must have instant_bpm column)
            new_stride: New stride value to simulate
            new_smoothing: New smoothing_window value to simulate
        
        Returns:
            Augmented DataFrame with simulated walking_bpm, or None if insufficient data
        """
        if 'instant_bpm' not in df.columns:
            return None
        
        # Get only rows with step_event = True (actual steps)
        if 'step_event' in df.columns:
            steps_df = df[df['step_event'] == True].copy()
        else:
            steps_df = df.copy()
        
        if len(steps_df) < new_smoothing + new_stride:
            return None  # Not enough data
        
        instant_bpm_values = steps_df['instant_bpm'].values
        
        # Simulate ESP32 behavior:
        # 1. Calculate rolling average (smoothing_window)
        # 2. Update every stride steps
        
        new_walking_bpm = []
        new_instant_bpm = []
        new_times = []
        new_song_bpm = []
        
        for i in range(len(instant_bpm_values)):
            # Calculate smoothed BPM from instant values
            # Use up to smoothing_window previous values
            start_idx = max(0, i + 1 - new_smoothing)
            window_values = instant_bpm_values[start_idx:i + 1]
            smoothed_bpm = np.mean(window_values)
            
            # Only update walking_bpm every 'stride' steps
            if i % new_stride == 0 or i == 0:
                new_walking_bpm.append(smoothed_bpm)
                new_instant_bpm.append(instant_bpm_values[i])
                new_times.append(steps_df.iloc[i]['time'] if 'time' in steps_df.columns else i)
                new_song_bpm.append(steps_df.iloc[i]['song_bpm'] if 'song_bpm' in steps_df.columns else 0)
        
        # Create new DataFrame
        aug_df = pd.DataFrame({
            'time': new_times,
            'song_bpm': new_song_bpm,
            'walking_bpm': np.clip(new_walking_bpm, self.bpm_min, self.bpm_max),
            'step_event': True,
            'instant_bpm': np.clip(new_instant_bpm, self.bpm_min, self.bpm_max)
        })
        
        return aug_df
    
    def _save_augmented(self, df: pd.DataFrame, metadata: Dict, 
                       output_base_dir: Path, user_folder: str,
                       session_name: str, aug_suffix: str) -> Path:
        """
        Save augmented session with metadata.
        
        Args:
            df: Augmented DataFrame
            metadata: Session metadata dict
            output_base_dir: Base augmented data directory
            user_folder: Original user folder name (e.g., "Default")
            session_name: Original session folder name
            aug_suffix: Suffix for augmented session (e.g., "warp1.1")
        
        Returns:
            Path to saved CSV file, or None if save failed
        """
        try:
            # Create directory structure: Augmented/UserFolder/session_name_suffix/
            aug_session_name = f"{session_name}_{aug_suffix}"
            session_dir = output_base_dir / user_folder / aug_session_name
            session_dir.mkdir(parents=True, exist_ok=True)
            
            csv_path = session_dir / "session_data.csv"
            
            # Write with metadata header
            with open(csv_path, 'w', encoding='utf-8') as f:
                f.write(f"# meta:{json.dumps(metadata)}\n")
                df.to_csv(f, index=False)
            
            return csv_path
        except Exception as e:
            print(f"   WARNING: Could not save augmented session: {e}")
            return None


def generate_augmented_data(logs_dir: Path, 
                           output_dir: Path = None,
                           enable: bool = True,
                           clean_existing: bool = True,
                           verbose: bool = True) -> Tuple[Path, int]:
    """
    Generate augmented dataset from all real sessions.
    
    Args:
        logs_dir: Path to server/logs directory
        output_dir: Where to save augmented data (default: logs_dir/Augmented)
        enable: If False, skip augmentation and return immediately
        clean_existing: If True, delete existing Augmented folder before generating
        verbose: If True, print progress information
    
    Returns:
        Tuple of (augmented_dir_path, num_generated_sessions)
    """
    if not enable:
        if verbose:
            print("[AUGMENTATION] Disabled - using original data only")
        return None, 0
    
    if output_dir is None:
        output_dir = logs_dir / "Augmented"
    
    # Clean existing augmented data if requested
    if clean_existing and output_dir.exists():
        if verbose:
            print(f"[AUGMENTATION] Cleaning existing augmented data...")
        try:
            shutil.rmtree(output_dir)
        except Exception as e:
            print(f"   WARNING: Could not clean {output_dir}: {e}")
    
    augmentor = BPMDataAugmentor()
    
    if verbose:
        print(f"[AUGMENTATION] Generating synthetic data...")
        print(f"   Source: {logs_dir}")
        print(f"   Output: {output_dir}")
        print(f"   Strategies:")
        print(f"     - Time warp: {augmentor.time_warp_factors}")
        print(f"     - Gaussian noise: std={augmentor.noise_std} BPM")
        if augmentor.enable_parameter_augmentation:
            print(f"     - Parameter variants: stride={augmentor.stride_variants}, smoothing={augmentor.smoothing_variants}")
    
    total_generated = 0
    processed_sessions = 0
    skipped_sessions = 0
    
    # Find all session CSVs in logs directory
    for csv_path in sorted(logs_dir.rglob("session_data.csv")):
        # Skip if already in Augmented folder
        if "Augmented" in str(csv_path):
            continue
        
        # Skip if doesn't exist
        if not csv_path.exists():
            continue
        
        processed_sessions += 1
        
        # Generate augmented versions
        aug_paths = augmentor.augment_session(csv_path, output_dir)
        
        if aug_paths:
            total_generated += len(aug_paths)
        else:
            skipped_sessions += 1
    
    if verbose:
        print(f"[AUGMENTATION] Complete!")
        print(f"   Processed: {processed_sessions} original sessions")
        print(f"   Generated: {total_generated} synthetic sessions")
        print(f"   Skipped: {skipped_sessions} (too short, <{augmentor.min_session_steps} steps)")
        print(f"   Total dataset: {processed_sessions + total_generated} sessions")
    
    return output_dir, total_generated


def count_augmented_sessions(logs_dir: Path) -> Tuple[int, int]:
    """
    Count real vs augmented sessions.
    
    Args:
        logs_dir: Path to server/logs directory
    
    Returns:
        Tuple of (real_count, augmented_count)
    """
    augmented_dir = logs_dir / "Augmented"
    
    real_count = 0
    augmented_count = 0
    
    for csv_path in logs_dir.rglob("session_data.csv"):
        if "Augmented" in str(csv_path):
            augmented_count += 1
        else:
            real_count += 1
    
    return real_count, augmented_count


if __name__ == "__main__":
    """Test augmentation on current dataset"""
    import sys
    
    # Get project root
    project_root = Path(__file__).resolve().parents[2]
    logs_dir = project_root / "server" / "logs"
    
    print("=" * 60)
    print("BPM Data Augmentation Test")
    print("=" * 60)
    
    # Generate augmented data
    aug_dir, num_gen = generate_augmented_data(
        logs_dir, 
        enable=True, 
        clean_existing=True,
        verbose=True
    )
    
    print("\n" + "=" * 60)
    print("Dataset Summary:")
    print("=" * 60)
    
    real, aug = count_augmented_sessions(logs_dir)
    print(f"Real sessions: {real}")
    print(f"Augmented sessions: {aug}")
    print(f"Total: {real + aug}")
    print(f"Augmentation multiplier: {(real + aug) / max(real, 1):.1f}x")
