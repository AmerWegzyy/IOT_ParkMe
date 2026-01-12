"""
LightGBM Data Analysis Module

Loads session logs and generates visualizations to inspect BPM data
before LightGBM training.
"""
import importlib.util
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Load the shared loader from research/analyze_data.py without clashing with this module's name.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = PROJECT_ROOT
RESEARCH_DIR = PROJECT_ROOT / "research"
PARENT_ANALYZE = RESEARCH_DIR / "analyze_data.py"
spec = importlib.util.spec_from_file_location("research_analyze_data", PARENT_ANALYZE)
parent_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent_mod)  # type: ignore
load_all_sessions = parent_mod.load_all_sessions
remove_spikes = getattr(parent_mod, "remove_spikes", lambda df, col="walking_bpm", window=5, threshold=200: df)

# Output directories for results
RESULTS_DIR = Path(__file__).parent / "results"
PLOTS_DIR = RESULTS_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR = BASE_DIR / "server" / "logs"


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


def filter_positive_bpm(df: pd.DataFrame, col: str = "walking_bpm") -> pd.DataFrame:
    """Drop rows with non-positive BPM values."""
    if col not in df.columns:
        return df
    return df[df[col] > 0].copy()


def drop_high_spikes(df: pd.DataFrame, col: str = "walking_bpm", window: int = 5, min_bpm: float = 150, deviation: float = 50) -> pd.DataFrame:
    """
    Remove spikes only when the value is high AND far from the local median:
    keep rows where bpm < min_bpm OR |bpm - rolling_median| <= deviation.
    """
    if col not in df.columns:
        return df
    med = df[col].rolling(window=window, center=True, min_periods=1).median()
    mask = (df[col] < min_bpm) | ((df[col] - med).abs() <= deviation)
    return df[mask].copy()


