"""Repository layer — the ONLY place that touches Supabase.

Every Supabase/PostgREST query lives in one of the repository classes below;
services and controllers never build a query themselves. Repositories take the
Supabase client as a constructor argument (wired in app/deps.py), so tests can
inject an offline fake (tests/conftest.FakeSupabase) instead of the real one.
"""
