# CLAUDE.md - AI Assistant Guidelines

## 프로젝트 개요

**KISTI 국회 요구자료 관리 프로그램** — 의정자료전자유통시스템 요구서 PDF를 올리면
텍스트를 추출(스캔본은 OCR 폴백)하고 항목을 파싱해 엑셀 관리대장에 누적하는 Flask 앱.
PC 전용(127.0.0.1)으로 실행하며 서버 배포는 하지 않는다.

## 구조

| 경로 | 역할 |
|------|------|
| `app.py` | Flask 앱 (라우팅, 업로드 처리) |
| `extractor/pdf_text.py` | PDF 텍스트 추출 (pdfplumber → tesseract OCR 폴백) |
| `extractor/hwp_text.py` | 첨부 한글파일 텍스트 추출 (HWP 5.0 OLE / HWPX ZIP+XML) |
| `extractor/parser.py` | 요구서 항목 파싱, 첨부 한글파일 항목 분리 (정규식) |
| `extractor/ledger.py` | 엑셀 관리대장 생성·누적 — 기관 관리대장 양식(제목 1행·머리글 3행), 기존 대장 이어쓰기·중복 건너뜀 (openpyxl) |
| `extractor/assign.py` | 질의별 담당 부서 배분 — 카테고리 규칙(RULES) → 세부 배분표(TABLE), 담당자 이름은 넣지 않음 |
| `extractor/roster.py` | 부서별 담당자 명단 — 대장 파일의 '부서별 담당자' 시트 읽기·쓰기 |
| `extractor/history.py` | 이전 질의 찾기 — 대장 기록을 질의 단위로 색인, 동일·기간만 다름·유사(TF-IDF) |
| `extractor/learning.py` | 배분 정정 학습 — '배분 이력'·'배분 추가 규칙' 시트, 정확도·규칙 제안, 이전 정정 반영 |
| `extractor/status.py` | 마감 현황 데이터 (`static/dashboard.js`가 D-day를 사용자 PC 날짜로 계산) |
| `extractor/export.py` | 업무 분장내역 엑셀 — 화면의 최종 배분을 분장내역·부서별 요약·해당없음 시트로 |
| `extractor/board.py` | 처리 결과 → 분배안 화면 데이터 (`static/board.js`가 그림) |
| `extractor/data/assembly_members.csv` | 제22대 국회의원 명단 (소속 정당 보완, 파일명 의원명 인식) |
| `templates/`, `static/` | 업로드 UI (KISTI 브랜딩) |
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
- 직원 이름·연락처는 코드·테스트·커밋에 넣지 않는다 — 담당자 명단은 사용자의 대장 파일 시트에만 둔다
- 기존 코드를 읽고 스타일을 맞출 것, 요청 범위 밖 변경 금지, 시크릿 커밋 금지
- 변경 후 테스트 실행 필수
