# Research Module

Experimental scripts for **Predictive BPM Estimation** using machine learning.

## Goal

Instead of reacting to steps *after* they happen, can we **predict** the user's next BPM based on their walking pattern? This would allow the music to anticipate tempo changes.

---

## 🚀 Current Model: LightGBM (Production)

**Location:** `research/LightGBM/`

### Features
- **Gradient Boosting** regressor for one-step-ahead BPM prediction
- **Lag features** from walking and music tempo history (window size: 4 steps)
- **Metadata features** (smoothing window, stride, run type)
- **Optuna hyperparameter optimization** (optional)
- **Comprehensive ML visualizations** (learning curves, feature importance, convergence plots)

### Training

**Quick Start:**
```bash
cd research/LightGBM
python train_lgbm.py
```

**With Hyperparameter Optimization:**
```bash
python train_lgbm.py --optimize --trials 50
```

**Training Specific Sessions:**
```bash
python train_lgbm.py --sessions path/to/session1.csv path/to/session2.csv
```

**User-Specific Calibration Head:**
```bash
python train_user_head.py --sessions path/to/user_sessions/*.csv --suffix "John_Doe"
```

### Visualization Outputs

**Standard Training Generates:**
- 📈 **Learning Curves** - Training/validation loss convergence over iterations
- 📊 **Feature Importance** - Which lag features matter most
- 📉 **Prediction vs. Actual** - Model accuracy on test set
- 📊 **BPM Distribution** - Data quality analysis (raw vs. processed)

**Optuna Optimization Adds:**
- 🔍 **Optimization History** - How hyperparameter search progressed
- 🎯 **Parameter Importance** - Which hyperparameters affected performance most
- 🌈 **Parallel Coordinate Plot** - Relationship between params and performance

**See full documentation:** [`LightGBM/VISUALIZATION_GUIDE.md`](LightGBM/VISUALIZATION_GUIDE.md)

### Model Performance
- **MAE:** ~2-3 BPM (typical)
- **R²:** ~0.90-0.95 (excellent)
- **Inference:** <1ms per prediction

### Output Files
```
research/LightGBM/results/
├── models/
│   ├── lgbm_model.joblib              # Base model (best of fast/deep/optuna)
│   ├── lgbm_user_head_*.joblib        # User-specific calibration heads
│   └── lgbm_optuna_best_params.json   # Hyperparameters (if optimized)
└── plots/
    ├── lgbm_fast_learning_curve.png
    ├── lgbm_fast_feature_importance.png
    ├── lgbm_fast_performance.png
    ├── lgbm_deep_learning_curve.png
    ├── lgbm_deep_feature_importance.png
    ├── lgbm_deep_performance.png
    ├── lgbm_optuna_learning_curve.png  (if --optimize)
    ├── lgbm_optuna_feature_importance.png  (if --optimize)
    ├── lgbm_optuna_performance.png  (if --optimize)
    ├── lgbm_optuna_optimization_history.png  (if --optimize)
    ├── lgbm_optuna_param_importance.png  (if --optimize)
    ├── lgbm_optuna_parallel_coordinate.png  (if --optimize)
    ├── lgbm_raw_bpm_distribution.png
    └── lgbm_processed_bpm_distribution.png
```

---

## 📚 Legacy Models (Archived)

### 1. `train_knn.py` - K-Nearest Neighbors (Baseline)
- Simple KNN regressor with sliding window
- Useful for benchmarking
- **Output:** `results/plots/knn_performance.png`

### 2. `analyze_data.py` - Data Exploration
- BPM distribution analysis
- Correlation plots
- **Output:** `results/plots/bpm_distribution.png`

---

## 🔬 Research Workflow

1. **Collect Data** - Run sessions through the GUI
2. **Analyze** - Check BPM distributions and data quality
3. **Train** - Run `train_lgbm.py` (with or without Optuna)
4. **Evaluate** - Review all generated plots (especially learning curves)
5. **Deploy** - Trained model is automatically available in GUI's "Prediction Model" dropdown
6. **Iterate** - Collect more data, retrain, compare

---

## 📊 Understanding Your Results

### ✅ Excellent Model
- Learning curves converge with small gap
- MAE < 3 BPM, R² > 0.90
- Recent walking lags (walk_lag_0, walk_lag_1) have highest feature importance
- Predictions closely track actuals on test set

### ⚠️ Overfitting
- Training loss decreases but validation loss increases
- Large gap between learning curves
- **Fix:** Reduce `n_estimators`, increase regularization

### ⚠️ Underfitting
- Both training and validation loss are high and flat
- R² < 0.70
- **Fix:** Increase `n_estimators`, `max_depth`, or `num_leaves`

### ⚠️ Need More Data
- High variance in validation loss
- Few samples after filtering
- **Fix:** Collect more walking sessions

---

## 🛠️ Dependencies

Install all ML dependencies:
```bash
pip install -r requirements.txt
```

**Core Libraries:**
- `lightgbm` - Gradient boosting framework
- `optuna` - Hyperparameter optimization
- `plotly`, `kaleido` - Interactive visualization exports
- `scikit-learn` - Preprocessing and metrics
- `pandas`, `numpy`, `matplotlib` - Data processing and plotting

---

## 🎯 Next Steps

- [x] Comprehensive training convergence visualizations
- [x] Optuna hyperparameter optimization with visualization
- [x] Feature importance analysis
- [x] User-specific calibration heads
- [ ] Cross-validation for more robust evaluation
- [ ] Ensemble models (LightGBM + XGBoost)
- [ ] Real-time prediction benchmarking
- [ ] A/B testing framework for model comparison
