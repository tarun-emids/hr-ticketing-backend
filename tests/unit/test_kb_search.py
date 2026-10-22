"""Pure knowledge-base rules: role pools, weighted search, keyword shaping.

No DB, no HTTP — mirrors how tests/unit/test_notification_rules.py tests the
notification recipient rules. The scorer's contract:
  - a token must hit a QUALIFIER field (title/category/keywords/summary) or
    the document is not selectable, no matter how well the body matches;
  - field weights order the results; exact title-phrase adds a bonus.
"""
from app.services.kb_service import (
    POPULAR_LIMIT,
    ROLE_POOLS,
    SEARCH_RESULT_LIMIT,
    keywords_out,
    pools_for,
    score,
    search_rows,
    tokenize,
)


def _doc(**over):
    base = {
        "slug": "leave-and-time-off-policy",
        "ref": "KB-E-01",
        "title": "Leave and Time Off Policy",
        "category": "Leave",
        "audience": "employee",
        "summary": "How time off accrues, carries over and gets approved.",
        "keywords": "leave, pto, vacation, carryover",
        "search_text": "policy on remote equipment monitors nobody wants to read",
    }
    base.update(over)
    return base


def test_employee_pool_is_employee_only():
    assert pools_for("employee") == ["employee"]


def test_agent_pool_includes_both_pools():
    # Agents act as the admin tier and need the public policies to answer
    # employee questions: both pools, nothing else.
    assert pools_for("agent") == ["employee", "hr"]
    assert pools_for("admin") == ["employee", "hr"]


def test_unknown_role_sees_nothing():
    assert pools_for("visitor") == []
    assert pools_for(None) == []


def test_pool_map_never_grants_new_audiences_silently():
    allowed = {pool for pools in ROLE_POOLS.values() for pool in pools}
    assert allowed == {"employee", "hr"}


def test_tokenize_drops_single_chars_and_normalises():
    assert tokenize("Leave  of ABSENCE!") == ["leave", "of", "absence"]
    assert tokenize("a i") == []


def test_body_only_match_is_not_selectable():
    doc = _doc(search_text="weekly scrum ceremonies happen wednesday")
    tokens = tokenize("scrum")
    assert score(doc, tokens, "scrum") is None
    assert search_rows([doc], "scrum") == []


def test_title_hit_scores_higher_than_body_hit():
    title_hit = _doc()
    body_hit = _doc(
        slug="company-handbook",
        ref="KB-E-09",
        title="Company Handbook",
        keywords="overview",
        summary="General welcome content.",
        search_text="leave procedures for every scenario imaginable",
    )
    ranked = search_rows([body_hit, title_hit], "leave")
    assert ranked[0]["slug"] == "leave-and-time-off-policy"


def test_weights_order_field_hits_strictly():
    title_hitter = _doc(title="Leave Policy Zeta")                 # token in title
    category_hitter = _doc(title="Working Hours", category="Leave")
    keywords_hitter = _doc(title="Working Hours", category="Workplace",
                           keywords="leave, shift")
    summary_hitter = _doc(title="Working Hours", category="Workplace",
                          keywords="shift", summary="leave accrual detail")
    ranked = search_rows(
        [summary_hitter, keywords_hitter, category_hitter, title_hitter], "leave"
    )
    assert [d["title"] for d in ranked] == [
        "Leave Policy Zeta",     # title hits outrank everything
        "Working Hours",         # category hit
        "Working Hours",         # keywords hit
        "Working Hours",         # summary hit ranks last but still selected
    ]


def test_every_token_must_qualify():
    # 'scrum' exists only in the body → not selectable even though
    # 'leave' hits the title.
    doc = _doc(search_text="scrum ceremonies weekly")
    tokens = tokenize("leave scrum")
    assert score(doc, tokens, "leave scrum") is None


def test_phrase_bonus_lifts_exact_title_matches():
    with_phrase = _doc()
    without = _doc(
        slug="embedded-leave-forms",
        ref="KB-E-42",
        title="Working Hours",
        category="Workplace",
        keywords="leave, forms",
    )
    ranked = search_rows([without, with_phrase], "leave and time off")
    assert ranked[0]["slug"] == "leave-and-time-off-policy"


def test_tiebreak_is_alphabetical_title():
    a = _doc(title="Alpha Leave Rules")
    b = _doc(title="Beta Leave Rules")
    ranked = search_rows([b, a], "leave")
    assert [d["title"] for d in ranked] == ["Alpha Leave Rules", "Beta Leave Rules"]


def test_keywords_out_splits_and_strips():
    assert keywords_out("leave, pto,  , carryover") == ["leave", "pto", "carryover"]
    assert keywords_out(None) == []
    assert keywords_out("") == []


def test_limits_exported_for_reference():
    assert SEARCH_RESULT_LIMIT == 3
    assert POPULAR_LIMIT == 8
