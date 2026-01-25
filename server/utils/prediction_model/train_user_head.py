"""
Lightweight CLI to train a per-user calibration head on top of the base
LightGBM model. You can point it at:
  - a CSV file with at least 'walking_bpm' (and optionally 'session_id'), or
  - a directory containing session_data.csv files, or
  - a user name, in which case it will look under server/logs/<user_name>.

Usage:
    python train_user_head.py --path path/to/user.csv|user_dir [--base-model ...] [--suffix user123]
    python train_user_head.py --user "Sonic wesh wesh" [--base-model ...] [--suffix user123]
"""
import argparse
from pathlib import Path

import pandas as pd

from train_lgbm import (
    train_user_calibration,
    BASE_DIR,
)

# Import load_all_sessions and _read_session from local analyze_data.py
from analyze_data import load_all_sessions, _read_session


def _load_sessions_from_file(filepath: str) -> list[str]:
    """Load session paths from a file (one path per line)."""
    paths = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and Path(line).exists():
                paths.append(line)
    return paths


def main():
    parser = argparse.ArgumentParser(description="Train per-user calibration head for LightGBM.")
    parser.add_argument(
        "--path",
        help="Path to user CSV or directory containing session_data.csv files.",
    )
    parser.add_argument(
        "--user",
        help="User name; looks under server/logs/<user> for session_data.csv files.",
    )
    parser.add_argument(
        "--sessions",
        nargs="+",
        default=None,
        help="Specific session CSV paths to train on.",
    )
    parser.add_argument(
        "--sessions-file",
        type=str,
        default=None,
        help="Path to a file containing session CSV paths (one per line).",
    )
    parser.add_argument(
        "--base-model",
        default=str(Path(__file__).parent / "results" / "models" / "lgbm_model.joblib"),
        help="Path to base LightGBM model artifact (joblib).",
    )
    parser.add_argument("--suffix", default="user", help="Identifier suffix for the saved head file.")
    args = parser.parse_args()

    # Load sessions from file if specified
    session_paths = args.sessions
    if args.sessions_file:
        session_paths = _load_sessions_from_file(args.sessions_file)
        print(f"Loaded {len(session_paths)} session paths from file.")

    # Load data from specified sources
    if session_paths:
        # Load specific session CSVs using _read_session to properly parse metadata
        print(f"Loading {len(session_paths)} specified session(s)...")
        dfs = []
        for csv_path in session_paths:
            if Path(csv_path).exists():
                df_sess = _read_session(csv_path)
                if df_sess is not None:
                    dfs.append(df_sess)
        if not dfs:
            raise ValueError("No valid session files found.")
        df = pd.concat(dfs, ignore_index=True)
    elif args.user:
        user_path = BASE_DIR / "server" / "logs" / args.user
        if not user_path.exists():
            raise FileNotFoundError(f"User path not found: {user_path}")
        df = load_all_sessions(str(user_path))
    elif args.path:
        user_path = Path(args.path)
        if not user_path.exists():
            raise FileNotFoundError(f"Path not found: {user_path}")
        if user_path.is_dir():
            df = load_all_sessions(str(user_path))
        else:
            df = pd.read_csv(user_path)
            if "session_id" not in df.columns:
                df["session_id"] = "user_session"
    else:
        raise ValueError("Provide --sessions, --path, or --user.")

    if "walking_bpm" not in df.columns:
        raise ValueError("Data must contain 'walking_bpm' column.")

    print(f"Training user head on {len(df)} data points from {df['session_id'].nunique()} session(s).")

    # train_user_calibration internally calls process_walking_data which handles filtering
    calibrator, head_path = train_user_calibration(
        df,
        base_model_path=Path(args.base_model),
        output_suffix=args.suffix,
    )
    print(f"Saved user head: {head_path}")


if __name__ == "__main__":
    main()

