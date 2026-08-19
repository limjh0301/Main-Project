"""요구서 텍스트에서 관리대장에 필요한 항목을 뽑아내는 파서.

의정자료전자유통시스템 요구서의 일반적인 서식(요구서번호, 소관위원회, 요구의원,
정당·지역구, 요구일자, 제출기한, 요구자, 이메일, 자료 요구내용)을 정규식 기반으로
파싱한다. 서식 편차에 대비해 각 항목마다 복수의 패턴을 순서대로 시도한다.
"""

import re
from dataclasses import asdict, dataclass, field

# 날짜: 2026. 8. 18 / 2026-08-18 / 2026년 8월 18일 등
_DATE = r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?"

def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p) for p in patterns]


# 요구서번호: 전자유통시스템 10자리 번호 우선, 문서번호 형식 폴백
_DOC_NO_PATTERNS = _compile([
    r"요구서\s*번호\s*[:：]?\s*([0-9][0-9\-]{5,19})",
    r"\b(\d{10})\b",
    r"문서\s*번호\s*[:：]?\s*(\S+(?:\s*제?\s*[\d\-]+\s*호)?)",
    r"([가-힣]+\s*제?\s*\d{2,}[\-–]\d+\s*호)",
])

_COMMITTEE_PATTERNS = _compile([
    r"(?:소관\s*)?위원회(?:명)?\s*[:：]\s*([가-힣·]{2,20}위원회)",
    r"([가-힣·]{2,20}위원회)",
])

# 요구의원/기관 ("국회의원 홍길동의원실" 형태 우선)
_MEMBER_PATTERNS = _compile([
    r"국회의원\s*([가-힣]{2,5})\s*의원실",
    r"([가-힣]{2,5})\s*의원실",
    r"요구\s*의원\s*[:：]?\s*([가-힣]{2,5})",
    r"요구\s*위원\s*[:：]?\s*([가-힣]{2,5})",
    r"([가-힣]{2,5})\s*의원(?:님)?",
    r"요구\s*기관\s*[:：]?\s*([^\n]{2,30})",
])

# 의원명으로 오인하기 쉬운 일반 명사
_MEMBER_BLACKLIST = frozenset({"국회", "국회의", "소관", "요구"})

# 정당: "정당 : OO당" 또는 "홍길동 의원(OO당, 지역구)" 형식
_PARTY_PATTERNS = _compile([
    r"정당\s*[:：]\s*([^\n,()·]{2,20})",
    r"의원\s*\(\s*([^,·)\n]{2,20})\s*[,·]",
])

# 지역구: "지역구 : 서울 종로구" 또는 "의원(OO당, 서울 종로구)" 형식
_DISTRICT_PATTERNS = _compile([
    r"지역구\s*[:：]\s*([^\n]{2,30})",
    r"의원\s*\(\s*[^,·)\n]{2,20}\s*[,·]\s*([^)\n]{2,30})\)",
])

_REQUEST_DATE_PATTERNS = _compile([
    r"요구\s*일자?\s*[:：]?\s*" + _DATE,
    r"(?:시행|발송)일?자?\s*[:：]?\s*" + _DATE,
])

_DEADLINE_PATTERNS = _compile([
    r"제출\s*기한\s*[:：]?\s*" + _DATE,
    r"제출\s*완료\s*일자?\s*[:：]?\s*" + _DATE,
    r"(?:까지\s*제출|제출\s*요구일)\s*[:：]?\s*" + _DATE,
    _DATE + r"\s*까지",
])

# 요구자: 실무 담당자(보좌관·비서관 등)
_REQUESTER_PATTERNS = _compile([
    r"요구자\s*[:：]?\s*([가-힣]{2,5})",
    r"담당\s*자?\s*[:：]?\s*([가-힣]{2,5})",
    r"([가-힣]{2,5})\s*(?:보좌관|비서관|선임비서관|비서)\b",
])

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# 자료 요구내용 항목 시작: "1. ...", "1) ...", "○ ...", "- ..." 등 (번호·기호 포함해 보존)
_ITEM_BULLET_START = re.compile(r"^\s*([○◦□■▶•\-–]\s*\S.*)$")
# 표 양식에서는 왼쪽 열(기관명)이 같은 줄 앞에 붙으므로, 한글·공백 접두 뒤의 번호 항목도 인식
_ITEM_NUM_ANY = re.compile(r"^[가-힣\s]*?(\d{1,3}\s*[.)]\s*\S.*)$")

