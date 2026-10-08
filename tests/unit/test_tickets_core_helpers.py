import uuid as uuidlib

import pytest
from fastapi import HTTPException
from postgrest.exceptions import APIError

from app.repositories.base import run, unwrap
from app.repositories.ticket_repository import ticket_ref


class _Boom:
    def __init__(self, code):
        self._code = code

    def execute(self):
        raise APIError({"message": "constraint boom", "code": self._code})


def _api_error(code, message="boom"):
    return APIError({"message": message, "code": code})


def test_ticket_ref_uuid_routes_to_id_column():
    uid = str(uuidlib.uuid4())
    assert ticket_ref(uid) == ("id", uid)


def test_ticket_ref_numeric_becomes_tkt_prefix():
    assert ticket_ref("123") == ("ref", "TKT-123")


def test_ticket_ref_explicit_ref_stays():
    assert ticket_ref("TKT-123") == ("ref", "TKT-123")


def test_ticket_ref_garbage_gets_prefixed():
    assert ticket_ref("abc!") == ("ref", "TKT-abc!")


def test_unwrap_tuple():
    data = [{"x": 1}]
    assert unwrap((data, 5)) is data


def test_unwrap_container():
    assert unwrap({"id": 1}) == {"id": 1}
    assert unwrap([1, 2]) == [1, 2]


def test_unwrap_api_response_like():
    class R:
        data = [{"y": 2}]

    assert unwrap(R()) == [{"y": 2}]


def test_unwrap_none_falls_back():
    assert unwrap(None) is None


def test_constraint_error_maps_to_400():
    with pytest.raises(HTTPException) as exc:
        run(_Boom("23503"))
    assert exc.value.status_code == 400
    assert "Database rejected the write" in exc.value.detail


def test_other_db_error_maps_to_502():
    with pytest.raises(HTTPException) as exc:
        run(_Boom("XX999"))
    assert exc.value.status_code == 502


def test_code_attribute_exists_as_empty_string():
    err = _api_error("", "no code")
    assert err.code == ""
    assert err.message == "no code"
