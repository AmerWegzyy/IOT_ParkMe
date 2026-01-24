"""
LightGBM Training Module

Trains a LightGBM regressor to predict the next walking BPM from lag
features (one-step-ahead forecast).

Outputs:
    - results/plots/lgbm_fast_performance.png (fast preset)
    - results/plots/lgbm_deep_performance.png (deep preset)
    - results/models/lgbm_model.joblib (best of the two)
"""
import argparse
import importlib.util
import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Any
import pandas as pd

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from analyze_data import analyze_bpm_distribution

try:
    import lightgbm as lgb
except ImportError as exc:  # pragma: no cover
    raise SystemExit("LightGBM is not installed. Please run run_lgbm.bat to install dependencies.") from exc

if TYPE_CHECKING:  # pragma: no cover
    import optuna  # type: ignore

# Load the shared loader from research/analyze_data.py without clashing with this module's name.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = PROJECT_ROOT
RESEARCH_DIR = PROJECT_ROOT / "research"
PARENT_ANALYZE = RESEARCH_DIR / "analyze_data.py"
spec = importlib.util.spec_from_file_location("research_analyze_data", PARENT_ANALYZE)
parent_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent_mod)  # type: ignore

# Load LightGBM analysis helpers from this directory without clashing names.
LGBM_ANALYZE = Path(__file__).parent / "analyze_data.py"
spec_lgbm = importlib.util.spec_from_file_location("lgbm_analyze_data", LGBM_ANALYZE)
lgbm_analyze = importlib.util.module_from_spec(spec_lgbm)
spec_lgbm.loader.exec_module(lgbm_analyze)  # type: ignore
prepare_training_dataset = lgbm_analyze.prepare_training_dataset
build_lag_features = lgbm_analyze.build_lag_features

# Import filtering separately from dedicated module
from data_filtering import DataFiltering

# Output directories for results
RESULTS_DIR = Path(__file__).parent / "results"
PLOTS_DIR = RESULTS_DIR / "plots"
MODELS_DIR = RESULTS_DIR / "models"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_WINDOW_SIZE = 4  # Default lag window (Optuna can tune this)
TEST_SIZE = 0.2
RANDOM_SEED = 42
DEFAULT_OPTUNA_TRIALS = 30

# Two parameter presets to compare - the best one is automatically selected
PRESET_FAST = dict(
    objective="regression",
    n_estimators=200,
    learning_rate=0.1,
    max_depth=5,
    num_leaves=31,
    subsample=0.9,
    colsample_bytree=0.9,
    min_child_samples=15,
    random_state=RANDOM_SEED,
    verbose=-1,  # Suppress warnings
)

PRESET_DEEP = dict(
    objective="regression",
    n_estimators=300,
    learning_rate=0.07,
    max_depth=6,
    num_leaves=31,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_samples=10,
    random_state=RANDOM_SEED,
    verbose=-1,  # Suppress warnings
)


def _prepare_dataset(session_paths: list[str] | None = None, window_size: int = DEFAULT_WINDOW_SIZE):
    """
    Wrapper for prepare_training_dataset from analyze_data.py.
    
    Args:
        session_paths: Optional list of specific session CSV paths to use.
                      If None, loads all sessions from server/logs/.
        window_size: Number of lag steps for feature engineering.
    
    Returns:
        Tuple of (X_train, X_test, y_train, y_test, scaler, meta_mappings)
        or None if preparation fails.
    """
    return prepare_training_dataset(
        session_paths=session_paths,
        window_size=window_size,
        test_size=TEST_SIZE,
        random_seed=RANDOM_SEED
    )


def _plot_predictions(tag, y_true, preds, mae, r2, limit=200):
    plt.figure(figsize=(12, 5))
    plot_limit = min(limit, len(y_true))
    plt.plot(y_true[:plot_limit], label="Actual Next Step", marker="o", markersize=3)
    plt.plot(preds[:plot_limit], label="LGBM Prediction", linestyle="--", linewidth=2)
    r2_pct = r2 * 100
    plt.title(f"LGBM Prediction vs Actual - MAE: {mae:.2f} BPM, R2: {r2:.3f} ({r2_pct:.1f}%) [{tag}]")
    plt.xlabel("Step Index")
    plt.ylabel("BPM")
    plt.legend()
    plt.grid(True, alpha=0.3)
    output_path = PLOTS_DIR / f"lgbm_{tag}_performance.png"
    plt.savefig(output_path)
    plt.close()
    print(f"Saved '{output_path}'")


