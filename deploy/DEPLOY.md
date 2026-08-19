# 서버 배포 가이드 — 링크만 눌러서 쓰는 방식

이 시스템은 웹서버 방식이므로, **사내 서버 한 대에만 설치하면
직원들은 브라우저에서 `http://서버IP:5000` 링크로 바로 사용**할 수 있습니다.
개인 PC에 Python을 설치할 필요가 없습니다. (기존 RAG 챗봇과 같은 운영 방식)

파일은 서버에 저장되지 않고 처리 직후 삭제되므로, 서버 한 대를 여럿이 함께 써도
요구서·관리대장 내용이 서버에 남지 않습니다.

---

## 방법 1: Docker (권장 — 기존 챗봇 서버에 Docker가 있다면 가장 간단)

```bash
git clone <저장소주소> yogu && cd yogu
docker build -t yogu .
docker run -d --name yogu --restart unless-stopped -p 5000:5000 yogu
```

- OCR(한국어), PDF 렌더러가 이미지에 모두 포함되어 있어 별도 설치가 없습니다.
- 접속: `http://서버IP:5000`
- 업데이트: `git pull && docker build -t yogu . && docker restart yogu`

## 방법 2: 리눅스 서버에 직접 설치 + systemd

```bash
# 1) 코드 배치
sudo git clone <저장소주소> /opt/yogu
cd /opt/yogu

# 2) OCR 도구
sudo apt install -y tesseract-ocr tesseract-ocr-kor poppler-utils

# 3) 파이썬 환경
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt gunicorn

# 4) 전용 계정 및 서비스 등록 (재부팅 시 자동 시작 + 죽으면 자동 재시작)
sudo useradd -r -s /usr/sbin/nologin yogu
sudo chown -R yogu:yogu /opt/yogu
sudo cp deploy/yogu.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now yogu

# 상태 확인
systemctl status yogu
```

## 방화벽

사내망에서 5000 포트 접속을 허용해야 합니다.

```bash
sudo ufw allow 5000/tcp        # ufw 사용 시
# 또는 firewalld: sudo firewall-cmd --permanent --add-port=5000/tcp && sudo firewall-cmd --reload
```

## 직원 안내

- 접속 주소: `http://서버IP:5000` (사내 DNS가 있다면 `http://yogu.내부도메인` 형태로 등록 권장)
- 브라우저 즐겨찾기에 추가하거나, 안내 게시판에 링크를 공유하면 끝입니다.

## 참고

- 동시 사용자가 늘면 `yogu.service`(또는 Dockerfile CMD)의 `-w 2`(워커 수)를 4 정도로 올리세요.
- OCR 처리 시간이 길어 gunicorn `--timeout 300`으로 설정되어 있습니다.
- 외부 인터넷에 공개하는 경우에는 HTTPS(nginx 리버스 프록시)와 접근 제한을 추가해야 합니다.
