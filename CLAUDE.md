# CLAUDE.md - AI Assistant Guidelines

## 프로젝트 개요

**국회 요구자료 목록화 시스템** — 의정자료전자유통시스템 요구서 PDF를 업로드하면
텍스트를 추출(스캔본은 OCR 폴백)하고 항목을 파싱해 엑셀 관리대장에 누적하는 Flask 웹 앱.

## 구조

| 경로 | 역할 |
|------|------|
| `app.py` | Flask 앱 (라우팅, 업로드 처리) |
| `extractor/pdf_text.py` | PDF 텍스트 추출 (pdfplumber → tesseract OCR 폴백) |
| `extractor/parser.py` | 요구서 항목 파싱 (정규식) |
| `extractor/ledger.py` | 엑셀 관리대장 생성·누적, 국회의원 현황 시트 연동 (openpyxl) |
| `extractor/data/assembly_members.csv` | 제22대 국회의원 명단 (관리대장 시트2 데이터) |
| `templates/`, `static/` | 업로드 UI (KISTI 브랜딩) |
| `deploy/`, `render.yaml`, `Dockerfile` | 배포 (Render Blueprint / Docker / systemd) |
| `start.bat`, `start.sh`, `바로가기.html` | 로컬 PC 실행 지원 |

## 명령어

```bash
pip install -r requirements.txt   # 의존성 설치
python -m pytest tests/ -q        # 테스트
python app.py                     # 로컬 실행 (http://127.0.0.1:5000)
```

## 작업 규칙

- 커밋: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
- 브랜치: `feature/…`, `fix/…`, AI 작업은 `claude/<session-id>`
- 관리대장 열 구조는 `ledger.py`의 `COLUMNS`가 단일 출처 — 헤더·미리보기·검증이 모두 여기서 파생됨
- `start.bat`은 CP949 인코딩 유지 (한글 Windows 콘솔용)
- 기존 코드를 읽고 스타일을 맞출 것, 요청 범위 밖 변경 금지, 시크릿 커밋 금지
- 변경 후 테스트 실행 필수
