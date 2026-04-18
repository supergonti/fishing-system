@echo off
chcp 65001 > nul
echo ============================================
echo  室戸沖 釣果データ解析ソフト v2.0
echo ============================================
echo.

cd /d "%~dp0"
echo 実行フォルダ: %CD%
echo.

:: ── Python の存在確認 ──────────────────────────
set PYTHON_CMD=
where python >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON_CMD=python
    goto :python_found
)
where py >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON_CMD=py
    goto :python_found
)
where python3 >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON_CMD=python3
    goto :python_found
)

echo *** エラー: Python が見つかりません ***
echo.
echo 解決方法:
echo   1. https://www.python.org/downloads/ から Python をインストール
echo   2. インストール時に「Add Python to PATH」に必ずチェック
echo   3. PCを再起動してから再度実行
echo.
pause
exit /b 1

:python_found
echo Python コマンド: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

:: ── CSVファイルの存在確認 ──────────────────────
echo CSVファイルを確認中...
if not exist "fishing_muroto_v2_filtered.csv" (
    echo *** エラー: fishing_muroto_v2_filtered.csv が見つかりません ***
    echo このフォルダに以下の3ファイルを配置してください:
    echo   fishing_muroto_v2_filtered.csv
    echo   fishing_condition_db.csv
    echo   muroto_offshore_current_all.csv
    pause
    exit /b 1
)
if not exist "fishing_condition_db.csv" (
    echo *** エラー: fishing_condition_db.csv が見つかりません ***
    pause
    exit /b 1
)
if not exist "muroto_offshore_current_all.csv" (
    echo *** エラー: muroto_offshore_current_all.csv が見つかりません ***
    pause
    exit /b 1
)
echo CSVファイル: OK
echo.

:: ── 解析実行 ───────────────────────────────────
echo [1/2] 解析データ生成中...
%PYTHON_CMD% analyze_engine.py
if errorlevel 1 (
    echo.
    echo *** エラーが発生しました（上記のメッセージを確認してください）***
    pause
    exit /b 1
)

:: ── ブラウザで開く ─────────────────────────────
echo.
echo [2/2] ブラウザで開いています...
if not exist "dashboard.html" (
    echo *** エラー: dashboard.html が生成されていません ***
    pause
    exit /b 1
)
start "" "%CD%\dashboard.html"

echo.
echo ============================================
echo  完了！ブラウザで dashboard.html が開きます。
echo  開かない場合は dashboard.html を
echo  直接ダブルクリックしてください。
echo ============================================
echo.
pause
