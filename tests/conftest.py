import zipfile
from xml.sax.saxutils import escape

import pytest

_SECTION = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">{body}</hs:sec>'
)


@pytest.fixture
def make_hwpx(tmp_path):
    """문단 목록으로 최소 구조의 HWPX(ZIP+OWPML) 파일을 만든다."""

    def build(name: str, paragraphs: list[str]):
        body = "".join(f"<hp:p><hp:run><hp:t>{escape(p)}</hp:t></hp:run></hp:p>" for p in paragraphs)
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("mimetype", "application/hwp+zip")
            zf.writestr("Contents/section0.xml", _SECTION.format(body=body))
        return path

    return build
