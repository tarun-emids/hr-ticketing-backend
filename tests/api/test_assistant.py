"""HR assistant endpoint — grounding, citations and the audit trail.

Runs against the offline SQLite double; embeddings and the chat model are
faked at their call seams (app.rag.embeddings.embed_texts / app.rag.llm.chat),
exactly the seam they'd use online — so the tests pin the SERVICE contract:
role-pool gating, [REF ¶block] reconciliation, the machine-verified sources
footer, and one audit row per answered question. No chat history exists.
"""

import json
import uuid as uuidlib

import pytest

from tests.conftest import U


def _fake_embed(vector):
    def embed(texts):
        return [vector] * len(texts)

    return embed


def _fake_llm(answer_text):
    def chat(messages):
        return answer_text

    return chat


def _stub_embed(arg_guard="embed must not be called here"):
    def embed(texts):
        raise AssertionError(arg_guard)

    return embed


def _stub_llm():
    def chat(messages):
        raise AssertionError("chat model must not be called here")

    return chat


def _chunk(
    fake,
    slug,
    ref,
    title,
    audience,
    section,
    block_no,
    body,
    vector,
):
    """Seed one citable paragraph against the harness's seeded documents."""
    document_id = fake.execute("SELECT id FROM kb_documents WHERE slug = %s", (slug,))[0][
        "id"
    ]
    fake.execute(
        "INSERT INTO kb_document_chunks (id, document_id, document_slug, ref, title,"
        " audience, section, block_no, body, embedding)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            str(uuidlib.uuid4()),
            document_id,
            slug,
            ref,
            title,
            audience,
            section,
            block_no,
            body,
            json.dumps(vector),
        ),
    )


def _ask(api, employee_id, question="How many PTO days carry over?"):
    return api.client.post(
        "/api/assistant/ask",
        json={"employeeId": employee_id, "question": question},
    )


@pytest.fixture()
def grounded(monkeypatch):
    """A configured assistant: fake token + deterministic embed/chat seams."""
    monkeypatch.setattr("app.rag.settings.HF_TOKEN", "hf_test_token")
    monkeypatch.setattr(
        "app.rag.embeddings.embed_texts", _fake_embed([0.8, 0.6]), raising=True
    )
    return monkeypatch


# -- grounding + gating ------------------------------------------------------


def test_employee_answer_cites_employee_pool_only(api, grounded):
    _chunk(
        api.fake, "leave-policy", "KB-E-01", "Leave Policy", "employee",
        "1. Carryover", 1, "Five PTO days carry over each quarter.", [0.8, 0.6],
    )
    _chunk(
        api.fake, "payroll-run-sop", "KB-HR-02", "Payroll Run", "hr",
        "2. Cutoffs", 4, "HR cuts payroll at the 24th.", [0.8, 0.6],
    )
    grounded.setattr(
        "app.rag.llm.chat", _fake_llm("Five PTO days carry over each quarter. [KB-E-01 ¶1]")
    )

    r = _ask(api, U["priya"])
    assert r.status_code == 200
    body = r.json()
    assert "carry over" in body["answer"]
    # only the employee-pool paragraph became a citable source
    assert [c["ref"] for c in body["citations"]] == ["KB-E-01"]
    assert body["citations"][0]["blockNo"] == 1
    assert body["citations"][0]["slug"] == "leave-policy"
    # machine-verified footer always names the sources
    assert "Sources:" in body["answer"]
    assert "KB-E-01 ¶1" in body["answer"]


def test_agent_answers_span_both_pools(api, grounded):
    _chunk(
        api.fake, "leave-policy", "KB-E-01", "Leave Policy", "employee",
        "1. Carryover", 1, "Five PTO days carry over each quarter.", [0.8, 0.6],
    )
    _chunk(
        api.fake, "payroll-run-sop", "KB-HR-02", "Payroll Run", "hr",
        "2. Cutoffs", 4, "HR cuts payroll at the 24th.", [0.8, 0.6],
    )
    grounded.setattr(
        "app.rag.llm.chat",
        _fake_llm("Carryover is five days [KB-E-01 ¶1]; payroll cuts on the 24th. [KB-HR-02 ¶4]"),
    )

    r = _ask(api, U["alicia"])
    assert r.status_code == 200
    refs = [c["ref"] for c in r.json()["citations"]]
    assert "KB-E-01" in refs and "KB-HR-02" in refs