def process_walking_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply the standard LightGBM preprocessing pipeline:
    - positive BPM only
    - true step events when available
    - rolling-median spike removal
    - high-spike suppression
    - clamp BPM to a sane upper bound
    """
    if df.empty:
        return df
    cleaned = filter_positive_bpm(df)
    cleaned = filter_true_steps(cleaned)
    cleaned = remove_spikes(cleaned, col="walking_bpm", window=5, threshold=200)
    cleaned = drop_high_spikes(cleaned, col="walking_bpm", window=5, min_bpm=150, deviation=50)
    cleaned = cleaned.replace([np.inf, -np.inf], np.nan).dropna(subset=["walking_bpm"])
    return cleaned


def load_raw_sessions(logs_dir=None) -> pd.DataFrame:
    """Load all session CSVs without any preprocessing."""
    resolved = Path(logs_dir) if logs_dir is not None else LOGS_DIR
    print(f"Loading data from '{resolved}'...")
    return load_all_sessions(str(resolved))


def get_raw_and_processed_sessions(logs_dir=None):
    """Return both raw and processed DataFrames for the requested logs directory."""
    raw_df = load_raw_sessions(logs_dir)
    if raw_df.empty:
        return raw_df, raw_df
    processed = process_walking_data(raw_df)
    return raw_df, processed


def load_processed_sessions(logs_dir=None) -> pd.DataFrame:
    """Convenience wrapper that returns only the processed DataFrame."""
    _, processed = get_raw_and_processed_sessions(logs_dir)
    return processed


def build_lag_features(df: pd.DataFrame, window_size: int):
    """
    Create sliding window lag features for one-step-ahead prediction.
    Uses both smoothed walking_bpm and per-step instant_bpm, and carries
    session-level meta (smoothing_window, stride, run_type).
    Returns (X_lag, y, meta, meta_mappings).
    """
    sequences, targets, metas = [], [], []

    def _to_seconds(tstr: str) -> float:
        parts = tstr.split(":")
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

    df = df.copy()
    # Encode run_type (dynamic/manual/hybrid) as numeric
    if "run_type" in df.columns:
        df["run_type"] = df["run_type"].fillna("dynamic").astype(str)
        run_type_labels = sorted(df["run_type"].unique())
        run_type_mapping = {label: float(idx) for idx, label in enumerate(run_type_labels)}
        df["_run_type_code"] = df["run_type"].map(run_type_mapping).astype(float)
    else:
        run_type_mapping = {"dynamic": 0.0}
        df["_run_type_code"] = 0.0
    if "time" in df.columns:
        try:
            df["seconds"] = df["time"].apply(_to_seconds)
        except Exception:
            df["seconds"] = pd.NA
    else:
        df["seconds"] = pd.NA

    for _, group in df.groupby("session_id"):
        g = group.copy()
        try:
            g = g.sort_values("seconds", kind="mergesort")
        except Exception:
            pass

        inst = g["instant_bpm"].copy() if "instant_bpm" in g.columns else None
        if inst is None or inst.isna().all():
            try:
                sec = g["seconds"].astype(float)
                delta = sec.diff()
                delta = delta.where(delta > 0)
                inst = 60.0 / delta
            except Exception:
                inst = None

        walk_vals = g["walking_bpm"].to_numpy(dtype=float)
        if inst is not None:
            inst_vals = (
                inst.ffill().bfill().fillna(g["walking_bpm"]).to_numpy(dtype=float)
            )
        else:
            inst_vals = walk_vals.copy()

        finite_mask = np.isfinite(walk_vals) & np.isfinite(inst_vals)
        walk_vals = walk_vals[finite_mask]
        inst_vals = inst_vals[finite_mask]

        sw = g["smoothing_window"].iloc[0] if "smoothing_window" in g else 3
        st = g["stride"].iloc[0] if "stride" in g else 1
        run_type_code = g["_run_type_code"].iloc[0] if "_run_type_code" in g else 0.0
        for idx in range(window_size, len(walk_vals)):
            walk_slice = walk_vals[idx - window_size : idx]
            inst_slice = inst_vals[idx - window_size : idx]
            sequences.append(list(walk_slice) + list(inst_slice))
            targets.append(walk_vals[idx])
            metas.append([sw, st, run_type_code])
    if not sequences:
        return np.array([]), np.array([]), np.array([]), {"run_type": run_type_mapping}
    return (
        np.array(sequences, dtype=np.float32),
        np.array(targets, dtype=np.float32),
        np.array(metas, dtype=np.float32),
        {"run_type": run_type_mapping},
    )


def _plot_distribution(df: pd.DataFrame, title_prefix: str, output_name: str):
    """Internal helper to plot histogram + correlation scatter."""
    if df.empty:
        print(f"Skipping {title_prefix.lower()} plot: no data.")
        return

    # Ensure numeric for plotting
    work = df.copy()
    work["walking_bpm"] = pd.to_numeric(work.get("walking_bpm", pd.NA), errors="coerce")
    work["song_bpm"] = pd.to_numeric(work.get("song_bpm", pd.NA), errors="coerce")
    work = work.dropna(subset=["walking_bpm", "song_bpm"])
    if work.empty:
        print(f"Skipping {title_prefix.lower()} plot: no numeric data.")
        return

    plt.figure(figsize=(10, 6))

    plt.subplot(2, 1, 1)
    plt.hist(work["walking_bpm"], bins=range(0, 651, 5), color="seagreen", edgecolor="black")
    plt.title(f"{title_prefix} - Distribution of Walking BPM")
    plt.xlabel("BPM")
    plt.ylabel("Count")
    plt.xlim(0, 650)

    plt.subplot(2, 1, 2)
    sample = work.sample(min(len(work), 2000))
    plt.scatter(sample["walking_bpm"], sample["song_bpm"], alpha=0.3, s=10, label="Samples")
    plt.title(f"{title_prefix} - Walking BPM vs Music BPM")
    plt.xlabel("User Walking BPM")
    plt.ylabel("Music BPM")
    plt.plot(
        [sample["walking_bpm"].min(), sample["walking_bpm"].max()],
        [sample["walking_bpm"].min(), sample["walking_bpm"].max()],
        "r--",
        label="Ideal Identity Line",
    )
    plt.legend()

    plt.tight_layout()
    output_path = PLOTS_DIR / output_name
    plt.savefig(output_path)
    print(f"Saved '{output_path}'")


def prepare_training_dataset(session_paths=None, window_size=4, test_size=0.2, random_seed=42):
    """
    Complete dataset preparation pipeline for training.
    
    Loads sessions, applies filters, builds lag features, splits into train/test,
    and scales the features.
    
    Args:
        session_paths: Optional list of specific session CSV paths to use.
                      If None, loads all sessions from server/logs/.
        window_size: Number of lag steps for time series features.
        test_size: Fraction of data to use for testing.
        random_seed: Random seed for reproducibility.
    
    Returns:
        Tuple of (X_train, X_test, y_train, y_test, scaler, meta_mappings)
        or None if insufficient data.
    """
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    
    # Load and process data
    if session_paths:
        # Load only specified sessions
        print(f"Loading {len(session_paths)} specified session(s)...")
        dfs = []
        for csv_path in session_paths:
            if Path(csv_path).exists():
                df_sess = pd.read_csv(csv_path)
                df_sess["session_id"] = Path(csv_path).parent.name
                dfs.append(df_sess)
        if not dfs:
            print("No valid session files found.")
            return None
        raw_df = pd.concat(dfs, ignore_index=True)
        df = process_walking_data(raw_df)
    else:
        # Load all sessions from default directory
        logs_dir = BASE_DIR / "server" / "logs"
        raw_df, df = get_raw_and_processed_sessions(logs_dir)
    
    if raw_df.empty:
        print("No data found. Run some sessions first.")
        return None

    if df.empty:
        print("No valid walking_bpm values after filtering.")
        return None

    print(f"Training on {len(df)} data points from {df['session_id'].nunique()} session(s).")

    # Build lag features
    X_lag, y, meta, meta_mappings = build_lag_features(df, window_size=window_size)
    if len(X_lag) < 20:
        print(f"Not enough sequences to train (found {len(X_lag)}).")
        return None

    # Combine lag and metadata features
    X = np.concatenate([X_lag, meta], axis=1) if len(meta) > 0 else X_lag
    
    # Remove non-finite values
    finite_mask = np.isfinite(X).all(axis=1)
    if finite_mask.sum() < len(finite_mask):
        X = X[finite_mask]
        y = y[finite_mask]
        print(f"Dropped {len(finite_mask) - len(X)} rows with non-finite features.")

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_seed
    )

    # Feature scaling
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    return X_train, X_test, y_train, y_test, scaler, meta_mappings


def analyze_bpm_distribution(logs_dir=None, session_paths=None):
    """
    Load sessions, apply the LightGBM preprocessing pipeline, and produce
    two plots: one for raw data and one for processed data.
    
    Args:
        logs_dir: Directory containing session logs (if None, uses default)
        session_paths: Optional list of specific session CSV paths to analyze
    """
    if session_paths:
        # Load specific sessions
        import pandas as pd
        from pathlib import Path
        dfs = []
        for csv_path in session_paths:
            if Path(csv_path).exists():
                df_sess = pd.read_csv(csv_path)
                df_sess["session_id"] = Path(csv_path).parent.name
                dfs.append(df_sess)
        if not dfs:
            print("No valid session files found.")
            return
        raw_df = pd.concat(dfs, ignore_index=True)
        processed_df = process_walking_data(raw_df)
    else:
        # Load all sessions from directory
        raw_df, processed_df = get_raw_and_processed_sessions(logs_dir)

    if raw_df.empty:
        print("No data found.")
        return

    print(f"Raw points: {len(raw_df)}, Processed points: {len(processed_df)}")

    _plot_distribution(raw_df, "Raw Walking Data", "lgbm_raw_bpm_distribution.png")
    _plot_distribution(processed_df, "Processed Walking Data", "lgbm_processed_bpm_distribution.png")


if __name__ == "__main__":
    analyze_bpm_distribution()

