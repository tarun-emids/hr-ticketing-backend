import pytest
from pydantic import ValidationError

from app.models import (
    AssigneeUpdate,
    CategoryUpdate,
    PriorityUpdate,
    ReplyCreate,
    StatusUpdate,
    TicketCreate,
)

VALID_TICKET = {
    "employeeId": "e1",
    "category": "Payroll",
    "subject": "Missing shift allowance",
    "description": "The payslip did not include weekend shift allowance.",
    "priority": "High",
}


def test_ticket_create_accepts_camel_case_aliases():
    m = TicketCreate.model_validate(VALID_TICKET)
    assert m.employee_id == "e1"
    assert m.subject == "Missing shift allowance"


def test_ticket_create_accepts_snake_case_too():
    m = TicketCreate.model_validate({
        "employee_id": "e1",
        "category": "Payroll",
        "subject": "Missing shift allowance",
        "description": "The payslip did not include weekend shift allowance.",
        "priority": "High",
    })
    assert m.employee_id == "e1"


def test_ticket_create_priority_defaults_medium():
    payload = {**VALID_TICKET}
    del payload["priority"]
    m = TicketCreate.model_validate(payload)
    assert m.priority == "Medium"


@pytest.mark.parametrize("priority", ["Critical", "medium", "", "1"])
def test_ticket_create_rejects_bad_priority(priority):
    with pytest.raises(ValidationError):
        TicketCreate.model_validate({**VALID_TICKET, "priority": priority})


def test_ticket_create_subject_length_bounds():
    with pytest.raises(ValidationError):
        TicketCreate.model_validate({**VALID_TICKET, "subject": "tiny"})
    with pytest.raises(ValidationError):
        TicketCreate.model_validate({**VALID_TICKET, "subject": "x" * 201})
    ok = TicketCreate.model_validate({**VALID_TICKET, "subject": "x" * 200})
    assert len(ok.subject) == 200


def test_ticket_create_description_length_bounds():
    with pytest.raises(ValidationError):
        TicketCreate.model_validate({**VALID_TICKET, "description": "too short"})
    assert TicketCreate.model_validate(
        {**VALID_TICKET, "description": "y" * 20}
    ).description == "y" * 20


def test_reply_create_bounds():
    assert ReplyCreate.model_validate({"authorId": "a", "text": "x"}).text == "x"
    with pytest.raises(ValidationError):
        ReplyCreate.model_validate({"authorId": "a", "text": ""})
    with pytest.raises(ValidationError):
        ReplyCreate.model_validate({"authorId": "a", "text": "z" * 5001})


def test_status_update_literals():
    assert StatusUpdate.model_validate(
        {"status": "Waiting on Employee", "actorId": "a"}
    ).status == "Waiting on Employee"
    with pytest.raises(ValidationError):
        StatusUpdate.model_validate({"status": "Done", "actorId": "a"})


def test_assignee_update_defaults_none():
    assert AssigneeUpdate.model_validate({}).assignee_id is None
    assert AssigneeUpdate.model_validate({"assigneeId": None}).assignee_id is None
    assert AssigneeUpdate.model_validate({"assigneeId": "a1"}).assignee_id == "a1"


def test_priority_and_category_updates():
    assert PriorityUpdate.model_validate({"priority": "Urgent"}).priority == "Urgent"
    with pytest.raises(ValidationError):
        PriorityUpdate.model_validate({"priority": "Someday"})
    assert CategoryUpdate.model_validate({"category": "Other"}).category == "Other"
    with pytest.raises(ValidationError):
        CategoryUpdate.model_validate({"category": "Wages"})


def test_constant_lists_match_frontend():
    from app.models import CATEGORIES, PRIORITIES, STATUSES

    assert CATEGORIES == ["Payroll", "Leave", "Benefits", "Onboarding", "Policy", "Other"]
    assert PRIORITIES == ["Low", "Medium", "High", "Urgent"]
    assert STATUSES == ["Open", "In Progress", "Waiting on Employee", "Resolved", "Closed"]