# 항목 수집을 끝내는 안내문·마감 문구
_ITEM_STOP = ("붙임", "끝.", "위 자료", "상기 자료", "유의", "문의", "의정자료전자유통시스템")

# 페이지 표기(1 / 1), 세로쓰기 표 헤더(소 관 기 관 ...) 등 무시할 줄
_SKIP_LINE = re.compile(r"^(?:\d+\s*/\s*\d+|(?:[가-힣]\s+){2,}[가-힣])$")

# 라벨 줄(예: "제출기한 : ...")은 항목의 연속 줄로 보지 않음
_LABEL_LINE = re.compile(
    r"^\s*(?:소관\s*)?(?:위원회|요구\s*일자?|제출\s*기한|요구서?\s*번호|문서\s*번호|"
    r"요구\s*(?:의원|위원|기관|자)|정당|지역구|수신|발신|시행|담당|전화|팩스|이메일|E-?mail)\s*[:：]"
)


@dataclass
class ParsedRequest:
    committee: str = ""       # 소관위원회
    request_date: str = ""    # 요구일자 (YYYY-MM-DD)
    deadline: str = ""        # 제출기한 (YYYY.MM.DD)
    doc_no: str = ""          # 요구서번호
    member: str = ""          # 요구의원/기관
    party: str = ""           # 정당
    district: str = ""        # 지역구
    items: list[str] = field(default_factory=list)  # 자료 요구내용 (항목별)
    requester: str = ""       # 요구자
    email: str = ""           # 요구자 이메일

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _first_match(patterns: list[re.Pattern], text: str, exclude=frozenset()) -> str:
    for pattern in patterns:
        for m in pattern.finditer(text):
            candidate = _norm(m.group(1))
            if candidate not in exclude:
                return candidate
    return ""


def _first_date(patterns: list[re.Pattern], text: str, sep: str) -> str:
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{y}{sep}{int(mo):02d}{sep}{int(d):02d}"
    return ""


def _extract_items(text: str) -> list[str]:
    """항목 시작 줄을 찾고, PDF 줄바꿈으로 잘린 뒷부분(연속 줄)을 이어붙인다."""
    items: list[str] = []
    current: list[str] = []

    def flush():
        if current:
            item = _norm(" ".join(current))
            if len(item) >= 4:
                items.append(item)
            current.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            flush()
            continue
        if any(line.startswith(word) for word in _ITEM_STOP):
            flush()
            continue
        if _SKIP_LINE.match(line):
            continue

        bullet = _ITEM_BULLET_START.match(line)
        if bullet and current:
            # 항목 수집 중의 "- ..." 줄은 하위 내용이므로 이어붙인다
            current.append(bullet.group(1).strip())
            continue

        # 번호 항목은 표 양식의 왼쪽 열(한글 기관명)이 앞에 붙어 있어도 인식
        num = _ITEM_NUM_ANY.match(line)
        if num:
            flush()
            current.append(num.group(1).strip())
            continue
        if bullet:
            flush()
            current.append(bullet.group(1).strip())
            continue

        # 항목 수집 중이면, 라벨 줄이 아닌 이상 줄바꿈으로 잘린 연속 문장으로 본다
        if current:
            if _LABEL_LINE.match(line):
                flush()
            elif len(line) <= 2:
                # 표 왼쪽 열에서 줄바꿈된 기관명 조각("원" 등)은 무시
                continue
            else:
                current.append(line)

    flush()
    return items


def parse_request(text: str) -> ParsedRequest:
    email_match = _EMAIL_PATTERN.search(text)
    return ParsedRequest(
        committee=_first_match(_COMMITTEE_PATTERNS, text),
        request_date=_first_date(_REQUEST_DATE_PATTERNS, text, "-"),
        deadline=_first_date(_DEADLINE_PATTERNS, text, "."),
        doc_no=_first_match(_DOC_NO_PATTERNS, text),
        member=_first_match(_MEMBER_PATTERNS, text, exclude=_MEMBER_BLACKLIST),
        party=_first_match(_PARTY_PATTERNS, text),
        district=_first_match(_DISTRICT_PATTERNS, text),
        items=_extract_items(text),
        requester=_first_match(_REQUESTER_PATTERNS, text),
        email=email_match.group(0) if email_match else "",
    )
