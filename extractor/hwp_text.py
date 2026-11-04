"""한글(HWP/HWPX) 첨부파일 텍스트 추출 모듈.

공통요구자료처럼 질의 항목이 많으면 질의서 PDF와 별도로 한글 파일이 첨부된다.
- HWP 5.0: OLE 복합문서, BodyText/SectionN 스트림에 문단 레코드가 (대개 zlib 압축으로) 저장됨
- HWPX: ZIP 안의 Contents/sectionN.xml (OWPML 표준)
문단 단위로 한 줄씩 돌려준다. 표 안의 문단도 순서대로 포함된다.
"""

import re
import struct
import sys
import zipfile
import zlib
from array import array

HWP_EXTENSIONS = (".hwp", ".hwpx")

_PARA_TEXT = 67  # HWPTAG_PARA_TEXT
# WCHAR 1개로 끝나는 제어문자. 나머지 0~31 제어문자는 WCHAR 8개를 차지한다 (HWP 5.0 규격)
_SINGLE_CTRL = frozenset({0, 10, 13, *range(24, 32)})
_FLAG_COMPRESSED = 0x1
_FLAG_LOCKED = 0x2 | 0x4  # 암호 설정, 배포용 문서
_MAX_SECTION_BYTES = 50 * 1024 * 1024  # 압축 폭탄 방지
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


class HwpReadError(RuntimeError):
    """한글 파일을 읽을 수 없을 때 발생 (사용자에게 그대로 보여줄 메시지)."""


def extract_hwp_text(path: str) -> str:
    if path.lower().endswith(".hwpx"):
        return _extract_hwpx(path)
    return _extract_hwp(path)


def _extract_hwp(path: str) -> str:
    import olefile

    if not olefile.isOleFile(path):
        raise HwpReadError("한글(HWP) 문서 형식이 아닙니다. 파일이 손상되지 않았는지 확인해 주세요.")
    try:
        with olefile.OleFileIO(path) as ole:
            flags = struct.unpack_from("<I", ole.openstream("FileHeader").read(), 36)[0]
            if flags & _FLAG_LOCKED:
                raise HwpReadError(
                    "암호가 걸려 있거나 배포용으로 저장된 한글 문서는 읽을 수 없습니다. "
                    "한글에서 일반 문서로 다시 저장해 주세요."
                )
            sections = sorted(
                (e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText"),
                key=lambda e: int(re.sub(r"\D", "", e[1]) or 0),
            )
            lines = []
            for section in sections:
                data = ole.openstream(section).read()
                if flags & _FLAG_COMPRESSED:
                    data = zlib.decompressobj(-15).decompress(data, _MAX_SECTION_BYTES)
                lines.extend(_paragraph_texts(data))
    except HwpReadError:
        raise
    except Exception as e:
        raise HwpReadError("한글 문서를 읽는 중 오류가 발생했습니다. 파일이 손상되지 않았는지 확인해 주세요.") from e
    return "\n".join(lines)


def _paragraph_texts(data: bytes):
    """본문 레코드 열에서 문단 텍스트 레코드만 골라 문자열로 돌려준다."""
    pos = 0
    while pos + 4 <= len(data):
        header = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        tag, size = header & 0x3FF, header >> 20
        if size == 0xFFF:  # 4095바이트 이상이면 실제 크기가 뒤따른다
            size = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        if tag == _PARA_TEXT:
            yield _decode_para(data[pos:pos + size])
        pos += size


def _decode_para(raw: bytes) -> str:
    units = array("H")
    units.frombytes(raw[: len(raw) // 2 * 2])
    if sys.byteorder == "big":
        units.byteswap()
    out = array("H")
    i = 0
    while i < len(units):
        c = units[i]
        if c >= 32:
            out.append(c)
            i += 1
            continue
        if c == 9:
            out.append(9)
        elif c == 10:  # 문단 안 줄바꿈
            out.append(32)
        i += 1 if c in _SINGLE_CTRL else 8
    if sys.byteorder == "big":
        out.byteswap()
    return out.tobytes().decode("utf-16-le", "replace")


def _extract_hwpx(path: str) -> str:
    from xml.etree import ElementTree

    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise HwpReadError("한글(HWPX) 문서 형식이 아닙니다. 파일이 손상되지 않았는지 확인해 주세요.") from e
    with zf:
        names = sorted(
            (n for n in zf.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)),
            key=lambda n: int(re.search(r"\d+", n).group()),
        )
        if not names:
            raise HwpReadError("한글(HWPX) 문서에서 본문을 찾을 수 없습니다.")
        lines = []
        for name in names:
            if zf.getinfo(name).file_size > _MAX_SECTION_BYTES:
                raise HwpReadError("한글 문서 본문이 너무 큽니다.")
            try:
                root = ElementTree.fromstring(zf.read(name))
            except ElementTree.ParseError as e:
                raise HwpReadError("한글(HWPX) 문서 본문을 해석할 수 없습니다.") from e
            for p in root.iter(f"{_HP}p"):
                lines.append("".join("".join(t.itertext()) for t in p.findall(f"{_HP}run/{_HP}t")))
    return "\n".join(lines)
