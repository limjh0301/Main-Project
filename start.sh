#!/usr/bin/env bash
# 국회 요구자료 목록화 시스템 실행 스크립트 (macOS / Linux / Raspberry Pi)
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[오류] python3가 설치되어 있지 않습니다."
    exit 1
fi

if [ ! -d .venv ]; then
    echo "[준비] 처음 실행이므로 가상환경을 만들고 패키지를 설치합니다..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install -r requirements.txt -q
fi

echo
echo " 국회 요구자료 목록화 시스템을 시작합니다."
echo " 잠시 후 브라우저가 자동으로 열립니다. (주소: http://127.0.0.1:5000)"
echo " 종료하려면 Ctrl+C 를 누르세요."
echo
exec .venv/bin/python app.py
