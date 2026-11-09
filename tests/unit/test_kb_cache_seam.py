"""KbService cache seam — hits, pool isolation, expiry, unknown-role guard.

Drives the service's PUBLIC endpoints with stubs for its two repository
dependencies and counts repository fetches — the number the cache is
supposed to collapse requests onto. Stubs return fresh copies per call,
so any data reuse across calls is the cache doing it, not stub state.
"""

import pytest

from app.cache import TtlCache
from app.services.kb_service import KbService, UnknownViewer
from tests.conftest import FakeClock

EMP = "11111111-1111-1111-1111-111111111111"
AGENT = "22222222-2222-2222-2222-222222222222"
ROW = {"slug": "payslip", "title": "Payslip", "audience": "employee"}


class CountingKbRepo:
    """Records every list_by_audiences call; serves fresh copies of rows."""

    def __init__(self, rows):
        self._rows = rows
        self.calls: list[tuple[str, ...]] = []

    def list_by_audiences(self, audiences, limit=200):
        self.calls.append(tuple(audiences))
        return list(self._rows)


class ReloadingUsers:
    """get_by_id returns a fresh viewer dict — mirrors real DB reads, so
    a role 'changes' are re-derived pools on every request."""

    def __init__(self, viewers):
        self._viewers = viewers

    def get_by_id(self, viewer_id):
        if viewer_id not in self._viewers:
            return None
        return {**self._viewers[viewer_id]}


def make_service(rows, viewers, clock):
    repo = CountingKbRepo(rows)
    svc = KbService(repo, ReloadingUsers(viewers), TtlCache(now=clock, ttl=30))
    return svc, repo


def test_miss_then_hit_collapses_to_one_fetch():
    clock = FakeClock(0.0)
    svc, repo = make_service([ROW], {EMP: {"role": "employee"}}, clock)

    first = svc.list_or_search(EMP)
    second = svc.list_or_search(EMP)

    assert first == second  # identical wire content either way
    assert repo.calls == [("employee",)]  # the WHOLE point: one DB fetch


def test_pool_keys_never_cross_employee_and_staff():
    clock = FakeClock(0.0)
    svc, repo = make_service(
        [ROW],
        {EMP: {"role": "employee"}, AGENT: {"role": "agent"}},
        clock,
    )

    svc.list_or_search(EMP)
    svc.list_or_search(AGENT)

    assert repo.calls == [("employee",), ("employee", "hr")]
    assert [o["audience"] for o in svc.list_or_search(EMP)] == ["employee"]
    # employee view queried LAST yet still the cached employee key, untouched


def test_entry_expires_and_refetches():
    clock = FakeClock(0.0)
    svc, repo = make_service([ROW], {EMP: {"role": "employee"}}, clock)

    svc.list_or_search(EMP)
    clock.advance(29)
    svc.list_or_search(EMP)
    assert len(repo.calls) == 1  # one second of lease left
    clock.advance(1)  # t=30: exactly at the deadline
    svc.list_or_search(EMP)
    assert len(repo.calls) == 2  # expired + refetched


def test_unknown_role_reaches_nothing():
    clock = FakeClock(0.0)
    svc, repo = make_service([ROW], {EMP: {"role": "intern"}}, clock)

    assert svc.list_or_search(EMP) == []
    assert repo.calls == []  # not even a key was formed


def test_unknown_viewer_still_no_data_served():
    clock = FakeClock(0.0)
    svc, repo = make_service([ROW], {EMP: {"role": "employee"}}, clock)

    with pytest.raises(UnknownViewer):
        svc.list_or_search(AGENT)
    assert repo.calls == []  # viewer resolution precedes any cache read


def test_list_and_popular_share_one_entry():
    clock = FakeClock(0.0)
    svc, repo = make_service([ROW], {EMP: {"role": "employee"}}, clock)

    svc.popular(EMP)
    svc.list_or_search(EMP)

    assert repo.calls == [("employee",)]  # both endpoints ride the same seam