def _plot_training_history(tag, eval_results, metric="rmse"):
    """Plot training and validation loss curves over iterations."""
    if not eval_results or "valid_0" not in eval_results:
        return
    
    train_metric = eval_results.get("training", {}).get(metric, [])
    val_metric = eval_results.get("valid_0", {}).get(metric, [])
    
    if not train_metric and not val_metric:
        return
    
    plt.figure(figsize=(10, 6))
    iterations = range(1, len(train_metric) + 1) if train_metric else range(1, len(val_metric) + 1)
    
    if train_metric:
        plt.plot(iterations, train_metric, label=f"Training {metric.upper()}", linewidth=2)
    if val_metric:
        plt.plot(iterations, val_metric, label=f"Validation {metric.upper()}", linewidth=2, linestyle="--")
    
    plt.title(f"Learning Curve - {metric.upper()} over Iterations [{tag}]", fontsize=14)
    plt.xlabel("Boosting Iteration", fontsize=12)
    plt.ylabel(metric.upper(), fontsize=12)
    plt.legend(fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    output_path = PLOTS_DIR / f"lgbm_{tag}_learning_curve.png"
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Saved '{output_path}'")


def _plot_feature_importance(tag, model, feature_names=None, top_n=15):
    """Plot feature importance from trained LightGBM model."""
    try:
        importance = model.feature_importances_
        if feature_names is None:
            feature_names = [f"Feature {i}" for i in range(len(importance))]
        
        # Sort by importance
        indices = np.argsort(importance)[::-1][:top_n]
        top_importance = importance[indices]
        top_features = [feature_names[i] for i in indices]
        
        plt.figure(figsize=(10, 6))
        plt.barh(range(len(top_features)), top_importance, align="center")
        plt.yticks(range(len(top_features)), top_features)
        plt.xlabel("Feature Importance (Gain)", fontsize=12)
        plt.title(f"Top {top_n} Feature Importance [{tag}]", fontsize=14)
        plt.gca().invert_yaxis()
        plt.grid(True, alpha=0.3, axis="x")
        plt.tight_layout()
        
        output_path = PLOTS_DIR / f"lgbm_{tag}_feature_importance.png"
        plt.savefig(output_path, dpi=150)
        plt.close()
        print(f"Saved '{output_path}'")
    except Exception as e:
        print(f"Could not plot feature importance: {e}")


def _plot_optuna_history(study, tag="optuna"):
    """Plot Optuna optimization history and parameter importance."""
    try:
        import optuna.visualization as vis
        
        # Optimization history plot
        fig = vis.plot_optimization_history(study)
        output_path = PLOTS_DIR / f"lgbm_{tag}_optimization_history.png"
        fig.write_image(str(output_path))
        print(f"Saved '{output_path}'")
        
        # Parameter importance plot
        fig = vis.plot_param_importances(study)
        output_path = PLOTS_DIR / f"lgbm_{tag}_param_importance.png"
        fig.write_image(str(output_path))
        print(f"Saved '{output_path}'")
        
        # Parallel coordinate plot (top 10 trials)
        fig = vis.plot_parallel_coordinate(study)
        output_path = PLOTS_DIR / f"lgbm_{tag}_parallel_coordinate.png"
        fig.write_image(str(output_path))
        print(f"Saved '{output_path}'")
        
    except ImportError:
        print("Note: Install 'plotly' and 'kaleido' for Optuna visualization plots")
    except Exception as e:
        print(f"Could not generate Optuna plots: {e}")


def train_lgbm_model(session_paths: list[str] | None = None, optimize: bool = False, trials: int = DEFAULT_OPTUNA_TRIALS):
    """Train LightGBM model with preset comparison, optionally including Optuna optimization.
    
    Args:
        session_paths: Optional list of session CSV paths to train on.
        optimize: If True, also run Optuna hyperparameter optimization and compare.
        trials: Number of Optuna trials (only used if optimize=True).
    """
    # Generate distribution plots for data analysis
    print("\n[DATA ANALYSIS] Generating BPM distribution plots...")
    analyze_bpm_distribution(session_paths=session_paths)
    
    prepared = _prepare_dataset(session_paths)
    if prepared is None:
        return

    X_train, X_test, y_train, y_test, scaler, meta_mappings = prepared
    
    # Split training data for validation tracking
    X_train_fit, X_val_track, y_train_fit, y_val_track = train_test_split(
        X_train, y_train, test_size=0.15, random_state=RANDOM_SEED
    )
    
    # Generate feature names for visualization (preset models use DEFAULT_WINDOW_SIZE)
    feature_names = (
        [f"walk_lag_{i}" for i in range(DEFAULT_WINDOW_SIZE)] +
        [f"inst_lag_{i}" for i in range(DEFAULT_WINDOW_SIZE)] +
        ["smoothing_window", "stride", "run_type"]
    )

    def train_and_eval(params, tag):
        # Train with evaluation tracking
        eval_results = {}
        model = lgb.LGBMRegressor(**params)
        model.fit(
            X_train_fit, 
            y_train_fit,
            eval_set=[(X_train_fit, y_train_fit), (X_val_track, y_val_track)],
            eval_metric="rmse",
            eval_names=["training", "valid_0"],
            callbacks=[lgb.record_evaluation(eval_results)]
        )
        
        # Validation error diagnostics
        val_preds = model.predict(X_val_track)
        val_errors = np.abs(val_preds - y_val_track)
        val_rmse = np.sqrt(np.mean((val_preds - y_val_track) ** 2))
        val_mae = val_errors.mean()
        
        print(f"\n      [{tag}] Validation Error Analysis:")
        print(f"         Samples: {len(y_val_track)}")
        print(f"         MAE: {val_mae:.2f} BPM")
        print(f"         RMSE: {val_rmse:.2f} BPM")
        print(f"         Median error: {np.median(val_errors):.2f} BPM")
        print(f"         90th percentile: {np.percentile(val_errors, 90):.2f} BPM")
        print(f"         95th percentile: {np.percentile(val_errors, 95):.2f} BPM")
        print(f"         Max error: {val_errors.max():.2f} BPM")
        print(f"         Errors >50 BPM: {(val_errors > 50).sum()} ({100*(val_errors > 50).sum()/len(val_errors):.1f}%)")
        print(f"         Errors >30 BPM: {(val_errors > 30).sum()} ({100*(val_errors > 30).sum()/len(val_errors):.1f}%)")
        print(f"         RMSE/MAE ratio: {val_rmse/val_mae:.2f} (ideal: ~1.25)")
        
        # Evaluate on held-out test set
        preds = model.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        r2 = r2_score(y_test, preds)
        
        print(f"      [{tag}] Test: MAE={mae:.3f}, R2={r2:.3f}")
        
        # Generate convergence visualizations
        _plot_training_history(tag, eval_results, metric="rmse")
        _plot_feature_importance(tag, model, feature_names=feature_names)
        
        return model, preds, mae, r2, tag

    # Train preset models
    print("\n[1/3] Training Fast preset...")
    fast_model, fast_preds, fast_mae, fast_r2, fast_tag = train_and_eval(PRESET_FAST, "fast")
    print(f"      Fast: MAE={fast_mae:.3f}, R2={fast_r2:.3f}")
    
    print("[2/3] Training Deep preset...")
    deep_model, deep_preds, deep_mae, deep_r2, deep_tag = train_and_eval(PRESET_DEEP, "deep")
    print(f"      Deep: MAE={deep_mae:.3f}, R2={deep_r2:.3f}")

    # Collect all candidates
    candidates = [
        (fast_model, fast_preds, fast_mae, fast_r2, "fast", PRESET_FAST),
        (deep_model, deep_preds, deep_mae, deep_r2, "deep", PRESET_DEEP),
    ]

    # Optionally run Optuna optimization
    optuna_params = None
    best_window_size = DEFAULT_WINDOW_SIZE  # Track the best window_size found
    if optimize:
        print(f"[3/3] Running Optuna optimization ({trials} trials)...")
        print("      Note: Optuna will tune BOTH model parameters AND window_size!")
        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)

            def objective(trial: optuna.Trial) -> float:
                # FEATURE ENGINEERING HYPERPARAMETER: window_size
                trial_window_size = trial.suggest_int("window_size", 2, 8)
                
                # Regenerate dataset with this trial's window_size
                trial_prepared = _prepare_dataset(session_paths, window_size=trial_window_size)
                if trial_prepared is None:
                    return float('inf')  # Invalid configuration
                
                X_train_trial, X_test_trial, y_train_trial, y_test_trial, scaler_trial, _ = trial_prepared
                
                # Split for validation
                X_train_opt, X_val_opt, y_train_opt, y_val_opt = train_test_split(
                    X_train_trial, y_train_trial, test_size=0.2, random_state=RANDOM_SEED
                )
                
                # MODEL HYPERPARAMETERS
                max_depth = trial.suggest_int("max_depth", 3, 10)
                params = dict(
                    objective="regression",
                    boosting_type="gbdt",
                    learning_rate=trial.suggest_float("learning_rate", 1e-3, 0.2, log=True),
                    n_estimators=trial.suggest_int("n_estimators", 200, 800),
                    max_depth=max_depth,
                    num_leaves=trial.suggest_int("num_leaves", 16, min(512, 2 ** (max_depth + 1))),
                    subsample=trial.suggest_float("subsample", 0.6, 1.0),
                    colsample_bytree=trial.suggest_float("colsample_bytree", 0.6, 1.0),
                    min_child_samples=trial.suggest_int("min_child_samples", 5, 60),
                    lambda_l1=trial.suggest_float("lambda_l1", 0.0, 5.0),
                    lambda_l2=trial.suggest_float("lambda_l2", 0.0, 5.0),
                    random_state=RANDOM_SEED,
                    verbose=-1,
                )
                model = lgb.LGBMRegressor(**params)
                model.fit(X_train_opt, y_train_opt)
                preds = model.predict(X_val_opt)
                return float(np.sqrt(mean_squared_error(y_val_opt, preds)))

            study = optuna.create_study(direction="minimize")
            study.optimize(objective, n_trials=trials, show_progress_bar=True)

            # Visualize optimization process
            print("      Generating Optuna visualization plots...")
            _plot_optuna_history(study, tag="optuna")

            # Extract best window_size from Optuna
            best_window_size = study.best_trial.params.get("window_size", DEFAULT_WINDOW_SIZE)
            print(f"\n      Best window_size found by Optuna: {best_window_size}")
            
            # Regenerate dataset with best window_size for final model training
            print(f"      Regenerating dataset with window_size={best_window_size}...")
            optuna_prepared = _prepare_dataset(session_paths, window_size=best_window_size)
            if optuna_prepared is None:
                print("      Failed to prepare dataset with best window_size - skipping Optuna model")
            else:
                X_train_opt, X_test_opt, y_train_opt, y_test_opt, scaler_opt, meta_mappings_opt = optuna_prepared
                
                # Split for validation tracking
                X_train_fit_opt, X_val_track_opt, y_train_fit_opt, y_val_track_opt = train_test_split(
                    X_train_opt, y_train_opt, test_size=0.15, random_state=RANDOM_SEED
                )
                
                # Generate dynamic feature names based on window_size
                optuna_feature_names = (
                    [f"walk_lag_{i}" for i in range(best_window_size)] +
                    [f"inst_lag_{i}" for i in range(best_window_size)] +
                    ["smoothing_window", "stride", "run_type"]
                )
                
                # Extract model hyperparameters (exclude window_size which is a feature engineering param)
                model_params = {k: v for k, v in study.best_trial.params.items() if k != "window_size"}
                optuna_params = dict(
                    objective="regression",
                    boosting_type="gbdt",
                    random_state=RANDOM_SEED,
                    verbose=-1,
                    **model_params,
                )
                
                # Train with evaluation tracking for convergence plot
                optuna_eval_results = {}
                optuna_model = lgb.LGBMRegressor(**optuna_params)
                optuna_model.fit(
                    X_train_fit_opt,
                    y_train_fit_opt,
                    eval_set=[(X_train_fit_opt, y_train_fit_opt), (X_val_track_opt, y_val_track_opt)],
                    eval_metric="rmse",
                    eval_names=["training", "valid_0"],
                    callbacks=[lgb.record_evaluation(optuna_eval_results)]
                )
                
                # Validation error diagnostics
                val_preds = optuna_model.predict(X_val_track_opt)
                val_errors = np.abs(val_preds - y_val_track_opt)
                val_rmse = np.sqrt(np.mean((val_preds - y_val_track_opt) ** 2))
                val_mae = val_errors.mean()
                
                print(f"\n      [optuna] Validation Error Analysis:")
                print(f"         Samples: {len(y_val_track_opt)}")
                print(f"         MAE: {val_mae:.2f} BPM")
                print(f"         RMSE: {val_rmse:.2f} BPM")
                print(f"         Median error: {np.median(val_errors):.2f} BPM")
                print(f"         90th percentile: {np.percentile(val_errors, 90):.2f} BPM")
                print(f"         95th percentile: {np.percentile(val_errors, 95):.2f} BPM")
                print(f"         Max error: {val_errors.max():.2f} BPM")
                print(f"         Errors >50 BPM: {(val_errors > 50).sum()} ({100*(val_errors > 50).sum()/len(val_errors):.1f}%)")
                print(f"         Errors >30 BPM: {(val_errors > 30).sum()} ({100*(val_errors > 30).sum()/len(val_errors):.1f}%)")
                print(f"         RMSE/MAE ratio: {val_rmse/val_mae:.2f} (ideal: ~1.25)")
                
                optuna_preds = optuna_model.predict(X_test_opt)
                optuna_mae = mean_absolute_error(y_test_opt, optuna_preds)
                optuna_r2 = r2_score(y_test_opt, optuna_preds)
                
                print(f"      [optuna] Test: MAE={optuna_mae:.3f}, R2={optuna_r2:.3f} (best trial: {study.best_trial.number})")
                
                # Generate convergence visualizations for Optuna model
                _plot_training_history("optuna", optuna_eval_results, metric="rmse")
                _plot_feature_importance("optuna", optuna_model, feature_names=optuna_feature_names)
                
                candidates.append((optuna_model, optuna_preds, optuna_mae, optuna_r2, "optuna", optuna_params))
            
        except ImportError:
            print("      Optuna not installed - skipping optimization")
        except Exception as e:
            print(f"      Optuna optimization failed: {e}")

    # Select best model based on R2 (higher is better), then MAE as tiebreaker
    best_model, best_preds, best_mae, best_r2, best_tag, best_params = max(
        candidates, key=lambda x: (x[3], -x[2])  # max R2, min MAE
    )

    # Print comparison
    print("\n" + "=" * 50)
    print("MODEL COMPARISON (same test set):")
    print("=" * 50)
    for _, _, mae, r2, tag, _ in candidates:
        marker = " ** BEST **" if tag == best_tag else ""
        print(f"  {tag:8s} - MAE: {mae:.3f}, R2: {r2:.3f}{marker}")
    print("=" * 50)

    # Plot all candidates (note: Optuna uses different test set if window_size differs)
    for _, preds, mae, r2, tag, _ in candidates:
        if tag == "optuna":
            # Optuna might use different window_size, so skip plotting if incompatible
            continue
        _plot_predictions(tag, y_test, preds, mae, r2)

    # Determine the window_size used by the best model
    final_window_size = best_window_size if best_tag == "optuna" else DEFAULT_WINDOW_SIZE
    
    # Build artifact
    artifact = {
        "model": best_model,
        "scaler": scaler,
        "window_size": final_window_size,
        "params": {
            "selected": best_tag,
            "fast": PRESET_FAST,
            "deep": PRESET_DEEP,
        },
        "feature_schema": {
            "lags": {
                "walking": final_window_size,
                "instant": final_window_size,
            },
            "extra": ["smoothing_window", "stride", "run_type"],
            "run_type_mapping": meta_mappings.get("run_type") if meta_mappings else None,
            "order": ([f"walk_lag_{i}" for i in range(final_window_size)] +
                      [f"inst_lag_{i}" for i in range(final_window_size)] +
                      ["smoothing_window", "stride", "run_type"]),
        },
    }
    
    # Add optuna params if used
    if optuna_params and best_tag == "optuna":
        artifact["params"]["optuna"] = optuna_params
        artifact["params"]["optuna_best_window_size"] = best_window_size

    model_path = MODELS_DIR / "lgbm_model.joblib"
    joblib.dump(artifact, model_path)
    print(f"\nModel exported to '{model_path}' (selected: {best_tag})")
    
    if len(X_test) > 0:
        example_input = X_test[0].tolist()
        example_prediction = best_preds[0]
        print(f"Example: input {example_input[:4]}... -> predicted {example_prediction:.1f} BPM")

    return best_model, model_path