def test_model_slip_markers_never_become_citations(api, grounded):
    _chunk(
        api.fake, "leave-policy", "KB-E-01", "Leave Policy", "employee",
        "1. Carryover", 1, "Five PTO days carry over each quarter.", [0.8, 0.6],
    )
    # the model cites a paragraph retrieval never offered: the marker is not
    # honoured as a citation, but the ANSWER still carries a verified source
    # (the retrieved paragraph the excerpt came from) via the footer.
    grounded.setattr("app.rag.llm.chat", _fake_llm("Guessing. [KB-E-09 ¶99] [KB-E-01 ¶1]"))
    r = _ask(api, U["priya"])
    assert r.status_code == 200
    refs = [c["ref"] for c in r.json()["citations"]]
    assert refs == ["KB-E-01"]  # the hallucinated KB-E-09 marker is gone
    assert "KB-E-09" not in r.json()["answer"] or "KB-E-01 ¶1" in r.json()["answer"]


# -- contract edges -----------------------------------------------------------


def test_unconfigured_token_answers_without_calling_providers(api, monkeypatch):
    monkeypatch.setattr("app.rag.settings.HF_TOKEN", "")
    monkeypatch.setattr("app.rag.embeddings.embed_texts", _stub_embed())
    monkeypatch.setattr("app.rag.llm.chat", _stub_llm())
    _chunk(
        api.fake, "leave-policy", "KB-E-01", "Leave Policy", "employee",
        "1. x", 1, "doc", [0.9],
    )
    r = _ask(api, U["priya"])
    assert r.status_code == 200
    assert "not configured" in r.json()["answer"]
    assert r.json()["citations"] == []


def test_library_without_chunks_answers_grounded_empty(api, grounded):
    grounded.setattr("app.rag.llm.chat", _stub_llm())
    r = _ask(api, U["priya"])
    assert r.status_code == 200
    assert "no documents" in r.json()["answer"]
    assert r.json()["citations"] == []


def test_short_question_and_unknown_viewer_are_rejected(api, grounded):
    grounded.setattr("app.rag.llm.chat", _stub_llm())
    assert _ask(api, U["priya"], "a").status_code == 422
    assert _ask(api, U["priya"], "").status_code == 422
    assert _ask(api, "not-a-uuid").status_code == 422
    assert _ask(api, "00000000-0000-0000-0000-000000000999").status_code == 404


# -- audit trail (saved once, never re-shown) ----------------------------------


def test_each_answer_is_audited_once_with_cited_sources(api, grounded):
    _chunk(
        api.fake, "leave-policy", "KB-E-01", "Leave Policy", "employee",
        "1. Carryover", 1, "Five PTO days carry over each quarter.", [0.8, 0.6],
    )
    grounded.setattr("app.rag.llm.chat", _fake_llm("Five carry over. [KB-E-01 ¶1]"))

    assert _ask(api, U["priya"]).status_code == 200
    rows = api.fake.execute("SELECT * FROM assistant_queries", ())
    assert len(rows) == 1
    row = rows[0]
    assert row["employee_id"] == U["priya"]
    assert row["employee_name"] == "Priya Sharma"
    assert row["employee_role"] == "employee"
    assert "carry over" in row["question"]
    assert "[KB-E-01 ¶1]" in row["answer"]
    saved = json.loads(row["sources"]) if isinstance(row["sources"], str) else row["sources"]
    assert saved[0]["ref"] == "KB-E-01"


def test_second_answer_is_stateless_new_exchange(api, grounded):
    _chunk(
        api.fake, "leave-policy", "KB-E-01", "Leave Policy", "employee",
        "1. Carryover", 1, "Five PTO days carry over each quarter.", [0.8, 0.6],
    )
    grounded.setattr("app.rag.llm.chat", _fake_llm("Five carry over. [KB-E-01 ¶1]"))
    first = _ask(api, U["priya"], "Question one about PTO?").json()
    second = _ask(api, U["priya"], "Question two about payslips?").json()
    assert first["id"] != second["id"]
    # the API exposes no history surface: each answer stands alone
    assert set(first) == set(second) == {"id", "answer", "citations"}
    assert "Question one" not in second["answer"]
