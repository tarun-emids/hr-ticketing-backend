# 3-layer refactor — project copy + how to sync it back into WSL

This folder (`C:\github\hr-ticketing-backend`) is a complete copy of the
backend refactored to controllers → services → repositories. It is the
project itself — `pytest` here once it has its own `.env` + venv — and it is
also the sync source for the WSL working repo. `.git`, `.env` and `.venv`
are untouched by the sync below; `git status` afterwards shows the refactor
as a normal, reviewable diff.

## What changed

```
BEFORE                              AFTER
app/main.py                         app/main.py                    (rewired)
app/config.py                       app/config.py                  (db() helper removed)
app/models.py                       app/models.py                  (+LoginRequest, -pickup text)
app/notifications.py  (domain+jobs) app/services/notification_service.py (+ repos)
app/routers/auth.py                 app/controllers/auth.py        + app/services/auth_service.py
app/routers/tickets_core.py         app/controllers/tickets.py     + app/services/ticket_service.py
app/routers/tickets_actions.py            (folded into the same files above)
app/routers/assignment.py                 (folded into ... + agent_workload)
app/routers/attachments.py          app/controllers/attachments.py + repo attachment_storage.py
app/routers/drafts.py               app/controllers/drafts.py      + app/services/draft_service.py
app/routers/notifications.py        app/controllers/notifications.py (+ service + repo)
app/routers/users_meta.py           app/controllers/users.py       + app/services/user_service.py
app/routers/tickets_core helpers    app/repositories/base.py       (unwrap/run/rows_of)
                 ticket_ref         app/repositories/ticket_repository.py
(new)                               app/deps.py                    (FastAPI DI graph)
(new)                               app/repositories/{user,ticket,draft,notification}_repository.py
tests/conftest.py                   patched modules list reduced to app.config (DI does the rest)
tests/unit/test_tickets_core_helpers.py   imports from app.repositories.*
tests/unit/test_notification_rules.py     imports from app.services.notification_service
scripts/provision_auth_users.py     fixed helper import + comment
README.md                           architecture section + path updates
```

Old `app/routers/*` + `app/notifications.py` become loud deprecation stubs
(importing anything from them raises ImportError pointing at the new module),
so nothing can silently keep working off the old code — and commits show the
deletion clearly.

## Run it from Windows (this folder)

```powershell
cd C:\github\hr-ticketing-backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env     # paste your SUPABASE_URL + SERVICE_ROLE_KEY
pytest                     # offline suite: the behavior-parity proof
pytest -m integration      # optional: live round-trips vs your Supabase
uvicorn app.main:app --reload --port 8000
```

## Sync this folder into the WSL working repo

From PowerShell (mirrors AND deletes — `/MIR` prunes the old `app/routers`,
old `db()` code and stale `__pycache__`; `.env`/`.venv`/`.git` are outside
every mirrored dir and never touched):

```powershell
$SRC = "C:\github\hr-ticketing-backend"
$DST = "\\wsl.localhost\Ubuntu\home\tarunr\github\hr-ticketing-backend"

robocopy "$SRC\app"     "$DST\app"     /MIR /NFL /NDL /NJH /NP
robocopy "$SRC\tests"   "$DST\tests"   /MIR /NFL /NDL /NJH /NP
robocopy "$SRC\scripts" "$DST\scripts" /MIR /NFL /NDL /NJH /NP
robocopy "$SRC" "$DST" README.md pytest.ini requirements.txt schema.sql .env.example MIGRATION.md /NFL /NDL /NJH /NP
```

Alternative from inside WSL:

```bash
cd ~/github/hr-ticketing-backend
B="/mnt/c/github/hr-ticketing-backend"
rm -rf app tests scripts
cp -r "$B/app" "$B/tests" "$B/scripts" .
cp "$B/README.md" "$B/pytest.ini" "$B/requirements.txt" "$B/schema.sql" "$B/.env.example" "$B/MIGRATION.md" .
```

## Then verify in WSL

```bash
cd ~/github/hr-ticketing-backend
git add -A && git status          # sanity: controllers/services/repositories + stubs, no .env/.venv
git diff --cached --stat          # review the refactor as a normal diff
source .venv/bin/activate
pytest                            # same test count as before, all green
uvicorn app.main:app --reload --port 8000   # boot check + /health
```

If anything fails, the most likely culprit is a path the sync missed — check
`git status` for untracked/stale files first.
