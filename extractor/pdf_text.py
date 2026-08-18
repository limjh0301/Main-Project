"""PDF 텍스트 추출 모듈.

1차: pdfplumber로 텍스트 레이어 추출 (의정자료전자유통시스템 요구서는 대부분 텍스트 레이어 보유)
2차: 텍스트 레이어가 없거나 빈약한 경우 tesseract OCR로 대체 (스캔본 대응)
"""

import logging
import shutil

import pdfplumber

logger = logging.getLogger(__name__)

# 문서 전체에서 추출된 글자 수가 이 값 미만이면 스캔본으로 간주하고 OCR 수행
MIN_TEXT_CHARS = 50

OCR_DPI = 200
OCR_LANG = "kor+eng"
# 요구서는 단일 컬럼 공문 서식이므로 PSM 4(가변 크기 단일 컬럼)가 가장 안정적
OCR_CONFIG = "--psm 4"


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None and shutil.which("pdftoppm") is not None


def extract_text(pdf_path: str, force_ocr: bool = False) -> tuple[str, str]:
    """PDF에서 텍스트를 추출한다.

    Returns:
        (text, method) — method는 "text-layer" 또는 "ocr"
    """
    text = ""
    if not force_ocr:
        text = _extract_text_layer(pdf_path)
        if len(text.strip()) >= MIN_TEXT_CHARS:
            return text, "text-layer"

    if not ocr_available():
        if text.strip():
            return text, "text-layer"
        raise RuntimeError(
            "PDF에 텍스트 레이어가 없고 OCR 도구(tesseract)가 설치되어 있지 않습니다. "
            "tesseract-ocr, tesseract-ocr-kor, poppler-utils를 설치해 주세요."
        )
    return _extract_ocr(pdf_path), "ocr"


def _extract_text_layer(pdf_path: str) -> str:
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
    except Exception:
        logger.exception("pdfplumber 텍스트 추출 실패: %s", pdf_path)
        return ""
    return "\n".join(pages)


def _extract_ocr(pdf_path: str) -> str:
    import pytesseract
    from pdf2image import convert_from_path

    images = convert_from_path(pdf_path, dpi=OCR_DPI)
    pages = []
    for image in images:
        pages.append(pytesseract.image_to_string(image, lang=OCR_LANG, config=OCR_CONFIG))
    return "\n".join(pages)
