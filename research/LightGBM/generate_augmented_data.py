"""
Command-line tool for generating augmented training data.

Usage:
    python generate_augmented_data.py                          # Augment all sessions
    python generate_augmented_data.py --user Default           # Augment specific user
    python generate_augmented_data.py --sessions session1.csv session2.csv  # Augment specific sessions
"""
import argparse
import sys
from pathlib import Path
from data_augmentation import generate_augmented_data, BPMDataAugmentor

# Get project root
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))


def augment_all_sessions(logs_dir: Path, verbose: bool = True):
    """Generate augmented data for all sessions."""
    aug_dir, num_generated = generate_augmented_data(
        logs_dir,
        enable=True,
        clean_existing=True,
        verbose=verbose
    )
    return aug_dir, num_generated


def augment_user_folder(logs_dir: Path, user_folder: str, verbose: bool = True):
    """Generate augmented data for a specific user folder."""
    user_dir = logs_dir / user_folder
    if not user_dir.exists() or not user_dir.is_dir():
        print(f"ERROR: User folder '{user_folder}' not found in {logs_dir}")
        return None, 0
    
    output_dir = logs_dir / "Augmented"
    
    # Clean existing augmented data for this user
    user_aug_dir = output_dir / user_folder
    if user_aug_dir.exists():
        if verbose:
            print(f"[AUGMENTATION] Cleaning existing augmented data for {user_folder}...")
        import shutil
        try:
            shutil.rmtree(user_aug_dir)
        except Exception as e:
            print(f"   WARNING: Could not clean {user_aug_dir}: {e}")
    
    augmentor = BPMDataAugmentor()
    
    if verbose:
        print(f"[AUGMENTATION] Generating synthetic data for user: {user_folder}")
        print(f"   Source: {user_dir}")
        print(f"   Output: {output_dir}")
        print(f"   Strategies:")
        print(f"     - Time warp: {augmentor.time_warp_factors}")
        print(f"     - Gaussian noise: std={augmentor.noise_std} BPM")
        if augmentor.enable_parameter_augmentation:
            print(f"     - Parameter variants: stride={augmentor.stride_variants}, smoothing={augmentor.smoothing_variants}")
    
    total_generated = 0
    processed_sessions = 0
    skipped_sessions = 0
    
    # Find all session CSVs in user directory
    for csv_path in sorted(user_dir.glob("session_*/session_data.csv")):
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
        print(f"   Processed: {processed_sessions} sessions from {user_folder}")
        print(f"   Generated: {total_generated} synthetic sessions")
        print(f"   Skipped: {skipped_sessions} (too short, <{augmentor.min_session_steps} steps)")
    
    return output_dir, total_generated


def augment_specific_sessions(logs_dir: Path, session_paths: list, verbose: bool = True):
    """Generate augmented data for specific session CSV files."""
    output_dir = logs_dir / "Augmented"
    
    augmentor = BPMDataAugmentor()
    
    if verbose:
        print(f"[AUGMENTATION] Generating synthetic data for {len(session_paths)} specific session(s)")
        print(f"   Output: {output_dir}")
        print(f"   Strategies:")
        print(f"     - Time warp: {augmentor.time_warp_factors}")
        print(f"     - Gaussian noise: std={augmentor.noise_std} BPM")
        if augmentor.enable_parameter_augmentation:
            print(f"     - Parameter variants: stride={augmentor.stride_variants}, smoothing={augmentor.smoothing_variants}")
    
    total_generated = 0
    processed_sessions = 0
    skipped_sessions = 0
    
    for session_path_str in session_paths:
        csv_path = Path(session_path_str)
        
        if not csv_path.exists():
            print(f"   WARNING: Session not found: {csv_path}")
            continue
        
        if not csv_path.name == "session_data.csv":
            print(f"   WARNING: Not a session_data.csv file: {csv_path}")
            continue
        
        processed_sessions += 1
        
        # Generate augmented versions
        aug_paths = augmentor.augment_session(csv_path, output_dir)
        
        if aug_paths:
            total_generated += len(aug_paths)
            if verbose:
                print(f"   ✓ {csv_path.parent.name}: {len(aug_paths)} variants")
        else:
            skipped_sessions += 1
            if verbose:
                print(f"   ✗ {csv_path.parent.name}: skipped (too short)")
    
    if verbose:
        print(f"[AUGMENTATION] Complete!")
        print(f"   Processed: {processed_sessions} sessions")
        print(f"   Generated: {total_generated} synthetic sessions")
        print(f"   Skipped: {skipped_sessions} (too short, <{augmentor.min_session_steps} steps)")
    
    return output_dir, total_generated


def main():
    parser = argparse.ArgumentParser(
        description="Generate augmented training data from real sessions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Augment all sessions
  python generate_augmented_data.py
  
  # Augment specific user folder
  python generate_augmented_data.py --user Default
  
  # Augment specific sessions
  python generate_augmented_data.py --sessions \\
      C:/path/to/session1/session_data.csv \\
      C:/path/to/session2/session_data.csv
  
  # Quiet mode (minimal output)
  python generate_augmented_data.py --quiet
        """
    )
    
    parser.add_argument(
        "--user",
        type=str,
        help="Specific user folder to augment (e.g., 'Default', 'Eitan')"
    )
    
    parser.add_argument(
        "--sessions",
        nargs="+",
        help="Specific session CSV paths to augment"
    )
    
    parser.add_argument(
        "--logs-dir",
        type=str,
        default=None,
        help="Path to logs directory (default: server/logs)"
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output (quiet mode)"
    )
    
    args = parser.parse_args()
    
    # Determine logs directory
    if args.logs_dir:
        logs_dir = Path(args.logs_dir)
    else:
        logs_dir = BASE_DIR / "server" / "logs"
    
    if not logs_dir.exists():
        print(f"ERROR: Logs directory not found: {logs_dir}")
        sys.exit(1)
    
    verbose = not args.quiet
    
    # Determine augmentation mode
    if args.sessions:
        # Augment specific sessions
        aug_dir, num_generated = augment_specific_sessions(logs_dir, args.sessions, verbose)
    elif args.user:
        # Augment specific user folder
        aug_dir, num_generated = augment_user_folder(logs_dir, args.user, verbose)
    else:
        # Augment all sessions
        aug_dir, num_generated = augment_all_sessions(logs_dir, verbose)
    
    if verbose:
        print(f"\n{'=' * 60}")
        print(f"Augmentation complete: {num_generated} synthetic sessions generated")
        print(f"Output location: {aug_dir}")
        print(f"{'=' * 60}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
