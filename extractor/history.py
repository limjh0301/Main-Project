"""이전 질의 찾기 — 관리대장에 쌓인 질의와 새 질의를 비교해 기제출 자료 후보를 찾는다.

대장의 내용 칸("[제목]" 다음 줄부터 질의)을 질의 단위로 나눠 색인하고, 새 질의마다
  동일        : 띄어쓰기·문장부호만 다르고 글자가 같음
  기간만 다름 : '최근 3년간'·연도 같은 숫자만 다름
  유사 n%     : 글자 두 개씩 끊은 조각의 TF-IDF 코사인 유사도가 기준 이상
순으로 가장 가까운 이전 질의를 돌려준다. '현황·자료·관련'처럼 어디에나 나오는 말은 가중치가 낮다.
"""

import math
import re
from collections import Counter

SIMILAR_MIN = 0.35  # 기존 대장 75건으로 맞춘 기준 — 이보다 낮으면 관련 없는 질의가 섞인다
_FUZZY_MIN_LEN = 6  # 너무 짧은 질의(예: '직제표')는 동일·기간만 다름일 때만 이어 준다

_DETAIL = re.compile(r"^\s*[-※*·ㅇ○◦▪•]")
_LEAD = re.compile(r"^\s*(?:\d{1,3}\s*[.)]|\(\d+\)|[가-하]\s*[.)]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s*[.)]?|■|□)\s*")


def split_questions(content: str) -> tuple[str, list[str]]:
    """대장 내용 칸 → (제목, 질의 목록). '- …'·'※ …' 같은 세부 줄은 앞 질의에 붙인다."""
    lines = [line.strip() for line in str(content or "").split("\n") if line.strip()]
    title = ""
    if lines and lines[0].startswith("[") and lines[0].endswith("]"):
        title, lines = lines[0][1:-1].strip(), lines[1:]
    questions: list[str] = []
    for line in lines:
        if _DETAIL.match(line):
            if questions:  # 첫 질의 앞의 '※ 대상·기간' 같은 안내 줄은 질의로 세지 않는다
                questions[-1] += " " + line
        else:
            questions.append(_LEAD.sub("", line))
    return title, [q for q in questions if q]


def _exact(text: str) -> str:
    return re.sub(r"[\W_]+", "", _LEAD.sub("", text))


def _loose(text: str) -> str:
    return re.sub(r"최근|년간|년도|개년|년|\d+", "", _exact(text))


def _bigrams(text: str) -> Counter:
    return Counter(text[i:i + 2] for i in range(len(text) - 1))


class Index:
    """대장 기록(records)의 질의 색인."""

    def __init__(self, records: list[dict]):
        self.entries = []
        for rec in records:
            title, questions = split_questions(rec.get("content", ""))
            for q in questions:
                self.entries.append({**{k: rec.get(k, "") for k in ("doc_no", "request_date", "member", "submitted")},
                                     "title": title, "text": q, "exact": _exact(q), "loose": _loose(q)})
        counts = [_bigrams(e["loose"]) for e in self.entries]
        df = Counter(k for c in counts for k in c)
        n = len(counts)
        self._idf = {k: math.log((n + 1) / (v + 1)) + 1 for k, v in df.items()}
        self._unseen = math.log(n + 1) + 1
        self._vecs = [self._vec(c) for c in counts]

    def _vec(self, counts: Counter) -> dict:
        v = {k: c * self._idf.get(k, self._unseen) for k, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {k: x / norm for k, x in v.items()}

    def __len__(self) -> int:
        return len(self.entries)

    def match(self, text: str, limit: int = 2) -> list[dict]:
        """가까운 이전 질의 (점수 높은 순, 같은 요구서는 한 번만)."""
        if not self.entries:
            return []
        exact, loose = _exact(text), _loose(text)
        vec = self._vec(_bigrams(loose)) if len(loose) >= _FUZZY_MIN_LEN else {}
        scored = []
        for e, ev in zip(self.entries, self._vecs):
            if exact and exact == e["exact"]:
                score, kind = 1.0, "동일"
            elif len(loose) >= 3 and loose == e["loose"]:
                score, kind = 0.99, "기간만 다름"
            elif vec:
                score = sum(x * ev.get(k, 0.0) for k, x in vec.items())
                if score < SIMILAR_MIN:
                    continue
                kind = f"유사 {round(score * 100)}%"
            else:
                continue
            scored.append((score, kind, e))
        scored.sort(key=lambda s: -s[0])
        out, seen = [], set()
        for score, kind, e in scored:
            if e["doc_no"] in seen:
                continue
            seen.add(e["doc_no"])
            out.append({"doc": e["doc_no"], "date": e["request_date"], "member": e["member"], "title": e["title"],
                        "submitted": e["submitted"], "text": e["text"], "kind": kind, "score": round(score, 2)})
            if len(out) == limit:
                break
        return out
