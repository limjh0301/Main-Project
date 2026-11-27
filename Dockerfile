FROM python:3.12-slim

# OCR 도구 (한국어 포함) + PDF 렌더러
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-kor poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 5000

# OCR 처리가 오래 걸릴 수 있어 timeout을 넉넉히 준다
# 클라우드 호스팅(Render 등)은 PORT 환경변수를 주입하므로 이를 우선 사용
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-5000} -w 2 --timeout 300 app:app"]
