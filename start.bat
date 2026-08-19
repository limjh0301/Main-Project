@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto nopython

python --version
if errorlevel 1 goto nopython

rem 가상환경이 없거나 손상된 경우 다시 설치
if exist .venv\Scripts\python.exe goto checkpkg

echo.
echo [준비 1/2] 가상환경을 만드는 중... (30초~1분, 백신 검사로 더 걸릴 수 있음)
if exist .venv rmdir /s /q .venv
python -m venv .venv
if not exist .venv\Scripts\python.exe goto venvfail
echo [준비 1/2] 가상환경 생성 완료

echo.
echo [준비 2/2] 패키지를 설치하는 중... (인터넷 연결 필요)
call .venv\Scripts\pip install -r requirements.txt --timeout 15 --retries 2
echo [준비 2/2] 패키지 설치 단계 종료

:checkpkg
rem 패키지가 실제로 설치됐는지 확인 (설치 실패 시 여기서 잡아냄)
.venv\Scripts\python -c "import flask, pdfplumber, openpyxl" >nul 2>nul
if errorlevel 1 goto pkgfail

:run
echo.
echo  국회 요구자료 목록화 시스템을 시작합니다.
echo  잠시 후 브라우저가 자동으로 열립니다. 주소: http://127.0.0.1:5000
echo  브라우저가 안 열리면 직접 주소창에 http://127.0.0.1:5000 을 입력하세요.
echo  이 창을 닫으면 프로그램이 종료됩니다.
echo.
.venv\Scripts\python app.py
echo.
echo [안내] 서버가 종료되었습니다. 위에 오류 메시지가 있다면 확인해 주세요.
pause
exit /b

:nopython
echo.
echo [오류] Python이 설치되어 있지 않거나 실행할 수 없습니다.
echo https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치하세요.
echo 설치할 때 "Add Python to PATH" 옵션을 반드시 체크해야 합니다.
echo.
echo 참고: 시작메뉴의 "앱 실행 별칭" 설정에서 python.exe 별칭이 켜져 있으면
echo Microsoft Store 창만 뜨고 실행이 안 될 수 있습니다. 별칭을 끄고 다시 시도하세요.
pause
exit /b 1

:venvfail
echo.
echo [오류] 가상환경 생성에 실패했습니다. 위의 오류 메시지를 확인해 주세요.
pause
exit /b 1

:pkgfail
echo.
echo [오류] 필수 패키지 설치가 완료되지 않았습니다.
echo 위쪽에 pip 오류 메시지(타임아웃, 연결 실패 등)가 있는지 확인해 주세요.
echo.
echo 사내망/공직자망처럼 인터넷이 제한된 환경에서는 pip이 차단될 수 있습니다.
echo 이 경우 명령 프롬프트에서 프록시를 지정해 설치해야 합니다:
echo   .venv\Scripts\pip install -r requirements.txt --proxy http://프록시주소:포트
echo.
echo 다시 설치를 시도하려면 .venv 폴더를 삭제한 뒤 start.bat 을 다시 실행하세요.
pause
exit /b 1