def optimize_lgbm_model(trials: int = DEFAULT_OPTUNA_TRIALS, timeout: Optional[int] = None):
    try:
        import optuna  # type: ignore
    except ImportError:  # pragma: no cover
        raise SystemExit("Optuna is not installed. Re-run with run_lgbm.bat --optimize to install dependencies.")

    prepared = prepare_training_dataset(
        session_paths=None,
        window_size=DEFAULT_WINDOW_SIZE,
        test_size=TEST_SIZE,
        random_seed=RANDOM_SEED
    )
    if prepared is None:
        return

    X_train, X_test, y_train, y_test, scaler, meta_mappings = prepared
    X_train_opt, X_val_opt, y_train_opt, y_val_opt = train_test_split(
        X_train, y_train, test_size=0.2, random_state=RANDOM_SEED
    )

    def objective(trial: optuna.Trial) -> float:
        max_depth = trial.suggest_int("max_depth", 3, 10)
        params = dict(
            objective="regression",
            boosting_type="gbdt",
            learning_rate=trial.suggest_float("learning_rate", 1e-3, 0.2, log=True),
            n_estimators=trial.suggest_int("n_estimators", 200, 800),
            max_depth=max_depth,
            num_leaves=trial.suggest_int("num_leaves", 16, min(512, 2 ** (max_depth + 1))),
            subsample=trial.suggest_float("subsample", 0.6, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.6, 1.0),
            min_child_samples=trial.suggest_int("min_child_samples", 5, 60),
            lambda_l1=trial.suggest_float("lambda_l1", 0.0, 5.0),
            lambda_l2=trial.suggest_float("lambda_l2", 0.0, 5.0),
            min_split_gain=trial.suggest_float("min_split_gain", 0.0, 1.0),
            bagging_freq=trial.suggest_int("bagging_freq", 0, 7),
            random_state=RANDOM_SEED,
            n_jobs=-1,
            verbosity=-1,
        )

        model = lgb.LGBMRegressor(**params)
        model.fit(
            X_train_opt,
            y_train_opt,
            eval_set=[(X_val_opt, y_val_opt)],
            eval_metric="rmse",
            callbacks=[lgb.early_stopping(stopping_rounds=50, verbose=False)],
        )
        preds = model.predict(X_val_opt)
        rmse = float(np.sqrt(mean_squared_error(y_val_opt, preds)))
        return rmse

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=trials, timeout=timeout, show_progress_bar=True)

    # Visualize optimization process
    print("\nGenerating Optuna visualization plots...")
    _plot_optuna_history(study, tag="optuna_standalone")

    print(f"\nBest trial: {study.best_trial.number}")
    print(f"Best RMSE: {study.best_trial.value:.4f}")
    print("Best parameters:")
    for k, v in study.best_trial.params.items():
        print(f"  {k}: {v}")

    best_params = study.best_trial.params
    best_params_full = dict(
        objective="regression",
        boosting_type="gbdt",
        n_jobs=-1,
        random_state=RANDOM_SEED,
        verbosity=-1,
        **best_params,
    )

    X_train_fit, X_val_fit, y_train_fit, y_val_fit = train_test_split(
        X_train, y_train, test_size=0.2, random_state=RANDOM_SEED
    )
    
    # Generate feature names for visualization
    feature_names = (
        [f"walk_lag_{i}" for i in range(DEFAULT_WINDOW_SIZE)] +
        [f"inst_lag_{i}" for i in range(DEFAULT_WINDOW_SIZE)] +
        ["smoothing_window", "stride", "run_type"]
    )
    
    # Train with evaluation tracking
    optuna_eval_results = {}
    best_model = lgb.LGBMRegressor(**best_params_full)
    best_model.fit(
        X_train_fit,
        y_train_fit,
        eval_set=[(X_train_fit, y_train_fit), (X_val_fit, y_val_fit)],
        eval_metric="rmse",
        eval_names=["training", "valid_0"],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.record_evaluation(optuna_eval_results)
        ],
    )

    best_preds = best_model.predict(X_test)
    best_mae = mean_absolute_error(y_test, best_preds)
    best_r2 = r2_score(y_test, best_preds)
    best_rmse = float(np.sqrt(mean_squared_error(y_test, best_preds)))

    print("\nOptuna-optimized model performance (held-out test):")
    print(f"  RMSE: {best_rmse:.3f}")
    print(f"  MAE : {best_mae:.3f}")
    print(f"  R2  : {best_r2:.3f}")

    # Generate all visualization plots
    _plot_predictions("optuna", y_test, best_preds, best_mae, best_r2)
    _plot_training_history("optuna_standalone", optuna_eval_results, metric="rmse")
    _plot_feature_importance("optuna_standalone", best_model, feature_names=feature_names)

    artifact = {
        "model": best_model,
        "scaler": scaler,
        "window_size": DEFAULT_WINDOW_SIZE,
        "params": {
            "selected": "optuna",
            "optuna_best": best_params_full,
            "trials": trials,
            "best_trial": study.best_trial.number,
            "best_rmse": best_rmse,
        },
        "feature_schema": {
            "lags": {
                "walking": DEFAULT_WINDOW_SIZE,
                "instant": DEFAULT_WINDOW_SIZE,
            },
            "extra": ["smoothing_window", "stride", "run_type"],
            "run_type_mapping": meta_mappings.get("run_type") if meta_mappings else None,
            "order": ([f"walk_lag_{i}" for i in range(DEFAULT_WINDOW_SIZE)] +
                      [f"inst_lag_{i}" for i in range(DEFAULT_WINDOW_SIZE)] +
                      ["smoothing_window", "stride", "run_type"]),
        },
    }
    model_path = MODELS_DIR / "lgbm_model.joblib"
    joblib.dump(artifact, model_path)
    print(f"Model exported to '{model_path}'")

    params_path = MODELS_DIR / "lgbm_optuna_best_params.json"
    with params_path.open("w", encoding="utf-8") as fh:
        json.dump(best_params_full, fh, indent=2)
    print(f"Best parameters exported to '{params_path}'")

    if len(X_test) > 0:
        example_input = X_test[0].tolist()
        example_prediction = best_preds[0]
        print(f"Example: input {example_input} -> predicted {example_prediction:.1f} BPM")

    return best_model, model_path


