"""요구서 텍스트에서 관리대장에 필요한 항목을 뽑아내는 파서.

의정자료전자유통시스템 요구서의 일반적인 서식(문서번호, 위원회, 요구위원,
요구일자, 제출기한, 요구자료 목록)을 정규식 기반으로 파싱한다.
서식 편차에 대비해 각 항목마다 복수의 패턴을 순서대로 시도한다.
"""

import re
from dataclasses import dataclass, field

# 날짜: 2026. 8. 18 / 2026-08-18 / 2026년 8월 18일 등
_DATE = r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?"

_DOC_NO_PATTERNS = [
    r"문서\s*번호\s*[:：]?\s*(\S+(?:\s*제?\s*[\d\-]+\s*호)?)",
    r"요구\s*번호\s*[:：]?\s*(\S+)",
    r"([가-힣]+\s*제?\s*\d{2,}[\-–]\d+\s*호)",
]

_COMMITTEE_PATTERNS = [
    r"위원회(?:명)?\s*[:：]\s*([가-힣·]{2,20}위원회)",
    r"([가-힣·]{2,20}위원회)",
]

_MEMBER_PATTERNS = [
    r"요구\s*위원\s*[:：]?\s*([가-힣]{2,5})",
    r"([가-힣]{2,5})\s*의원(?:실|님)?",
]

_REQUEST_DATE_PATTERNS = [
    r"요구\s*일자?\s*[:：]?\s*" + _DATE,
    r"(?:시행|발송)일?자?\s*[:：]?\s*" + _DATE,
]

_DEADLINE_PATTERNS = [
    r"제출\s*기한\s*[:：]?\s*" + _DATE,
    r"(?:까지\s*제출|제출\s*요구일)\s*[:：]?\s*" + _DATE,
    _DATE + r"\s*까지",
]

_DEPARTMENT_PATTERNS = [
    r"(?:담당|소관)\s*부서\s*[:：]?\s*([^\n]{2,40})",
    r"수신\s*[:：]?\s*([^\n]{2,40})",
]

# 요구자료 목록 항목: "1. ...", "1) ...", "○ ...", "□ ...", "- ..."
_ITEM_PATTERN = re.compile(r"^\s*(?:\d{1,3}\s*[.)]|[○◦□■▶•\-–])\s+(.+)$", re.MULTILINE)

# 목록 항목으로 보기 어려운 접두어 (안내문·주의사항 등)
_ITEM_EXCLUDE = ("붙임", "끝.", "위 자료", "상기", "유의", "문의", "참고")


@dataclass
class ParsedRequest:
    doc_no: str = ""
    committee: str = ""
    member: str = ""
    request_date: str = ""
    deadline: str = ""
    department: str = ""
    items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "doc_no": self.doc_no,
            "committee": self.committee,
            "member": self.member,
            "request_date": self.request_date,
            "deadline": self.deadline,
            "department": self.department,
            "items": self.items,
        }


def _first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _first_date(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{y}-{int(mo):02d}-{int(d):02d}"
    return ""


def _extract_items(text: str) -> list[str]:
    items = []
    for m in _ITEM_PATTERN.finditer(text):
        item = re.sub(r"\s+", " ", m.group(1)).strip()
        if len(item) < 4:
            continue
        if any(item.startswith(word) for word in _ITEM_EXCLUDE):
            continue
        items.append(item)
    return items


def parse_request(text: str) -> ParsedRequest:
    parsed = ParsedRequest(
        doc_no=_first_match(_DOC_NO_PATTERNS, text),
        committee=_first_match(_COMMITTEE_PATTERNS, text),
        member=_first_match(_MEMBER_PATTERNS, text),
        request_date=_first_date(_REQUEST_DATE_PATTERNS, text),
        deadline=_first_date(_DEADLINE_PATTERNS, text),
        department=_first_match(_DEPARTMENT_PATTERNS, text),
        items=_extract_items(text),
    )
    return parsed
