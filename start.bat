@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto nopython

rem 가상환경이 없거나 손상된 경우 다시 설치
if exist .venv\Scripts\python.exe goto run

echo [준비] 처음 실행: 가상환경을 만들고 패키지를 설치합니다. 1~2분 걸립니다...
if exist .venv rmdir /s /q .venv
python -m venv .venv
if not exist .venv\Scripts\python.exe goto venvfail
call .venv\Scripts\python -m pip install --upgrade pip -q
call .venv\Scripts\pip install -r requirements.txt -q

:run
echo.
echo  국회 요구자료 목록화 시스템을 시작합니다.
echo  잠시 후 브라우저가 자동으로 열립니다. 주소: http://127.0.0.1:5000
echo  이 창을 닫으면 프로그램이 종료됩니다.
echo.
.venv\Scripts\python app.py
pause
exit /b

:nopython
echo [오류] Python이 설치되어 있지 않습니다.
echo https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치하세요.
echo 설치할 때 "Add Python to PATH" 옵션을 반드시 체크해야 합니다.
pause
exit /b 1

:venvfail
echo [오류] 가상환경 생성에 실패했습니다. 인터넷 연결을 확인한 뒤 다시 실행해 주세요.
pause
exit /b 1
