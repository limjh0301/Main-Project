@echo off
chcp 65001 >nul
title 국회 요구자료 목록화 시스템
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치한 뒤 다시 실행해 주세요.
    echo 설치 시 "Add Python to PATH" 옵션을 반드시 체크하세요.
    pause
    exit /b 1
)

if not exist .venv (
    echo [준비] 처음 실행이므로 가상환경을 만들고 패키지를 설치합니다. 잠시만 기다려 주세요...
    python -m venv .venv
    .venv\Scripts\python -m pip install --upgrade pip -q
    .venv\Scripts\pip install -r requirements.txt -q
)

echo.
echo  국회 요구자료 목록화 시스템을 시작합니다.
echo  잠시 후 브라우저가 자동으로 열립니다. (주소: http://127.0.0.1:5000)
echo  이 창을 닫으면 프로그램이 종료됩니다.
echo.
.venv\Scripts\python app.py
pause