def train_user_calibration(user_df, base_model_path=None, output_suffix="user_head"):
    """
    Fit a lightweight per-user linear calibration head on top of the base LightGBM predictions.

    Args:
        user_df: DataFrame containing user data with walking_bpm and session_id.
        base_model_path: Path to base LightGBM artifact (joblib). Defaults to latest lgbm_model.joblib.
        output_suffix: Identifier to distinguish the saved head artifact.

    Returns:
        calibrator (Ridge), artifact_path
    """
    if base_model_path is None:
        base_model_path = MODELS_DIR / "lgbm_model.joblib"
    if not Path(base_model_path).exists():
        raise FileNotFoundError(f"Base model not found at {base_model_path}")

    # Load base artifact
    artifact = joblib.load(base_model_path)
    base_model = artifact["model"]
    scaler = artifact["scaler"]
    window_size = artifact["window_size"]

    # Filter outliers for stability
    data_filter = DataFiltering()
    user_df = data_filter.process_walking_data(user_df)
    if user_df.empty:
        raise ValueError("No valid user data after filtering.")

    # Build lag features
    X_lag, y, meta, _ = build_lag_features(user_df, window_size=window_size)
    if len(X_lag) < 10:
        raise ValueError(f"Not enough user sequences to fit calibration head (found {len(X_lag)}).")
    X = np.concatenate([X_lag, meta], axis=1) if len(meta) > 0 else X_lag

    # Scale lags with the base scaler
    X_scaled = scaler.transform(X)

    # Base predictions
    base_preds = base_model.predict(X_scaled)

    # Calibration features: base prediction plus scaled lags
    calib_features = np.column_stack([base_preds, X_scaled])

    # Split for a quick validation (optional)
    X_train, X_val, y_train, y_val = train_test_split(
        calib_features, y, test_size=0.2, random_state=RANDOM_SEED
    )

    calibrator = Ridge(alpha=1.0, random_state=RANDOM_SEED)
    calibrator.fit(X_train, y_train)

    val_preds = calibrator.predict(X_val)
    val_mae = mean_absolute_error(y_val, val_preds)
    val_r2 = r2_score(y_val, val_preds)
    print("\nUser calibration head")
    print("-" * 40)
    print(f"Val MAE: {val_mae:.2f} BPM")
    print(f"Val R2 : {val_r2:.3f}")

    head_artifact = {
        "calibrator": calibrator,
        "base_model_path": str(base_model_path),
        "window_size": window_size,
        "params": {"alpha": 1.0},
    }
    head_path = MODELS_DIR / f"lgbm_user_head_{output_suffix}.joblib"
    joblib.dump(head_artifact, head_path)
    print(f"User head exported to '{head_path}'")

    return calibrator, head_path


