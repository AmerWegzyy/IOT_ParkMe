@echo off
:: ============================================
:: LightGBM User Calibration Head Runner
:: Trains a per-user linear head on top of the base LightGBM model
:: Usage:
::   run_lgbm_user_head.bat path\to\user.csv^|user_dir [suffix]
::   run_lgbm_user_head.bat "User Name" [suffix]   (looks under server\logs\User Name)
:: ============================================

title Brain-Music LightGBM User Head
cls

if "%~1"=="" (
    echo Usage: %~nx0 path\to\user.csv^|user_dir^|user_name [suffix]
    pause
    exit /b 1
)

set TARGET=%~1
set SUFFIX=%~2
if "%SUFFIX%"=="" (
    rem Default suffix: user name/path with spaces replaced by underscores
    set SUFFIX=%TARGET: =_%
)

:: Navigate to project root (three levels up from server\utils\prediction_model)
cd /d "%~dp0..\..\.."

:: Activate Virtual Environment
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    echo Virtual environment activated.
) else (
    echo Error: Virtual environment '.venv' not found.
    echo Please run 'setup_env.bat' first!
    pause
    exit /b 1
)

:: Ensure dependencies (LightGBM is already expected)
pip show lightgbm >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing LightGBM...
    pip install lightgbm
)

pip show scikit-learn >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing scikit-learn...
    pip install scikit-learn
)

:: Navigate to prediction_model folder
cd server\utils\prediction_model

echo.
echo [User Head] Training calibration head for %TARGET%
echo.
rem Decide whether TARGET looks like a path (contains \ or / or :)
set TARGET_IS_PATH=0
echo %TARGET% | findstr /R "[\\/:]" >nul && set TARGET_IS_PATH=1

if %TARGET_IS_PATH%==1 (
    python train_user_head.py --path "%TARGET%" --suffix "%SUFFIX%"
) else (
    python train_user_head.py --user "%TARGET%" --suffix "%SUFFIX%"
)
if %errorlevel% neq 0 (
    echo ERROR: train_user_head.py failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo   User Head Training Complete!
echo ========================================
echo.
echo Saved to server\utils\prediction_model\results\models\lgbm_user_head_%SUFFIX%.joblib
echo.

pause

