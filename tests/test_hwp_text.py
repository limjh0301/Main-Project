import struct

import pytest

from extractor.hwp_text import HwpReadError, _decode_para, _paragraph_texts, extract_hwp_text


def _utf16(text: str) -> bytes:
    return text.encode("utf-16-le")


def _ctrl(code: int) -> bytes:
    # 확장·인라인 제어문자는 WCHAR 8개(코드 + 부가정보 6개 + 코드)를 차지한다
    return struct.pack("<8H", code, 0, 0, 0, 0, 0, 0, code)


def _record(tag: int, payload: bytes) -> bytes:
    size = len(payload)
    if size >= 0xFFF:
        return struct.pack("<II", tag | (0xFFF << 20), size) + payload
    return struct.pack("<I", tag | (size << 20)) + payload


def test_decode_para_skips_control_chars():
    raw = _ctrl(11) + _utf16("1) 설립") + _ctrl(9) + _utf16("근거") + struct.pack("<H", 13)
    assert _decode_para(raw) == "1) 설립\t근거"


def test_paragraph_texts_reads_only_text_records_including_long_ones():
    long_text = "가" * 3000  # 6000바이트 → 확장 크기 헤더 사용
    data = (
        _record(66, b"\x00" * 22)  # 문단 헤더 (무시)
        + _record(67, _utf16("※ 9월 28일까지 제출"))
        + _record(67, _utf16(long_text))
    )
    assert list(_paragraph_texts(data)) == ["※ 9월 28일까지 제출", long_text]


def test_extract_hwpx(make_hwpx):
    path = make_hwpx("a.hwpx", ["기관 개요", " 1) 설립근거 & 목적"])
    assert extract_hwp_text(str(path)) == "기관 개요\n 1) 설립근거 & 목적"


def test_non_hwp_file_raises_readable_error(tmp_path):
    bad = tmp_path / "bad.hwp"
    bad.write_bytes(b"not an ole file")
    with pytest.raises(HwpReadError):
        extract_hwp_text(str(bad))
    bad_x = tmp_path / "bad.hwpx"
    bad_x.write_bytes(b"not a zip")
    with pytest.raises(HwpReadError):
        extract_hwp_text(str(bad_x))
