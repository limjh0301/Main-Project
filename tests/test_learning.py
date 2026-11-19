from extractor import learning
from extractor.ledger import create_ledger


def _log(rows):
    return [{"date": "2026-10-01", "doc": d, "key": k, "text": t, "model": m, "final": f} for d, k, t, m, f in rows]


LOG = _log([
    ("0001", "1", "병가 사용 복무점검 실시 현황", "인재개발실", "감사부"),
    ("0002", "3", "연구원 복무점검 결과 및 조치", "인재개발실", "감사부"),
    ("0003", "2", "복무점검 대상 기관 목록", "감사부", "감사부"),
    ("0003", "4", "직원 징계 현황", "인재개발실", "인재개발실"),
])


def test_suggestions_from_repeated_corrections():
    got = learning.suggestions(LOG, [])
    assert [(s["keyword"], s["dept"], s["count"]) for s in got] == [("복무점검", "감사부", 2)]
    assert learning.suggestions(LOG, [{"keyword": "복무점검", "dept": "감사부"}]) == []


def test_no_suggestion_when_word_points_elsewhere_too():
    log = LOG + _log([("0004", "1", "복무점검 매뉴얼", "인재개발실", "인재개발실")] * 1)
    log += _log([("0005", "1", "복무점검 교육", "인재개발실", "인재개발실")])
    assert learning.suggestions(log, []) == []  # 복무점검 질의의 확정 부서가 감사부 3/5 = 60% < 80%


def test_stats():
    assert learning.stats(LOG) == {"total": 4, "kept": 2, "rate": 50}
    assert learning.stats([])["rate"] is None


def test_learner_applies_rules_then_previous_corrections():
    learner = learning.Learner(LOG, [{"keyword": "칼퇴", "dept": "인재개발실"}])
    qs = [
        {"text": "직원 칼퇴 현황", "dept": "기획실", "task": "x", "ambiguous": True, "why": "", "section": ""},
        {"text": "(최근5년간) 병가 사용 복무점검 실시 현황", "dept": "인재개발실", "task": "x", "ambiguous": False, "why": "", "section": ""},
        {"text": "예산서", "dept": "예산실", "task": "x", "ambiguous": False, "why": "", "section": ""},
    ]
    learner.apply(qs)
    assert [(q["dept"], q["why"]) for q in qs] == [
        ("인재개발실", "‘칼퇴’ 추가 규칙"), ("감사부", "이전 정정 반영 (0001)"), ("예산실", "")]
    assert not qs[0]["ambiguous"]


def test_log_round_trip_in_workbook():
    wb = create_ledger()
    learning.write_log(wb, [{k: v for k, v in r.items() if k != "date"} for r in LOG])
    # 같은 요구서를 다시 저장하면 그 요구서 기록만 교체
    learning.write_log(wb, [{"doc": "0003", "key": "2", "text": "복무점검 대상", "model": "감사부", "final": "기획실"}])
    log = learning.read_log(wb)
    assert [(r["doc"], r["final"]) for r in log] == [("0001", "감사부"), ("0002", "감사부"), ("0003", "기획실")]
