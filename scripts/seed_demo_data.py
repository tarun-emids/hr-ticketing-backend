"""Seed showcase data for the admin analytics: 40 tickets over the last
~30 days, 25 of them solved (20 Resolved + 5 Closed), created by all three
demo employees across all six categories, assigned across the three agents,
with hour-of-day stamps so the console's peak-activity heatmap has real
shape.

Timings follow the priority SLA targets the console reports (Urgent 8h,
High 24h, Medium 48h, Low 72h) — three rows deliberately breach so the
SLA-compliance gauge is not a flat 100%.

Run AFTER provision_users.py — every row keys off the 7 seeded accounts.

Every demo row is marked: subjects start with "(DEMO) ". A previous demo set
is REPLACED automatically (replies/notifications die with the ticket rows via
FK cascade — set one goes with it), so a plain run always yields exactly one
fresh set; real tickets are never touched.

Usage:
    python scripts/seed_demo_data.py            # seed (replaces old demo set)
    python scripts/seed_demo_data.py --replace  # same thing, still accepted
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")
import psycopg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MARK = "(DEMO) "
EMPLOYEES = ("priya@acme.com", "marcus@acme.com", "dana@acme.com")
EMP_ID = {"priya": EMPLOYEES[0], "marcus": EMPLOYEES[1], "dana": EMPLOYEES[2]}
AGENTS = {"alicia": "alicia@acme.com", "ben": "ben@acme.com", "ruth": "ruth@acme.com"}

# One row per demo ticket:
#   (employee, category, priority, status, agent|None, days_ago, hour,
#    reply_after_days, solve_after_days, subject suffix, description)
# creation is stamped days_ago days back at hour o'clock (UTC), so the
# heatmap sees a working-day-shaped spread: 09-11h and 14-17h peaks.
# reply/solve delays are fractions of a day; solve_after_days is only used
# for Resolved/Closed rows and must place resolved_at before now.
PLAN = [
    # --- payroll -----------------------------------------------------------
    (
        "priya",
        "Payroll",
        "High",
        "Resolved",
        "alicia",
        18,
        10,
        0.9,
        1.1,
        "Payslip shows the wrong tax band",
        "This month's payslip puts me in the wrong tax band; take-home is lower "
        "than last month and I filed no declaration change.",
    ),
    (
        "marcus",
        "Payroll",
        "Medium",
        "Resolved",
        "ben",
        16,
        14,
        0.4,
        2.05,
        "Weekend payday: when does December salary land?",
        "Salary date falls on a weekend; please confirm the disbursement weekday "
        "and whether I must refresh my bank record.",
    ),
    (
        "dana",
        "Payroll",
        "Medium",
        "Resolved",
        "ruth",
        13,
        11,
        0.05,
        0.6,
        "Payslip missing the transport allowance line",
        "The transport allowance line is absent from this month's payslip; it "
        "was present last month and my commute status did not change.",
    ),
    (
        "priya",
        "Payroll",
        "Low",
        "Closed",
        "alicia",
        26,
        9,
        0.2,
        3.2,
        "Investment declaration proof deadline",
        "When does the proof-submission window close and which house-rent and "
        "medical formats do payroll actually accept for the receipts?",
    ),
    (
        "marcus",
        "Payroll",
        "High",
        "In Progress",
        "ben",
        3,
        16,
        0.05,
        None,
        "HRA segment is missing from this month's payslip",
        "My housing allowance segment is entirely missing from the current "
        "payslip and the net pay looks proportionally short.",
    ),
    (
        "dana",
        "Payroll",
        "Urgent",
        "Resolved",
        "ben",
        8,
        9,
        0.03,
        0.5,
        "Loan repayment deducted twice from salary",
        "The recurring loan repayment was deducted twice this month; I cannot "
        "afford the duplicate adjustment without a correction.",
    ),
    (
        "priya",
        "Payroll",
        "Medium",
        "Waiting on Employee",
        "alicia",
        2,
        15,
        0.6,
        None,
        "Provident fund transfer status on the new account",
        "My previous employer's provident fund balance has not arrived in the "
        "new account yet; my new member id is attached to the ticket.",
    ),
    (
        "marcus",
        "Payroll",
        "Low",
        "Open",
        None,
        1,
        10,
        None,
        None,
        "Performance bonus encashment date this quarter",
        "Raising ahead of planning: when is this quarter's performance bonus "
        "encashment date, and who confirms the payout window per team?",
    ),
    # --- leave -------------------------------------------------------------
    (
        "dana",
        "Leave",
        "Medium",
        "Resolved",
        "ruth",
        20,
        11,
        0.08,
        0.35,
        "Compensatory off for the weekend deployment",
        "Worked the full weekend on the quarterly release freeze; requesting "
        "compensatory off per the one-day-per-day-worked rule.",
    ),
    (
        "priya",
        "Leave",
        "Medium",
        "Resolved",
        "alicia",
        14,
        10,
        0.3,
        1.2,
        "What is my total leave entitlement this year?",
        "I want the full year's picture: how earned, casual and sick leave "
        "build up per month for my band, plus the carry-forward cap above them.",
    ),
    (
        "marcus",
        "Leave",
        "Medium",
        "Resolved",
        "alicia",
        12,
        16,
        0.1,
        0.9,
        "What is my total leave entitlement this year?",
        "The leave grid never states the annual bucket; send me my total "
        "entitlement with the monthly accrual and what carries into January.",
    ),
    (
        "dana",
        "Leave",
        "Low",
        "Closed",
        "ruth",
        24,
        15,
        0.25,
        2.8,
        "Leave encashment rules at exit",
        "For the exit checklist I need the exact encashment rule: which balances "
        "are encashable at separation and how the per-day rate is computed.",
    ),
    (
        "priya",
        "Leave",
        "High",
        "Waiting on Employee",
        "ben",
        4,
        13,
        0.5,
        None,
        "Sickness certificate upload failed on the leave panel",
        "The leave panel rejects my medical certificate upload; the file is a "
        "standard PDF well below the stated size limit.",
    ),
    (
        "marcus",
        "Leave",
        "Medium",
        "In Progress",
        "ruth",
        5,
        17,
        0.2,
        None,
        "What is my total leave entitlement this year?",
        "Joined mid-year and my tracker shows fewer days than my colleagues; "
        "I need the pro-rated entitlement for my band plus the carry-forward rule.",
    ),
    (
        "dana",
        "Leave",
        "Low",
        "Open",
        None,
        0,
        10,
        None,
        None,
        "What is my total leave entitlement this year?",
        "Raising so the grid reflects my band: what is my total leave "
        "entitlement for this year and how is a half-day cut counted against it?",
    ),
    # --- benefits ------------------------------------------------------------
    (
        "priya",
        "Benefits",
        "Urgent",
        "Resolved",
        "alicia",
        23,
        9,
        0.05,
        0.32,
        "Insurance card not generated after enrolment",
        "Finished my benefits enrolment weeks ago but my health insurance card "
        "still shows as pending in the portal and the provider cannot find my record.",
    ),
    (
        "dana",
        "Benefits",
        "Medium",
        "Resolved",
        "alicia",
        19,
        14,
        0.7,
        2.2,
        "Insurance card not generated after enrolment",
        "Enrolment finished in the second week but the provider portal cannot "
        "find my record and the card generator keeps answering pending.",
    ),
    (
        "marcus",
        "Benefits",
        "Low",
        "Closed",
        "alicia",
        27,
        16,
        0.3,
        3.5,
        "Wellness reimbursement annual cap",
        "The wellness portal rejected two of my claims; I need the annual "
        "reimbursement figure and the receipts that actually qualify.",
    ),
    (
        "priya",
        "Benefits",
        "Medium",
        "Resolved",
        "ben",
        10,
        15,
        0.06,
        0.5,
        "Which clinics are inside the network list?",
        "The provider directory on the portal has not an updated list; confirm "
        "whether the clinics near my office are inside the network.",
    ),
    (
        "dana",
        "Benefits",
        "High",
        "In Progress",
        "ben",
        6,
        11,
        0.4,
        None,
        "Counselling sessions available under the EAP",
        "I want to use the employee assistance programme for counselling; how "
        "many sessions are covered and how is confidentiality handled?",
    ),
    (
        "marcus",
        "Benefits",
        "Medium",
        "Resolved",
        "ruth",
        4,
        10,
        0.25,
        1.4,
        "Retirement fund statement for the year",
        "My retirement fund portal login is fine but the annual statement "
        "button errors out; I need the consolidated statements for the financial year.",
    ),
    (
        "priya",
        "Benefits",
        "Low",
        "Open",
        None,
        0,
        9,
        None,
        None,
        "Gym reimbursement claim form link broken",
        "The gym reimbursement claim form link on the benefits page opens a "
        "404; raising it until the link is repaired.",
    ),
    (
        "dana",
        "Benefits",
        "Medium",
        "Waiting on Employee",
        "ruth",
        2,
        12,
        0.3,
        None,
        "Insurance card not generated after enrolment",
        "Raised this before and the earlier answer closed the case; my card is "
        "still pending, the portal shows enrolment incomplete, nothing moved.",
    ),
    (
        "marcus",
        "Benefits",
        "Low",
        "Resolved",
        "alicia",
        21,
        17,
        0.15,
        0.7,
        "Insurance card not generated after enrolment",
        "Joined three weeks back; portal confirms active coverage but the card "
        "never arrived and the provider cannot locate my enrolment record.",
    ),
    # --- onboarding ----------------------------------------------------------
    (
        "marcus",
        "Onboarding",
        "High",
        "Resolved",
        "ben",
        22,
        10,
        0.1,
        0.6,
        "Laptop login access missing on day one",
        "Joined this morning; the laptop boots but I have no AD login or VPN "
        "credentials and cannot reach any team tooling.",
    ),
    (
        "dana",
        "Onboarding",
        "Medium",
        "Resolved",
        "ben",
        17,
        14,
        0.45,
        1.6,
        "Buddy assignment never happened at induction",
        "Two weeks in and no buddy contact happened through the induction "
        "process; requesting the assignment now for the manager checklist.",
    ),
    (
        "priya",
        "Onboarding",
        "Low",
        "Closed",
        "ben",
        28,
        11,
        0.2,
        2.4,
        "Welcome kit missing the stock milestones sheet",
        "The welcome kit arrived without the printed milestones sheet other "
        "joiners received; either send it or point me to the PDF.",
    ),
    (
        "marcus",
        "Onboarding",
        "Medium",
        "In Progress",
        "ruth",
        7,
        12,
        0.35,
        None,
        "HRIS profile shows the wrong reporting mnemonic",
        "My HRIS profile shows the wrong reporting mnemonic; two colleagues "
        "referenced that field when routing an access request that then failed.",
    ),
    (
        "dana",
        "Onboarding",
        "Low",
        "Open",
        None,
        0,
        11,
        None,
        None,
        "Background check paperwork re-submission path",
        "The background-check portal has no re-submission path after fixing "
        "one address typo; guidance on who processes it at HR would help.",
    ),
    (
        "priya",
        "Onboarding",
        "Medium",
        "Resolved",
        "ruth",
        9,
        16,
        0.15,
        0.9,
        "Probation review calendar entry missing",
        "My probation review date passed without a calendar entry or an HR "
        "mail; the portal still lists the review as upcoming.",
    ),
    # --- policy ---------------------------------------------------------------
    (
        "dana",
        "Policy",
        "High",
        "Resolved",
        "ruth",
        15,
        12,
        0.07,
        0.55,
        "Whistleblower report: how anonymous is it?",
        "I want to raise a Speak-Up report and need to know which details stay "
        "anonymous and what management can trace.",
    ),
    (
        "priya",
        "Policy",
        "Medium",
        "Resolved",
        "alicia",
        11,
        10,
        0.2,
        1.1,
        "Travel reimbursement cap for client visits",
        "The travel policy caps reimbursement per visit; confirm the per-day "
        "cap for client-site visits and which receipts count.",
    ),
    (
        "marcus",
        "Policy",
        "Medium",
        "Closed",
        "alicia",
        25,
        15,
        0.4,
        2.6,
        "Remote workdays per week for project teams",
        "My project team claims zero remote days; the policy annex says the "
        "default is different — clarify who approves exceptions and the process.",
    ),
    (
        "dana",
        "Policy",
        "Medium",
        "In Progress",
        "alicia",
        3,
        14,
        0.3,
        None,
        "Gift policy value cap for vendor token gifts",
        "A vendor wants to send a token gift; I need the exact value cap from "
        "the gift policy and the declaration path when the cap is not crossed.",
    ),
    (
        "priya",
        "Policy",
        "Low",
        "Open",
        None,
        1,
        17,
        None,
        None,
        "Casual Friday dress-code applicability for visitor floors",
        "Does the casual-day dress code carry to visitor-facing floors or "
        "only to internal floors? Two managers answered differently.",
    ),
    (
        "marcus",
        "Policy",
        "Medium",
        "Waiting on Employee",
        "ben",
        2,
        16,
        0.25,
        None,
        "Reference-check consent form before the internal move",
        "HR asked for signed reference-check consent before my internal move; "
        "the form link in the mail expired and I need a fresh one.",
    ),
    # --- other -----------------------------------------------------------------
    (
        "priya",
        "Other",
        "Low",
        "Resolved",
        "alicia",
        18,
        13,
        0.12,
        0.4,
        "Cafeteria menu feedback: more vegan options",
        "Proposing the cafeteria carries one weekly vegan option — several "
        "teammates on our floor have asked for it.",
    ),
    (
        "dana",
        "Other",
        "Low",
        "Resolved",
        "ben",
        6,
        15,
        0.15,
        0.4,
        "Month-end reminder emails: two fields missing",
        "The month-end reminder email lacks the cut-off date and the approver "
        "name; both would avoid repeated clarification rounds.",
    ),
    (
        "marcus",
        "Other",
        "Low",
        "Closed",
        "ruth",
        29,
        19,
        0.9,
        3.0,
        "Team offsite: venue suggestion request",
        "Collecting preferences for the quarterly one-day offsite within the "
        "city before we book anything.",
    ),
    (
        "dana",
        "Other",
        "Low",
        "Open",
        None,
        0,
        20,
        None,
        None,
        "Workstation chair replacement for the wing",
        "My chair's height lock failed twice last sprint and the caster keeps "
        "swinging; requesting a replacement seat from the facilities stock.",
    ),
]

AGENT_TURN = (
    "Thanks for flagging this — I can see the request in the queue and "
    "I'm checking the policy record it depends on; I'll confirm within "
    "the day.",
    "Checked with the owning team: the account record came from an older "
    "batch. I've requested a correction; the updated view lands shortly.",
    "Per the current annex: the rule caps at the stated limit and anything "
    "above is handled case by case. Want me to re-check your case against it?",
    "Good catch — one check before I take this forward: can you confirm "
    "the reference shown on your side so I line it up with the record?",
    "Welcome aboard! Your access is queued with the platform team — "
    "credentials usually go live within 4 working hours of sign-off.",
    "Confirmed — the rule allows what you're asking within the standard "
    "window. I've pre-filled the request; pick the date and it routes "
    "to your manager.",
)
EMPLOYEE_TURN = (
    "Thank you! I can also share the acknowledgement copy if needed.",
    "Great, thanks — will check on my side next week.",
    "Understood, that's reassuring. I'll proceed this week.",
    "Credentials received and working — you can close this.",
    "That clears my question completely. Thanks for confirming!",
    "Confirming my side today; the document should be valid.",
)


def _stamped(days_ago: int, hour: int, minute: int) -> datetime:
    """Creation timestamp: (today - days_ago days) at hour:minute UTC.

    Today-scheduled rows run 'today at H:o'clock'; if that instant is still
    in the future (early-morning setup runs), the row slips back one day so
    no ticket is born in the future."""
    day = datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    ) - timedelta(days=days_ago)
    if day > datetime.now(timezone.utc):
        day -= timedelta(days=1)
    return day


def main() -> int:
    load_dotenv()
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL missing — create backend/.env first.", file=sys.stderr)
        return 2
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        emails = [*EMPLOYEES, *AGENTS.values()]
        rows = cur.execute(
            "SELECT email, id FROM users WHERE email = ANY(%s)", (emails,)
        ).fetchall()
        ids = {email: str(uid) for email, uid in rows}
        missing = [e for e in emails if e not in ids]
        if missing:
            print(f"Accounts missing from the DB: {missing}", file=sys.stderr)
            print(
                "Run `python scripts/provision_users.py` first (schema.sql seeds the 7 personas).",
                file=sys.stderr,
            )
            return 1

        existing = cur.execute(
            "SELECT count(*) FROM tickets WHERE subject LIKE '(DEMO)%'"
        ).fetchone()[0]
        if existing:
            # a second run refreshes the showcase in place: the old marked
            # set dies with its replies/notifications via FK cascade, so
            # nothing duplicates
            cur.execute("DELETE FROM tickets WHERE subject LIKE '(DEMO)%'")
            print(
                f"{existing} demo ticket(s) were already created — "
                "replaced the whole set, no duplicates."
            )

        created = 0
        for i, (
            emp_key,
            cat,
            prio,
            status,
            agent_key,
            days_ago,
            hour,
            reply_after,
            solve_after,
            subject,
            desc,
        ) in enumerate(PLAN):
            ticket_id = str(uuid.uuid4())
            created_at = _stamped(days_ago, hour, minute=(i * 13) % 60)
            assignee = ids[AGENTS[agent_key]] if agent_key else None
            cur.execute(
                "INSERT INTO tickets (id, employee_id, category, subject, description,"
                " priority, status, assignee_id, created_at)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING ref",
                (
                    ticket_id,
                    ids[EMP_ID[emp_key]],
                    cat,
                    MARK + subject,
                    desc,
                    prio,
                    status,
                    assignee,
                    created_at,
                ),
            )
            ref = cur.fetchone()[0]

            if agent_key:
                # the agent answers first: minutes-to-hours after creation
                reply_at = created_at + timedelta(days=reply_after)
                cur.execute(
                    "UPDATE tickets SET first_reply_at = %s WHERE id = %s",
                    (reply_at, ticket_id),
                )
                cur.execute(
                    "INSERT INTO replies (ticket_id, author_id, author_role, body, created_at)"
                    " VALUES (%s,%s,'agent',%s,%s)",
                    (ticket_id, assignee, AGENT_TURN[i % len(AGENT_TURN)], reply_at),
                )
                if status in ("Resolved", "Closed"):
                    resolved_at = created_at + timedelta(days=solve_after)
                    if status == "Closed":
                        # the loop closes on an employee turn, then the agent
                        # signs the ticket off (closed_by + a second reply)
                        emp_turn_at = resolved_at - timedelta(hours=2)
                        cur.execute(
                            "INSERT INTO replies (ticket_id, author_id, author_role,"
                            " body, created_at) VALUES (%s,%s,'employee',%s,%s)",
                            (
                                ticket_id,
                                ids[EMP_ID[emp_key]],
                                EMPLOYEE_TURN[i % len(EMPLOYEE_TURN)],
                                emp_turn_at,
                            ),
                        )
                        cur.execute(
                            "UPDATE tickets SET resolved_at = %s, updated_at = %s"
                            ", closed_by = %s WHERE id = %s",
                            (resolved_at, resolved_at, assignee, ticket_id),
                        )
                    else:
                        cur.execute(
                            "UPDATE tickets SET resolved_at = %s, updated_at = %s WHERE id = %s",
                            (resolved_at, resolved_at, ticket_id),
                        )
                elif status == "Waiting on Employee":
                    emp_turn_at = reply_at + timedelta(days=0.25)
                    cur.execute(
                        "INSERT INTO replies (ticket_id, author_id, author_role,"
                        " body, created_at) VALUES (%s,%s,'employee',%s,%s)",
                        (
                            ticket_id,
                            ids[EMP_ID[emp_key]],
                            EMPLOYEE_TURN[(i + 3) % len(EMPLOYEE_TURN)],
                            emp_turn_at,
                        ),
                    )
            created += 1
            label = f"agent:{agent_key}" if agent_key else "unassigned"
            print(f"  {ref}  {status:<22} {emp_key:<8} {label:<15} {subject}")

        solved = sum(1 for row in PLAN if row[3] in ("Resolved", "Closed"))
        print(
            f"\nDone: {created} demo tickets inserted ({solved} solved; subjects marked '(DEMO) ')."
        )
        print("Remove the full set any time: python scripts/remove_demo_data.py")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