def _parse_args():
    parser = argparse.ArgumentParser(description="Train or tune the LightGBM model.")
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run Optuna hyperparameter search instead of fixed presets.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=DEFAULT_OPTUNA_TRIALS,
        help=f"Number of Optuna trials (default: {DEFAULT_OPTUNA_TRIALS}).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Optional Optuna timeout in seconds.",
    )
    parser.add_argument(
        "--sessions",
        nargs="+",
        default=None,
        help="Specific session CSV paths to train on. If omitted, uses all sessions.",
    )
    parser.add_argument(
        "--sessions-file",
        type=str,
        default=None,
        help="Path to a file containing session CSV paths (one per line). Alternative to --sessions for many paths.",
    )
    parser.add_argument(
        "--augment",
        action="store_true",
        help="Use data augmentation (generates synthetic training data for larger dataset).",
    )
    return parser.parse_args()


def _load_sessions_from_file(filepath: str) -> list[str]:
    """Load session paths from a file (one path per line)."""
    paths = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and Path(line).exists():
                paths.append(line)
    return paths


if __name__ == "__main__":
    args = _parse_args()
    
    # Generate augmented data if requested
    if args.augment:
        try:
            from data_augmentation import generate_augmented_data
            logs_dir = BASE_DIR / "server" / "logs"
            aug_dir, num_generated = generate_augmented_data(
                logs_dir,
                enable=True,
                clean_existing=True,
                verbose=True
            )
            print(f"\n[AUGMENTATION] Ready to train with augmented data (+{num_generated} synthetic sessions)\n")
        except Exception as e:
            print(f"WARNING: Data augmentation failed: {e}")
            print("Continuing with original data only...\n")
    
    # Determine session paths from either --sessions or --sessions-file
    session_paths = args.sessions
    if args.sessions_file:
        session_paths = _load_sessions_from_file(args.sessions_file)
        print(f"Loaded {len(session_paths)} session paths from file.")
    
    # Train with optional Optuna optimization
    train_lgbm_model(
        session_paths=session_paths,
        optimize=args.optimize,
        trials=args.trials,
    )

