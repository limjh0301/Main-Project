"""마감 현황 — 관리대장의 제출기한·제출일자로 요구서별 진행 상태를 만든다.

오늘 기준 D-day 계산은 화면(사용자 PC 날짜)에서 한다. 서버 시간대(클라우드는 UTC)에 따라
날짜가 하루 어긋나지 않게 하기 위해서다. 여기서는 요구서 목록과, 아직 제출하지 않은 요구서의
질의가 부서별로 몇 개인지('배분 이력' 시트 기준)만 만든다.
"""

from collections import Counter, defaultdict

from extractor import history, learning
from extractor.ledger import records


def build(wb) -> dict:
    by_doc: dict[str, Counter] = defaultdict(Counter)
    for row in learning.read_log(wb):
        if row["final"] and row["final"] != "해당없음":
            by_doc[row["doc"]][row["final"]] += 1
    out = []
    for rec in records(wb):
        title, questions = history.split_questions(rec["content"])
        out.append({
            "doc": rec["doc_no"], "member": rec["member"], "title": title or (questions[0] if questions else ""),
            "request_date": rec["request_date"], "deadline": rec["deadline"], "submitted": rec["submitted"],
            "questions": len(questions), "depts": dict(by_doc.get(rec["doc_no"], {})),
        })
    return {"records": out}
