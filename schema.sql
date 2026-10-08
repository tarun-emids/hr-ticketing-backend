-- ============================================================
-- HR Desk — Supabase schema
-- Run once in the Supabase SQL Editor (Dashboard -> SQL Editor).
-- Safe to re-run: everything is idempotent.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Users (employees + HR agents)
-- ------------------------------------------------------------
create table if not exists public.users (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  email       text not null unique,
  role        text not null check (role in ('employee', 'agent')),
  created_at  timestamptz not null default now()
);

-- ------------------------------------------------------------
-- 2. Tickets
--    - number:  human sequence used inside the reference
--    - ref:     generated "TKT-<number>", starts at TKT-101
-- ------------------------------------------------------------
create table if not exists public.tickets (
  id             uuid primary key default gen_random_uuid(),
  number         bigint generated always as identity (start with 101),
  ref            text generated always as ('TKT-' || number::text) stored unique,
  employee_id    uuid not null references public.users (id),
  category       text not null
                 check (category in ('Payroll','Leave','Benefits','Onboarding','Policy','Other')),
  subject        text not null check (char_length(subject) between 5 and 200),
  description    text not null check (char_length(description) between 20 and 10000),
  priority       text not null default 'Medium'
                 check (priority in ('Low','Medium','High','Urgent')),
  status         text not null default 'Open'
                 check (status in ('Open','In Progress','Waiting on Employee','Resolved','Closed')),
  assignee_id    uuid references public.users (id),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  first_reply_at timestamptz,
  resolved_at    timestamptz,
  closed_by      uuid references public.users (id),
  -- single optional attachment (uploaded via /tickets/{id}/attachment)
  attachment_path  text,
  attachment_name  text,
  attachment_size  bigint
);

create index if not exists idx_tickets_updated on public.tickets (updated_at desc);
create index if not exists idx_tickets_status on public.tickets (status);
create index if not exists idx_tickets_employee on public.tickets (employee_id);

-- ------------------------------------------------------------
-- 2a. Employee ticket drafts (not visible to HR as tickets)
-- ------------------------------------------------------------
create table if not exists public.ticket_drafts (
  id               uuid primary key default gen_random_uuid(),
  employee_id      uuid not null references public.users (id) on delete cascade,
  category         text not null default 'Other'
                   check (category in ('Payroll','Leave','Benefits','Onboarding','Policy','Other')),
  subject          text not null default '',
  description      text not null default '',
  priority         text not null default 'Medium'
                   check (priority in ('Low','Medium','High','Urgent')),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  attachment_path  text,
  attachment_name  text,
  attachment_size  bigint
);

create index if not exists idx_ticket_drafts_employee on public.ticket_drafts (employee_id, updated_at desc);

-- ------------------------------------------------------------
-- 3. Ticket thread (turns)
-- ------------------------------------------------------------
create table if not exists public.replies (
  id          uuid primary key default gen_random_uuid(),
  ticket_id   uuid not null references public.tickets (id) on delete cascade,
  author_id   uuid not null references public.users (id),
  author_role text not null check (author_role in ('employee', 'agent')),
  body        text not null check (char_length(body) between 1 and 5000),
  created_at  timestamptz not null default now()
);

create index if not exists idx_replies_ticket on public.replies (ticket_id, created_at);

-- ------------------------------------------------------------
-- 4. updated_at trigger (matches store.js timestamp behaviour)
-- ------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_tickets_updated on public.tickets;
create trigger trg_tickets_updated
  before update on public.tickets
  for each row execute function public.set_updated_at();

drop trigger if exists trg_ticket_drafts_updated on public.ticket_drafts;
create trigger trg_ticket_drafts_updated
  before update on public.ticket_drafts
  for each row execute function public.set_updated_at();

-- ------------------------------------------------------------
-- 5. RLS: deny all client-side access; the backend talks with the
--    service_role key which bypasses RLS. No public policies on purpose.
-- ------------------------------------------------------------
alter table public.users   enable row level security;
alter table public.tickets enable row level security;
alter table public.replies enable row level security;
alter table public.ticket_drafts enable row level security;

-- ------------------------------------------------------------
-- 6. Storage bucket for ticket attachments (private; backend reads
--    files back via signed URLs).
-- ------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('ticket-attachments', 'ticket-attachments', false)
on conflict (id) do nothing;

-- ------------------------------------------------------------
-- 7. Seed the demo users from src/data/users.js
--    (ON CONFLICT keeps re-runs safe)
-- ------------------------------------------------------------
insert into public.users (name, email, role) values
  ('Priya Sharma', 'priya@acme.com',    'employee'),
  ('Marcus Webb',  'marcus@acme.com',   'employee'),
  ('Dana Cole',    'dana@acme.com',     'employee'),
  ('Tomas Nowak',  'tomas@acme.com',    'employee'),
  ('Alicia Gomez', 'alicia.hr@acme.com','agent'),
  ('Ben Osei',     'ben.hr@acme.com',   'agent'),
  ('Ruth Meyer',   'ruth.hr@acme.com',  'agent')
on conflict (email) do nothing;

-- ------------------------------------------------------------
-- 8. In-app notifications
--    One row per (recipient, event). Message text is intentionally
--    generic — HR ticket content (subject/description/replies) must
--    never be copied into a notification row. `channel` keeps the
--    store channel-agnostic so other delivery channels can be added
--    later without reshaping this table.
-- ------------------------------------------------------------
create table if not exists public.notifications (
  id            uuid primary key default gen_random_uuid(),
  recipient_id  uuid not null references public.users (id) on delete cascade,
  ticket_id     uuid references public.tickets (id) on delete cascade,
  ticket_ref    text,
  type          text not null
                check (type in ('ticket_created','ticket_assigned',
                                'ticket_status_changed','ticket_reply','sla_breached')),
  channel       text not null default 'in_app',
  actor_name    text,
  payload       jsonb not null default '{}'::jsonb,
  message       text not null,
  read          boolean not null default false,
  created_at    timestamptz not null default now(),
  read_at       timestamptz
);

-- unread badge + dropdown listing hot paths
create index if not exists idx_notifications_recipient_created
  on public.notifications (recipient_id, created_at desc);
create index if not exists idx_notifications_recipient_unread
  on public.notifications (recipient_id) where not read;
create index if not exists idx_notifications_ticket
  on public.notifications (ticket_id);

alter table public.notifications enable row level security;
