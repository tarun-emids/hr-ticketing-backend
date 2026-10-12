"""Knowledge base seed content — employee policies, part 2 (KB-E-06..09)."""

EMPLOYEE_PART2 = [
    {
        "slug": "public-holidays-calendar",
        "ref": "KB-E-06",
        "title": "Public Holidays Calendar & Locational Holidays",
        "category": "Leave & Time Off",
        "audience": "employee",
        "summary": (
            "Company public holidays for 2026, the two floating holidays you can "
            "self-select, and how locational client calendars affect your days."
        ),
        "keywords": (
            "holidays, holiday calendar, public holidays, floating holiday, optional holiday, "
            "list of holidays 2026, office holiday, day off"
        ),
        "version": "v1.6",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "Emids Technologies observes 12 public holidays a year for India offices, together with 2 floating holidays that you may use on days the office is working. US employees follow the separate US holiday guide issued by People Operations each December."),
            ("h", "1. Company-wide public holidays (calendar year 2026)"),
            ("table",
             ["Date", "Day", "Holiday"],
             [
                 ["26 Jan 2026", "Monday", "Republic Day"],
                 ["04 Mar 2026", "Wednesday", "Ramzan Id / Eid-ul-Fitr*"],
                 ["03 Apr 2026", "Friday", "Good Friday"],
                 ["14 Apr 2026", "Tuesday", "Dr. Ambedkar Jayanti"],
                 ["01 May 2026", "Friday", "Labour Day"],
                 ["15 Aug 2026", "Saturday", "Independence Day"],
                 ["28 Aug 2026", "Friday", "Ganesh Chaturthi*"],
                 ["02 Oct 2026", "Friday", "Gandhi Jayanti"],
                 ["10 Nov 2026", "Tuesday", "Deepavali"],
                 ["25 Dec 2026", "Friday", "Christmas"],
             ]),
            ("note", "*Muslim and Hindu astronomical holidays shift with moon declarations. Watch HR announcements in the last week of the prior month — the portal calendar is always authoritative."),
            ("h", "2. Floating (self-declared) holidays"),
            ("p", "Each employee picks 2 floating holidays per calendar year from the working days in the year, except during the year-end freeze (20 Dec – 2 Jan) or dates your project marks as blackout. Apply through the leave system as 'Floating Holiday'; they do not deduct from your other balances."),
            ("h", "3. Dates or days that teams may adjust"),
            ("h2", "3.1 Where client calendars differ"),
            ("p", "If your engagement follows a US, UK or APAC client calendar, your list of holidays can differ from India central list only with a documented client-calendar approval from your delivery head and HR. The approved calendar for your project is the one your manager publishes."),
            ("h2", "3.2 Work falling on a holiday"),
            ("p", "If you are asked to work on a public holiday, your manager must record the pre-approval in an HR ticket. You earn a compensatory day off (use within 90 days) or, for certain client-critical months, an equivalent day credited as comp-off."),
            ("h", "4. Calendar updates"),
            ("p", "The version here is for calendar year 2026. Amendments and next year's calendar are announced in December; if in doubt, trust the in-app calendar."),
        ],
    },
    {
        "slug": "hybrid-work-policy",
        "ref": "KB-E-07",
        "title": "Hybrid Work & Work-From-Home Policy",
        "category": "Ways of Working",
        "audience": "employee",
        "summary": (
            "Which roles work from where, minimum office presence, approval for "
            "extended remote work, working from another city and client-site rules."
        ),
        "keywords": (
            "work from home, wfh policy, hybrid work, remote work, telecommuting, flexible work, "
            "work from anywhere, office attendance, relocation, digital nomad"
        ),
        "version": "v1.8",
        "effective": (2025, 11, 1),
        "blocks": [
            ("p", "Emids works hybrid: most roles need regular office presence, some are location-flexible, and client engagements follow the client's rules. This policy explains how the three models work and how to request flexibility beyond standard practice."),
            ("h", "1. Work models at a glance"),
            ("table",
             ["Model", "Set by", "Typical presence"],
             [
                 ["On-site", "Role (infrastructure, data rooms, hardware labs)", "4–5 days per week"],
                 ["Hybrid", "Manager approved roster", "2–3 days per week, incl. team anchor days"],
                 ["Remote-flex", "Delivery / business unit head", "1 day per month unless agreed"],
             ]),
            ("h", "2. Team anchor days"),
            ("p", "Each team chooses 1–2 anchor days when everyone in that team is expected on-site — for collaboration, ceremonies and mentoring. Rosters are shared monthly; exceptions need your manager's OK before skipping."),
            ("h", "3. Requesting extended work-from-home"),
            ("p", "For personal reasons, an agreed temporary WFH stretch beyond your roster uses a temporary WFH request: raise an HR ticket with dates and a work-continuation note from your manager. Stretches of up to 15 working days ride on manager approval alone; beyond that, HR and business-head approvals apply. Chronic health needs are handled as reasonable accommodations instead."),
            ("h", "4. Working from another city or country"),
            ("bullets", [
                "India: up to 4 weeks per financial year with manager + HR approval; longer stretches are relocation decisions under the transfer policy.",
                "Outside India: needs HR, immigration and client-approval sign-off before travel; income tax, payroll and visa implications are reviewed case by case.",
                "Client-site rules always trump this policy when you are deputed there.",
            ]),
            ("h", "5. Working-day expectations wherever you work"),
            ("bullets", [
                "Be reachable within a reasonable response time during your declared working hours.",
                "Your declared workplace must stay secure: sensitive data never on shared screens or in earshot of calls made from public spaces.",
                "Company data stays on company systems — download nothing to personal drives; plugin/personal-device limits in the IT Assets & Acceptable Use Policy (KB-E-17) apply.",
                "Your internet needs to support the declared availability without constant dropouts.",
            ]),
            ("h", "6. Equipment"),
            ("p", "Company-issued laptops are handed over on joining; long-term WFH employees may also request peripherals (monitor, keyboard) delivered to their registered WFH address. Hardware support at home is self-service first, filing support ticket guidelines in the IT Assets & Acceptable Use Policy (KB-E-17)."),
            ("note", "Work-from-home is not sick leave or caregiving leave: if you are unwell or the sole carer, take the leave you are entitled to instead of claiming availability — both for your own health and your team's planning."),
        ],
    },
    {
        "slug": "attendance-working-hours-policy",
        "ref": "KB-E-08",
        "title": "Attendance & Working Hours Policy",
        "category": "Ways of Working",
        "audience": "employee",
        "summary": (
            "Working hours, flexible start windows, shift and on-call rules, biometric "
            "attendance, late marks and how attendance exceptions get regularised."
        ),
        "keywords": (
            "attendance policy, working hours, shift timing, late mark, biometric, swipe, "
            "on call, night shift, timesheet, flexible hours, core hours"
        ),
        "version": "v2.3",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "Standard full-time hours at Emids Technologies are 9 hours per day (including 1 hour break), 5 days a week. Within office and team norms, you may slide your start time within a flexible window; your team roster is the authority for exact working hours."),
            ("h", "1. Working hours and flexibility"),
            ("table",
             ["Parameter", "Standard"],
             [
                 ["Weekly hours", "40–45 hours across 5 days"],
                 ["Flexible start window", "08:00–10:30 local, end time slides accordingly"],
                 ["Team core hours", "11:00–16:00 — when overlap is expected"],
                 ["Break", "1 hour (~ any pattern: lunch + short breaks)"],
             ]),
            ("h", "2. Recording attendance"),
            ("p", "Attendance is captured by swipe / biometric at office and by badge-in on the virtual tracker for WFH days. Forgotten swipes are regularised once a month with manager confirmation — occasional forgetfulness stays out of performance conversation unless it becomes a pattern."),
            ("h", "3. Late marks, half-days and early departures"),
            ("bullets", [
                "Arriving more than 15 minutes past your rostered start is a late mark; 3 late marks in a month equal one half-day leave.",
                "Leaving a stretch 2+ hours early (with no applied leave) counts 0.5 day of Casual Leave.",
                "Client-site travel days are recorded by your manager from the client visit note.",
            ]),
            ("h", "4. Shifts and on-call"),
            ("p", "Night and shifted roles receive shift allowances per the compensation policy. On-call responsibilities require pre-agreed rotations, rest periods between shifts, and compensation as per the client contract. Night work follows statutory rules on hours, rest breaks and safety transport where they apply."),
            ("h", "5. Overtime"),
            ("p", "Non-managerial roles under eligible bands are paid or queued overtime for approved work beyond 45 hours a week; approvals come before the hours worked. Overtime is exceptional, not a default way to close gaps — pre-approved and properly recorded."),
            ("h", "6. Exceptions and regularisation"),
            ("p", "Missed swipes, offline days, client visits and travel: raise a regularisation ticket with date, facts and expected hours. Regularisations cross-checked by HR team within 5 working days, before payroll cut-off of the same month."),
            ("note", "Your login time is not a productivity metric. Presence is governed by outcomes and hours; if your hours are being recomputed wrongly, raise the ticket — the numbers matter only when they are right."),
        ],
    },
    {
        "slug": "compensation-structure-policy",
        "ref": "KB-E-09",
        "title": "Compensation Structure & Payment Policy",
        "category": "Compensation & Payroll",
        "audience": "employee",
        "summary": (
            "How salary structures are built at Emids, what each pay component means, "
            "pay dates, statutory deductions, increments and how your pay is paid."
        ),
        "keywords": (
            "compensation, salary structure, pay components, basic, hra, special allowance, "
            "variable pay, ctc, payroll, pay date, deductions, pf, tax, tds, increment"
        ),
        "version": "v3.1",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "Your total compensation (CTC) is structured by grade and role from a company-wide band table, reviewed annually against market benchmarks. This document explains the anatomy of your pay, withholding rules and how pay behaves at each change; it does not contain band numbers (available from your HR partner on request)."),
            ("h", "1. Components of your pay"),
            ("table",
             ["Component", "What it means", "Typical share"],
             [
                 ["Basic", "Fixed base pension-able salary", "30–40% of fixed"],
                 ["House Rent Allowance (HRA)", "Living / rent allowance component", "40–50% of Basic"],
                 ["Special Allowance", "Balancing fixed component", "Balance of fixed pay"],
                 ["Variable / Performance Pay", "Payout linked to level & performance cycle", "5–20% of fixed, by level"],
                 ["Retirals & benefits", "EPF employer share, gratuity provision, insurance premiums", "Over and above fixed"],
             ]),
            ("h", "2. Statutory and other deductions"),
            ("bullets", [
                "Provident Fund (EPF): employee 12% of (Basic + DA) capped by statutory wage ceiling.",
                "Professional Tax where applicable by state.",
                "TDS on salaries per your declared regime & investments; re-declaring at each cycle through the payroll portal.",
                "Voluntary programs (meal plan, NPS VCS, club membership) only with your opt-in.",
            ]),
            ("h", "3. Pay dates and payslips"),
            ("p", "Salary is paid on the 1st working day of the following calendar month (or agreed client-calendar date for deputed employees who are separately informed). Payslips appear on the payroll portal; see the Payroll Calendar & Payslip Guide (KB-E-10) for reading payslips and corrections."),
            ("h", "4. Variable pay (performance-linked)"),
            ("p", "Variable targets and the payout % per rating band are published at cycle start. Payment is on the cycle close — typically May for the annual cycle — and prorated by presence during the cycle (joiners, exits per the exit policy). Company or unit gate (for example performance of business unit modulating the pool by up to 25%) is communicated the same cycle."),
            ("h", "5. Increments and promotions"),
            ("p", "Increments take effect on your confirmation date or promotion date, whichever is latest within the annual cycle. Increment amounts flow from the merit matrix; promotion adjustments additionally in the new band. Off-cycle corrections use the salary-correction channel in the ticket portal, and ideally before the month's payroll cut-off on the 20th."),
            ("h", "6. View and correct"),
            ("p", "For clarity on any pay component, the payslip guide (KB-E-10) is the first stop, then a payroll ticket — a response on tickets is due within the SLA published in the HR Ticket SLA (HR-internal), and pay corrections are audited before they are processed."),
            ("note", "Details of your own grade, band and structure live in your offer letter and its amendments; HR can share your current structure statement at any time on request."),
        ],
    },
]
