"""Knowledge base seed content — HR-internal documents, part 2 (KB-HR-07..12)."""

HR_PART2 = [
    {
        "slug": "onboarding-playbook",
        "ref": "KB-HR-07",
        "title": "Offer, Onboarding & Induction Playbook (HR)",
        "category": "HR Operations & Talent",
        "audience": "hr",
        "summary": (
            "From signed offer to the 90-day checkpoint: the joiner timeline HR owns "
            "day by day, assets, buddy assignment and BGV gate-keeping."
        ),
        "keywords": (
            "onboarding, induction, offer release, joining date, welcome kit, system access, "
            "buddy, day 1, induction session, bgv, documents checklist, joiner timeline"
        ),
        "version": "v2.2",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "An assigned onboarding buddy cannot rescue a sloppy joining week — the checklist below is the guarantee. Use it as the master for every joiner; deviations (late BGV, deferred dates) are recorded in the onboarding ticket, not improvised."),
            ("h", "1. Pre-joining (T-2 weeks)"),
            ("bullets", [
                "Offer accepted → trigger HRIS record creation, email id, and the document upload link on the same day.",
                "Track BGV per the verification SOP; flag risk profile (pending originals, employer mismatch) to TA + hiring manager early.",
                "Coordinate IT: laptop, licences, application access from the role access-templates — no bespoke access creation on Day 1.",
                "Send joining logistics (reporting time, contact person, location guide) one week ahead.",
            ]),
            ("h", "2. Day 1"),
            ("table",
             ["Time", "Item", "Owner"],
             [
                 ["Morning", "Welcome, badge / access card, seat, welcome kit", "Location HR"],
                 ["Late morning", "HR induction: policies, benefits enrolment, code of conduct acknowledgement", "HR Ops"],
                 ["Afternoon", "IT set-up completion + MFA enrolment; email / chat sanity checks", "IT"],
                 ["End of day", "Manager meets the joiner; 30-60-90 goal-setting is scheduled (not necessarily complete)", "Hiring manager"],
                 ["Same day", "Onboarding ticket updated; BGV status unchanged", "HR Ops"],
             ]),
            ("h", "3. Week 1",),
            ("bullets", [
                "Buddy assigned by the manager (same org, not the manager) and logged in HRIS.",
                "Document set completed: ID proofs, education, previous employment, PF nomination, insurance dependants.",
                "Payroll cut-off aligned: the joiner appears in next-cycle input validation with a first-pay sanity check.",
                "Missing original documents: the probation-start clock notes it (see BGV SOP rules).",
            ]),
            ("h", "4. 30 / 60 / 90 checkpoints"),
            ("p", "HR owns the calendar; managers own the conversation. HR pings at T-2 days for each checkpoint, verifies the record exists, and flags systemic issues (three joiners missing a checkpoint from one manager, for example) to the business head."),
            ("h", "5. Benefits enrolment"),
            ("p", "Everything election-based (dependants, family covers) happens within the first 30 days via the benefits portal — late elections create Q1 enrolment gaps that insurers will not reopen. HR pays particular attention at the 30-day joiner audit each cycle."),
        ],
    },
    {
        "slug": "exit-process-sop",
        "ref": "KB-HR-08",
        "title": "Exit Process & Full & Final Settlement SOP (HR)",
        "category": "Exits & Transitions",
        "audience": "hr",
        "summary": (
            "The HR-side exit map: resignation intake, clearance, knowledge transfer "
            "gates, asset return and the full-and-final settlement mechanics."
        ),
        "keywords": (
            "exit process, resignation, fnf, full and final settlement, clearance, no dues, "
            "asset return, notice period buyout, gratuity, relieving letter, exit interview"
        ),
        "version": "v3.0",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "Exits convert relationships and balances into paperwork that must match the system, without exception. This SOP is the owner's manual for HR on every separation: voluntary, involuntary, abandonment, death-in-service and retrenchment-track cases."),
            ("h", "1. Resignation intake"),
            ("bullets", [
                "Resignations are acknowledged in the HR system within 1 working day of receipt; the notice period runs from acknowledgement (per probation policy), not the email date.",
                "Manager + HR partner conversation within 3 days — retention check first, then logistics.",
                "For involuntary exits (performance / conduct), documentation references the disciplinary or performance file; HR never mixes tracks.",
            ]),
            ("h", "2. The notice-period clock"),
            ("table",
             ["Item", "Standard"],
             [
                 ["Notice on probation", "15 days"],
                 ["Notice confirmed ≤ 5 years", "60 days"],
                 ["Notice confirmed > 5 years / leaders", "90 days"],
                 ["Buyout", "Employer or employee may buy out at basic+ allowances per approved matrix"],
                 ["Notice extension by leave", "Only manager-approved leave extends the clock (documented)"],
             ]),
            ("h", "3. Clearance gates (all before last working day)"),
            ("bullets", [
                "IT: device, accessories, access revocation scheduled for LWD+1; no post-LWD mailbox access.",
                "Finance: pending advances reconciled, credit cards surrendered, no open audits.",
                "Project: knowledge-transfer sign-off from the project manager.",
                "Admin: badge, parking, library / club memberships surrender.",
            ]),
            ("h", "4. Full & final settlement"),
            ("p", "F&F inputs (days worked, LOP adjustments, leave encashment at eligible balance cap, notice adjustments, settled reimbursements) are compiled by location HR and validated against the last payroll cycle. Gratuity triggers on service ≥ 5 years at the statutory rate; PF transfer / withdrawal guidance is portal-based. Settlement is processed on the next available payroll cycle after the clearance checklist completes — the effort is deliberately front-loaded so money closes fast."),
            ("h", "5. Documents issued"),
            ("p", "Relieving letter, experience letter and the F&F statement are issued within 15 working days of the LWD (gratuity in its statutory window). Letters are issued once, from the letter system — no bespoke letters in personal mailboxes; disputed wording goes back to HR review, not private edits."),
            ("h", "6. Special cases"),
            ("bullets", [
                "Abandonment: precedes the attendance SOP's AWOL protocol; a formally recorded decision letter precedes any F&F negative balance recovery.",
                "Death in service: family liaison named by HR head; gratuity / insurance proceeds initiated without waiting for clearance gates.",
                "Retrenchment-type exits: the notification and gratuity / retrenchment compensation math is a legal review item before issuance.",
            ]),
        ],
    },
    {
        "slug": "background-verification-sop",
        "ref": "KB-HR-09",
        "title": "Background Verification & Documentation SOP (HR)",
        "category": "HR Operations & Talent",
        "audience": "hr",
        "summary": (
            "What Emids verifies, through whom, with which timelines — and how to "
            "handle adverse findings, gaps and pending documents without surprises."
        ),
        "keywords": (
            "background check, bgv, adverse finding, education verification, employment verification, "
            "reference check, criminal record, pending documents, document checklist, onboarding docs"
        ),
        "version": "v1.6",
        "effective": (2025, 9, 1),
        "blocks": [
            ("p", "Emids verifies identity, education, past employment and (for eligible roles) criminal and credit records through the empanelled BGV agency before or shortly after joining. Clients in regulated engagements may require additional checks; those annex to this SOP, they do not replace it."),
            ("h", "1. Standard check matrix"),
            ("table",
             ["Check", "Applies to", "Source"],
             [
                 ["Identity (Aadhaar / PAN / passport)", "All hires", "Agency + document check"],
                 ["Education (highest qualification)", "All hires", "University / agency"],
                 ["Employment (last 3 employers or full history if < 5 yrs)", "All hires", "Agency employer reports"],
                 ["Address", "Client-mandated roles", "Agency"],
                 ["Criminal record", "Client-mandated + leadership", "Court record search"],
                 ["Credit / financial", "Finance team, certain client mandates", "Bureau report with consent"],
             ]),
            ("h", "2. Consent and disclosure"),
            ("p", "Verification runs only on written consent captured at offer stage. Candidate-declared information mismatched with reports gets a chance to explain (below); undeclared material facts are handled differently from errors."),
            ("h", "3. Handling adverse findings"),
            ("bullets", [
                "Amber (small gap, typo-level mismatch): HR confirms the correct fact in writing; corrected record attached — employment proceeds.",
                "Orange (employer dates, designation inflation, unverifiable education): escalation call to candidate + TA; documented decision by HR head; offer continuation possible for self-made junior-level factual corrections that both parties accept in writing.",
                "Red (identity fraud, fake employer, forged document, declared-false court record): rescind and blacklist from future consideration; legal consulted if already on-boarded.",
            ]),
            ("h", "4. Pending documents"),
            ("p", "Onboarding may start with up to two documents pending beyond standard originals (typically lost or out-of-print university records) only with a written undertaking in the onboarding ticket and a deadline; after the deadline without documents, the probation-note records 'BGV incomplete', which gates confirmation per the probation policy."),
            ("h", "5. Records"),
            ("p", "BGV reports, consents and explanations live in the employee file. Access is restricted to HR pod roles; reports are never emailed to hiring managers — the rating (green / amber / red) plus a one-line reason is shared instead."),
        ],
    },
    {
        "slug": "hr-ticket-sla-escalation-matrix",
        "ref": "KB-HR-10",
        "title": "HR Ticket SLA & Escalation Matrix (HR)",
        "category": "HR Operations & Talent",
        "audience": "hr",
        "summary": (
            "The working SLA for the HR Desk portal: response and resolution times per "
            "category, first-line ownership, and the escalation ladder when SLAs slip."
        ),
        "keywords": (
            "hr ticket sla, response time, resolution time, escalation matrix, ticket categories, "
            "first line support, backlog review, priority matrix, hr inbox, assignments"
        ),
        "version": "v1.4",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "Every HR ticket entering the portal is a promise made in writing. This matrix defines what that promise is — first response, resolution, priority handling — and what happens when it is missed. Employees see the response targets per category; this version additionally defines ownership and escalation."),
            ("h", "1. Category SLAs"),
            ("table",
             ["Category", "First response", "Target resolution", "First-line owner"],
             [
                 ["Payroll & payslip queries", "1 working day", "Before next credit date; urgent cases same week", "Payroll pod"],
                 ["Leave & attendance", "8 working hours", "3 working days", "HR Ops on duty"],
                 ["Benefits & insurance", "1 working day", "5 working days (claims per TPA calendar)", "Benefits admin"],
                 ["Policy / general query", "1 working day", "3 working days", "Any available agent"],
                 ["Workplace concerns / grievance", "Same working day", "Ladder per grievance SOP", "ER pod"],
                 ["Data / access / system issues", "4 working hours", "2 working days", "HR systems"],
                 ["Recruitment & internal candidates", "1 working day", "5 working days", "TA pod"],
             ]),
            ("h", "2. Priority rules"),
            ("bullets", [
                "Emergency (paid-day credit failure visible, medical / bereavement coordination, harassment-tagged): break the queue and page the pod lead immediately — SLA does not substitute for care.",
                "High priority embodies financial impact attached in the ticket by an agent or supervisor.",
                "Auto-triage is naïve: agents should correct categories on triage when the employee picked the wrong one; SLA follows the corrected category.",
            ]),
            ("h", "3. Escalation ladder"),
            ("table",
             ["Breach point", "Escalate to"],
             [
                 ["First response missed", "Pod lead (auto)"],
                 ["Resolution target missed", "Pod lead files face-up escalation note + revised commitment in the ticket"],
                 ["2 business days overdue", "HR head"],
                 ["4+ days or repeated breaches on the same category", "Business head + audit of the pod's queue"],
             ]),
            ("h", "4. Backlog and quality review"),
            ("p", "Weekly: pod leads review aging tickets and re-assignment; monthly: HR head reviews SLA report, employee satisfaction tags and reopen counts. A pattern of reopens tells the real SLA story — resolution rate by itself flatters a queue that closes without resolving."),
        ],
    },
    {
        "slug": "compensation-review-guide-hr",
        "ref": "KB-HR-11",
        "title": "Compensation Review & Increment Administration Guide (HR)",
        "category": "Compensation & Payroll",
        "audience": "hr",
        "summary": (
            "How HR runs the annual increment cycle: budgets, merit matrix, band "
            "checks, promotion comp, off-cycle corrections and manager communication."
        ),
        "keywords": (
            "compensation review, increment, merit matrix, salary band, band penetration, "
            "promotion increment, off cycle correction, compa ratio, market increment, revision"
        ),
        "version": "v2.3",
        "effective": (2026, 2, 1),
        "blocks": [
            ("p", "The increment cycle converts performance ratings into pay changes under budget and equity constraints. This guide is the HR playbook for running it cleanly; band tables and budgets live in the finance-restricted compensation working file."),
            ("h", "1. Cycle inputs"),
            ("bullets", [
                "Budget envelope and distribution guidance (differentiation by rating) come from finance + business head at cycle start.",
                "Band tables refreshed on latest market data; HR maintains the relationship between ratings and increments in the merit matrix.",
                "Eligibility: confirmed employees on the roll at the effective date; notice-period employees are eligible if the effective date falls inside their notice.",
            ]),
            ("h", "2. Merit matrix mechanics"),
            ("table",
             ["Rating", "Indicative increment band"],
             [
                 ["Exceeds", "Top of matrix (often 2× average)"],
                 ["Meets", "Around the average"],
                 ["Partially meets", "Below average or freeze; improvement plan required"],
                 ["Below", "Freeze; PIP policy track"],
             ]),
            ("h", "3. Band checks before release"),
            ("bullets", [
                "Any proposed salary above the band maximum flags outright: it comes out of band exception review, not quietly into payroll.",
                "Compa-ratio shifts larger than ±25% in one cycle need justification lines.",
                "Promotion increments sit within the new band's lower third normally, well-justified exceptions allowed.",
            ]),
            ("h", "4. Off-cycle corrections"),
            ("p", "Off-cycle salary changes come from three sources only: approved retention cases signed by business head; market-correction for an untenable band position with benchmarks attached; error corrections following unsuccessful arbitration of a payroll mistake. Retention cases go to the committee with a written case; they are the most abuse-prone channel and are audited."),
            ("h", "5. Communication discipline"),
            ("p", "HR briefs managers before letters go out: total revision, the split (fixed / variable), the effective date and what is intentionally not in the band. Managers' talking points stay with documented reasons; their personal speculations move to the grievance SOP when they surface as complaints."),
        ],
    },
    {
        "slug": "benefits-administration-manual",
        "ref": "KB-HR-12",
        "title": "Benefits & Insurance Administration Manual (HR)",
        "category": "Benefits & Insurance",
        "audience": "hr",
        "summary": (
            "The admin playbook for the employee benefits stack: enrolment cycles, "
            "insurer interfaces, claims escalation, vendor management and eligibility audits."
        ),
        "keywords": (
            "benefits administration, insurance master data, tpa coordination, claims escalation, "
            "enrolment window, dependants add, eligibility audit, renewal, sum insured, eap administration"
        ),
        "version": "v2.0",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "This manual is for the benefits pod: how master data gets to insurers, how enrolment windows work, how claims escalate, and how vendors are managed. It complements (employee-side) the Group Health Insurance guide and the Benefits Overview."),
            ("h", "1. Master data to insurer"),
            ("bullets", [
                "Monthly add / delete file (joins, dependants, exits) goes to the insurer on the 5th working day; acknowledgement tracked per employee id — never bulk-claimed as settled.",
                "Dependant records carry relationship codes from the insurer's sheet; designation-based personal email IDs are not member ids.",
                "Exits remove cover from LWD; the insurer's grace confirmations (if any) are recorded on the ticket rather than assumed.",
            ]),
            ("h", "2. Enrolment windows"),
            ("table",
             ["Event", "Window", "HR action"],
             [
                 ["New joiner elections", "30 days from joining", "Joiner audit at day 28 — personal reminders"],
                 ["Annual general window", "April (announced)", "Comm slips in employee portal; report of unchanged covers verified"],
                 ["Special (marriage / child)", "30 days from the event", "Verify documents, immediate update"],
             ]),
            ("h", "3. Claims escalation ladder"),
            ("p", "TPA ticket numbers are mandatory from day one of attempting help; escalation beyond 10 working days or a second failed response goes: TPA account manager → insurer relationship manager → benefits pod lead takes it into a physical meeting. Employee communication states the facts and next review date, never speculation on outcomes."),
            ("h", "4. Audit cadence"),
            ("bullets", [
                "Quarterly: eligibility reconciliations use payroll data vs insurer member list (active + dependants) — spurious members removed with letter trail.",
                "Renewal prep: 90 days before policy expiry, claims ratio and demographics go to finance for negotiation inputs.",
                "EAP usage: aggregate-only reporting to HR head with vendor; no individual counselling data is ever requested or accepted.",
            ]),
            ("h", "5. Employee experience standards"),
            ("p", "The benefits pod answers a benefits question in ordinary language, links the current plan sheet rather than paraphrasing it, and closes tickets with the exact next action and owner. Escalation by employees to the HR head happens when this standard is not met, and that feedback is treated as an input to the vendor review."),
        ],
    },
]
