"""TtlCache — contract tests on a controllable clock, zero sleeping.

Pins every behavior the KB integration leans on, including the expiry
boundary (an entry dies AT its deadline) and the equivalence callers
con rely on: expired and absent are indistinguishable. Tests assert
public behavior only — `_entries` stays a black box.
"""

from app.cache import TtlCache
from tests.conftest import FakeClock


def test_miss_returns_default():
    cache = TtlCache(now=FakeClock())
    assert cache.get("absent") is None  # nothing stored, nothing raised
    assert cache.get("absent", default=[]) == []  # caller-chosen default


def test_hit_returns_stored_value():
    clock = FakeClock(0.0)
    cache = TtlCache(now=clock, ttl=30)
    cache.set(("kb", ("employee",)), [{"slug": "payslip"}])
    assert cache.get(("kb", ("employee",))) == [{"slug": "payslip"}]


def test_entry_dies_at_deadline_and_stays_dead():
    clock = FakeClock(0.0)
    cache = TtlCache(now=clock, ttl=30)
    cache.set("k", "v")

    clock.advance(29)
    assert cache.get("k") == "v"  # advance(29): one second left
    clock.advance(1)
    assert clock() == 30.0  # exactly at the boundary
    assert cache.get("k") is None  # lease up: expired ≡ absent
    clock.advance(1)  # deliberately one more step
    assert cache.get("k") is None  # still dead: no resururrection


def test_reset_replaces_value_and_deadline():
    clock = FakeClock(0.0)
    cache = TtlCache(now=clock, ttl=30)
    cache.set("k", "old")
    clock.advance(20)
    cache.set("k", "new")  # re-set: fresh value, fresh lease
    clock.advance(29)  # t=49 — old entry would be dead
    assert cache.get("k") == "new"


def test_delete_is_silent_on_missing_key():
    cache = TtlCache(now=FakeClock())
    cache.delete("never-there")  # must not raise
    assert cache.get("anything") is None


def test_pool_keys_are_independent():
    employee = ("kb", ("employee",))  # keys tuple-shapes the Stage 4 will use
    staff = ("kb", ("employee", "hr"))
    cache = TtlCache(now=FakeClock())
    cache.set(employee, [1, 2])
    cache.set(staff, [1, 2, 3])
    assert cache.get(staff) == [1, 2, 3]  # distinct entries, never crossed
    cache.delete(employee)
    assert cache.get(employee) is None  # one pool invalidation...
    assert cache.get(staff) == [1, 2, 3]  # ...leaves the other untouched
