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


# ---------- 첨부 한글파일(공통요구자료 등) 항목 분리 ----------
# 최상위 "1. …", 하위 "1) …", 세부 "- …"·"①"·"·" 구조의 질의 목록을 배분 단위(하위 항목)로 나눈다.
# 한글 자동 문단번호는 텍스트에 남지 않으므로, 번호 없는 목록은 들여쓰지 않은 줄 하나를 항목 하나로 본다.
# "<연구기관>" 같은 섹션 제목이 있으면 섹션마다 번호를 새로 매기고 항목 앞에 섹션명을 붙인다.

_ATT_TOP = re.compile(r"^(\d{1,3})[.,]\s*(\S.*)$")  # "6," 같은 번호 오타 허용
_ATT_SUB = re.compile(r"^\s*(\d{1,2})\)\s*(\S.*)$")
_ATT_SECTION = re.compile(r"^<\s*(.+?)\s*>$")
_ATT_DETAIL_START = ("-", "·", "*", "※", "○", "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩")
# 별도 자료가 아니라 상위 항목의 제출 조건인 하위 항목 (예: "관련 근거 별첨", "자회사 포함 제출")
_ATT_CONDITION = re.compile(r"(포함|별첨|첨부|기재)(\s*(제출|요망|바람))?\s*$")
_ATT_SUBJECT = re.compile(r"현황|내역|목록|명단|결과|실적|리스트")


@dataclass
class ParsedAttachment:
    notes: list[str] = field(default_factory=list)  # 첫 항목 앞의 제출 안내(※ 제출기한·방법 등)
    items: list[str] = field(default_factory=list)  # 배분 단위 항목 (관리대장 1행씩)


def _is_condition(text: str) -> bool:
    return bool(_ATT_CONDITION.search(text)) and not _ATT_SUBJECT.search(text)


def _is_bullet(stripped: str) -> bool:
    return stripped.startswith(_ATT_DETAIL_START)


def parse_attachment(text: str) -> ParsedAttachment:
    lines = [raw.rstrip() for raw in text.splitlines() if raw.strip()]
    notes: list[str] = []
    tops: list[dict] = []

    # 문서 앞머리: 제목 한 줄(바로 뒤에 안내 글머리가 올 때)과 안내 글머리 묶음
    i = 0
    if len(lines) > 1 and not _ATT_TOP.match(lines[0]) and not _is_bullet(lines[0].strip()) \
            and _is_bullet(lines[1].strip()):
        notes.append(_norm(lines[0]))
        i = 1
    while i < len(lines) and _is_bullet(lines[i].strip()) and not _ATT_SUB.match(lines[i]):
        notes.append(_norm(lines[i].strip()))
        i += 1

    section, count = "", 0
    for line in lines[i:]:
        stripped = line.strip()
        sec = _ATT_SECTION.match(stripped)
        if sec:
            section, count = sec.group(1), 0
            continue
        top, sub = _ATT_TOP.match(line), _ATT_SUB.match(line)
        cur = [t for t in tops if t["section"] == section]

        if top:
            # 번호 없는 제목 하나 바로 뒤에 1번이 오면 그 제목은 문서 제목이다
            if top.group(1) == "1" and len(cur) == 1 and cur[0]["auto"] \
                    and not cur[0]["detail"] and not cur[0]["subs"]:
                tops.remove(cur[0])
                notes.append(cur[0]["title"])
            count = int(top.group(1))
            tops.append({"no": top.group(1), "title": _norm(top.group(2)), "detail": [], "subs": [],
                         "section": section, "auto": False})
        elif sub and cur:
            cur[-1]["subs"].append({"no": sub.group(1), "lines": [_norm(sub.group(2))]})
        elif _is_bullet(stripped) or line[0].isspace() or sub:
            if cur:
                target = cur[-1]["subs"][-1]["lines"] if cur[-1]["subs"] else cur[-1]["detail"]
                target.append(_norm(stripped))
            else:
                notes.append(_norm(stripped))
        elif not cur or cur[-1]["auto"]:
            count += 1
            tops.append({"no": str(count), "title": _norm(stripped), "detail": [], "subs": [],
                         "section": section, "auto": True})
        else:
            # 번호 목록 중간의 번호 없는 줄은 앞 항목에 이어지는 내용이다
            cur[-1]["detail"].append(_norm(stripped))

    items: list[str] = []
    for t in tops:
        title = f'[{t["section"]}] {t["title"]}' if t["section"] else t["title"]
        subs = [s for s in t["subs"] if not (len(s["lines"]) == 1 and _is_condition(s["lines"][0]))]
        common = t["detail"] + [s["lines"][0] for s in t["subs"] if s not in subs]
        if len(subs) <= 1:
            body = [f'{t["no"]}. {title}']
            body += [f'{s["no"]}) ' + "\n".join(s["lines"]) for s in t["subs"]]
            items.append("\n".join(body[:1] + t["detail"] + body[1:]))
            continue
        for s in subs:
            lines_ = [f'{t["no"]}-{s["no"]}) [{title}] {s["lines"][0]}', *s["lines"][1:]]
            lines_ += [f"(공통) {c}" for c in common]
            items.append("\n".join(lines_))
    return ParsedAttachment(notes=notes, items=items)
