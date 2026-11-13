<!--
HOW TO OPEN THIS PR (compare-URL flow):
1. branch:  git checkout -b feat/schema-<topic>     (or feat/<topic> for non-schema work)
2. verify:  ruff format . && ruff check . && pytest
3. commit:  git commit -m "migration: <topic> (rev 000N)"
4. rebase:  git fetch origin && git rebase origin/dev
5. push:    git push origin feat/schema-<topic>
6. open the DRAFT PR via:
   https://github.com/tarun-emids/hr-ticketing-backend/compare/dev...feat/schema-<topic>
Delete the sections that don't apply (e.g. everything "Schema change" for a
non-schema PR).
-->

## What this PR does

<!-- one or two sentences: the problem and the change -->

…

## Schema change (Alembic) — fill in for migration PRs, delete otherwise

- [ ] New revision file in `migrations/versions/` with revision id `000N`
      and correct `down_revision` (it must stack onto the CURRENT head, not
      the head when you started)
- [ ] Contains **one logical change**; no revision already merged was edited
- [ ] Both `upgrade()` and `downgrade()` written; one SQL statement per
      `op.execute()`; table order respected (dependents after `users`)
- [ ] Any new indexes/triggers follow the `0001` naming convention
- [ ] `docker compose exec backend alembic current` on a clean DB:
      previous head before, `000N` after
- [ ] `alembic upgrade head --sql` (offline output) pasted below for review
- [ ] Existing (pre-Alembic) databases verified with `make migrate-stamp`
      + `make migrate`
- [ ] Downgrade exercised at least once locally
      (`alembic downgrade -1` → re-upgrade), or marked N/A with reason
- [ ] Seed data untouched / accounted for (provision_users,
      seed_knowledge_base, seed_demo_data are separate tools)

**Offline SQL for review:**

```sql
-- paste `alembic upgrade head --sql` output here
```

**Rollback plan:** downgrading to the previous head drops/reverts …
<!-- state what a revert loses (if anything) -->

## Checklist (all PRs)

- [ ] `ruff format .` and `ruff check .` clean
- [ ] `pytest` green (integration tests need a migrated DATABASE_URL)
- [ ] No config knob read in code without a `config.py` attribute and a
      `.env.example` entry
- [ ] `README`/guides updated when behavior, endpoints or the developer
      workflow changed
- [ ] `logs/app.log` shows no new `unhandled server error` lines in a manual
      smoke of the change
