"""Knowledge base seed content — employee policies, part 1 (KB-E-01..05).

Block types understood by the renderer (app.kb_seed.render):
    ("h", text)                 numbered section heading
    ("p", text)                 paragraph
    ("bullets", [items])        dash list
    ("table", [head], [rows])   bordered table
    ("note", text)              highlighted call-out
"""

EMPLOYEE_PART1 = [
    {
        "slug": "employee-handbook",
        "ref": "KB-E-01",
        "title": "Employee Handbook",
        "category": "Company & Culture",
        "audience": "employee",
        "summary": (
            "Start here — who Emids Technologies is, what we value, how your "
            "first days unfold, and where every other policy in this library connects."
        ),
        "keywords": (
            "employee handbook, welcome, onboarding, culture, values, overview, "
            "induction, policies, emids technologies"
        ),
        "version": "v3.0",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "Welcome to Emids Technologies. This handbook is the front door to working at Emids: it explains who we are, what we stand for, and where to find the details for every situation you are likely to meet during your employment. The individual policies it points to are published in the knowledge base; where they overlap, the specific policy prevails over this overview."),
            ("h", "1. Who we are"),
            ("p", "Emids Technologies is a healthcare technology and services company that helps payers, providers and life-science clients reimagine care through data, engineering and operations. Our teams work across delivery centres and client engagements in North America and India. What ties us together is our purpose: enabling better health outcomes by doing our part for the healthcare ecosystem."),
            ("h", "2. Our values"),
            ("bullets", [
                "Client outcome first — we measure ourselves by the change we create for the people our healthcare systems ultimately serve.",
                "Own it like yours — we take end-to-end responsibility for our work and are transparent about progress and problems.",
                "Grow by growing others — knowledge is shared deliberately: reviews, documentation, mentoring and honest feedback.",
                "Integrity without exceptions — we do the right thing even when no one is watching, especially in data and compliance.",
            ]),
            ("h", "3. Your first days"),
            ("table",
             ["Window", "What happens", "Where to read more"],
             [
                 ["Day 1", "Welcome kit, system access, buddy assigned, HR induction session", "Offer, Onboarding & Induction (HR internal)"],
                 ["Week 1", "Role orientation, project allocation, goal-setting conversation with your manager", "Probation & Confirmation (KB-E-14)"],
                 ["First 30 days", "Learning track assigned, 30-60-90 goals agreed and recorded", "Learning & Development (KB-E-16)"],
                 ["End of probation", "Confirmation review based on goals and feedback", "Probation & Confirmation (KB-E-14)"],
             ]),
            ("h", "4. How to get help"),
            ("p", "Raise an HR ticket from the HR Desk portal for anything HR-related — payroll, leave, benefits, policy questions or workplace concerns. Tickets route to the right specialist with a defined response time; you can follow up directly in the ticket thread. For time-sensitive emergencies (for example, a medical emergency on site), call your site HR contact listed during induction."),
            ("p", "Your day-to-day questions are often answered faster in the knowledge base: use the search on the home dashboard to find any policy. If a document is restricted to HR, you will see that it is not available to you rather than hitting an error."),
            ("h", "5. Keeping this handbook current"),
            ("p", "Policies change as the company and the law change. The knowledge base shows the effective date and version on every document; when a policy changes materially, HR announces it and updates the document here. Printing or forwarding PDFs from this library defeats that purpose — bookmark the search instead."),
            ("note", "Nothing in this handbook creates a contract of employment or alters its terms. Specific arrangements are set out in your offer letter / employment agreement."),
        ],
    },
    {
        "slug": "code-of-conduct-policy",
        "ref": "KB-E-02",
        "title": "Code of Conduct & Workplace Ethics",
        "category": "Company & Culture",
        "audience": "employee",
        "summary": (
            "The standards of behaviour we hold ourselves to at work, at client sites "
            "and online — integrity, respect, confidentiality and conflict-of-interest rules."
        ),
        "keywords": (
            "code of conduct, ethics, behaviour, respect, conflict of interest, gifts, "
            "business ethics, dress code, workplace behaviour"
        ),
        "version": "v2.1",
        "effective": (2025, 10, 1),
        "blocks": [
            ("p", "This code applies to every Emids employee, permanent or contractual, at our offices, client sites, off-sites and in any virtual space where you represent Emids. It sits on top of — never instead of — the law and your employment agreement."),
            ("h", "1. Integrity in our work"),
            ("bullets", [
                "Represent your skills, credentials and the effort involved in your work accurately.",
                "Never falsify, backdate or selectively edit records: timesheets, expense claims, test results, timesheet approvals, client reports.",
                "Do not accept or give other people's credit for work; acknowledge contributions honestly.",
            ]),
            ("h", "2. Conflicts of interest"),
            ("p", "Avoid any situation where your personal interest could interfere — or appear to interfere — with Emids' interest. Outside employment, board positions, equity in competitors and hiring or supervising a close relative all need prior written disclosure to HR. Once disclosed we will work out safeguards together; hiding a conflict is the breach, not the situation itself."),
            ("h", "3. Gifts and entertainment"),
            ("p", "Goodwill gestures up to a nominal value (about ₹1,000 / USD 25 per occasion) are acceptable. Anything beyond that, cash or cash equivalents, or gifts connected to a live deal or evaluation must be declined or disclosed to HR within three working days. The same limits apply to what we offer clients and partners."),
            ("h", "4. Respect and safety"),
            ("p", "We treat colleagues, clients, vendors and visitors with courtesy regardless of seniority. Harassment, bullying, discriminatory remarks and intimidation violate this code and are handled under the Prevention of Sexual Harassment (POSH) — Employee Handbook (KB-E-18) and the grievance policy. Violence or threats of violence lead straight to disciplinary action."),
            ("h", "5. Information and duty of care"),
            ("bullets", [
                "Treat client, patient and company information as confidential; share it only with people who need it for their work.",
                "Follow the IT Assets & Acceptable Use Policy (KB-E-17) for systems, devices and data handling.",
                "Do not speak for the company to media, investors or analysts unless you are authorised to do so.",
            ]),
            ("h", "6. Workplace presence"),
            ("p", "Dress for your day: client-facing days require business or business-casual attire, delivery floors accept smart casual, and client dress codes override ours when you are on their site. Office spaces, behaviours on video calls and messaging channels should stay professional."),
            ("h", "7. What happens when this code is breached"),
            ("p", "Suspected breaches can be raised with your manager, HR, or through the Speak-Up & Whistleblower Policy (KB-E-04) where you prefer confidentiality. Cases are handled under the Disciplinary & Corrective Action Procedure; retaliation against anyone reporting in good faith is itself a severe violation."),
            ("note", "When in doubt, ask: a plain question to your manager or HR officer is always cheaper than a misconduct finding later."),
        ],
    },
    {
        "slug": "equal-opportunity-policy",
        "ref": "KB-E-03",
        "title": "Equal Opportunity & Anti-Discrimination Policy",
        "category": "Company & Culture",
        "audience": "employee",
        "summary": (
            "Our commitment to fair, merit-based decisions in hiring, pay, promotion, "
            "training and every other employment decision — and how to raise a concern."
        ),
        "keywords": (
            "equal opportunity, anti discrimination, eeo, diversity, inclusion, fairness, "
            "hiring, pay equity, promotion, accessibility"
        ),
        "version": "v2.0",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "Emids Technologies provides equal opportunity in every aspect of employment: hiring, onboarding, pay, benefits, training, transfer, promotion, discipline and exit. Decisions are made on capability, performance and conduct — nothing else."),
            ("h", "1. Our commitment"),
            ("p", "We do not discriminate on the basis of race, colour, religion, caste, sex, gender identity or expression, sexual orientation, pregnancy, marital or family status, disability, age, national origin, veteran status or any other characteristic protected by the law that applies to you. Harassment or victimisation linked to any of these is treated under the disciplinary policy as serious misconduct."),
            ("h", "2. What this looks like in practice"),
            ("bullets", [
                "Job postings, interview questions and evaluation sheets are standardised so candidates are compared on the same criteria.",
                "Pay ranges are set by role and level; adjustments need a documented business or market reason.",
                "Meeting times, lighting, workstations and leave practices are flexible enough that caregivers, employees with disabilities and employees observing religious obligations can perform fully.",
                "Reasonable accommodation requests for disabilities or chronic illness are handled by HR confidentially and without you needing to justify your worth for it.",
            ]),
            ("h", "3. Raising a concern"),
            ("p", "If you feel you have been treated unfairly on any protected ground, raise it in an HR ticket, with any HR contact, or through your manager. You may also use the Speak-Up & Whistleblower Policy (KB-E-04) if you prefer confidentiality or are reporting someone senior. Concerns are investigated without you being required to first confront the person involved."),
            ("h", "4. No retaliation"),
            ("p", "No one may be punished — formally or informally — for raising a good-faith concern, supporting an investigation or refusing an instruction that breaches this policy. HR monitors outcomes for at least 12 months after a complaint to make sure nothing shifts quietly against the complainant."),
            ("note", "Managers: this policy makes you personally accountable for the fairness of decisions on your team. When scoring reports or forming panels, document your reasoning — it is reviewed if the decision is later challenged."),
        ],
    },
    {
        "slug": "speak-up-whistleblower-policy",
        "ref": "KB-E-04",
        "title": "Speak-Up & Whistleblower Policy",
        "category": "Compliance & Security",
        "audience": "employee",
        "summary": (
            "How to report financial, integrity, safety, data or conduct concerns "
            "safely — reporting channels, anonymity, investigation and anti-retaliation."
        ),
        "keywords": (
            "whistleblower, speak up, report misconduct, fraud, hotline, anonymous reporting, "
            "ethics line, retaliation, investigation, compliance"
        ),
        "version": "v1.4",
        "effective": (2025, 7, 1),
        "blocks": [
            ("p", "Most issues are best raised openly through your manager or HR. This policy exists for the ones that are not: concerns you cannot comfortably raise on your own because they involve seniority, confidentiality or the possibility that the normal channels themselves are part of the problem."),
            ("h", "1. What belongs here"),
            ("bullets", [
                "Financial irregularity or fraud — falsified invoices, expense abuse, fake vendors, kickbacks.",
                "Data or privacy misuse — patient or client data being shared or mishandled against policy.",
                "Legal or regulatory breach — violations of employment, health, safety or industry regulation.",
                "Conduct of concern — harassment that you could not report through the usual route, or improper instruction from a senior person.",
            ]),
            ("p", "Payroll errors, leave disputes and ordinary workplace friction are quicker through an HR ticket; the whistleblower channel is not a fast lane but a safe one."),
            ("h", "2. How to report"),
            ("table",
             ["Channel", "Best for", "Identified?"],
             [
                 ["HR Desk portal (ticket to category 'Policy')", "Most concerns, tracked response", "Identified, visible to HR team"],
                 ["Email to the Compliance mailbox (compliance@emids)", "Sensitive conduct matters", "Identified, only Compliance + Chair of Audit Committee"],
                 ["Post under sealed cover addressed to the Chair, Audit Committee, at the compliance office", "Matters involving very senior leadership", "You may remain anonymous"],
             ]),
            ("h", "3. Anonymous reports"),
            ("p", "Anonymous complaints are accepted and investigated with the same seriousness, with one caution: they are difficult to close without going back to you for detail. Where you can, share what you know precisely — dates, documents, names — and keep a personal record of what you reported and when."),
            ("h", "4. What happens next"),
            ("bullets", [
                "Acknowledgement within 5 working days; an initial assessment decides whether a full investigation is warranted.",
                "Investigations are conducted by people without a conflict of interest, with documents preserved from the start.",
                "Findings reach the disciplinary process where warranted; substantiated financial findings are also reported to the Audit Committee.",
                "You receive a closure summary — enough to know the matter was examined — without exposing others' personal data.",
            ]),
            ("h", "5. Protection against retaliation"),
            ("p", "Retaliation — demotion, exclusion, poor review outcomes, transfers used as punishment — for an honest report is itself serious misconduct and is treated as a separate complaint. This protection extends to witnesses and to people who participate in investigations of others' reports. Recommendations made with malicious intent or knowingly false information are not protected."),
            ("note", "If you believe you are being retaliated against, say so in writing to HR immediately — the protection ratchets up the moment retaliation is alleged."),
        ],
    },
    {
        "slug": "leave-and-time-off-policy",
        "ref": "KB-E-05",
        "title": "Leave & Time-Off Policy",
        "category": "Leave & Time Off",
        "audience": "employee",
        "summary": (
            "Annual, casual, sick and special leave entitlements: how they accrue, "
            "how to apply, carry-forward and encashment rules, and approvals."
        ),
        "keywords": (
            "leave policy, annual leave, casual leave, sick leave, earned leave, vacation, "
            "carry forward, encashment, sabbatical, comp off, bereavement, maternity, paternity"
        ),
        "version": "v4.2",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "This policy sets the leave entitlements for full-time employees of Emids Technologies in India; terms for US employees are governed by their local benefits guides. Apply for leave in the HR system before it starts — retrospective applications need your manager's approval and HR sign-off."),
            ("h", "1. Entitlements at a glance"),
            ("table",
             ["Leave type", "Annual entitlement", "Key rules"],
             [
                 ["Annual / Earned Leave (EL)", "18 days", "Accrues 1.5 days per month; apply at least 10 days ahead"],
                 ["Casual Leave (CL)", "6 days", "Max 3 days at a stretch; cannot be combined with EL"],
                 ["Sick Leave (SL)", "8 days", "2+ consecutive days require a medical certificate"],
                 ["Maternity Leave", "26 weeks", "As per the Maternity Benefit Act 2013 (first two children; statutory thereafter)"],
                 ["Paternity Leave", "2 weeks", "Within 4 weeks of birth; apply via HR ticket"],
                 ["Bereavement Leave", "3 days", "Immediate family; actual leave for travel considered case by case"],
                 ["Marriage Leave", "5 days", "Once during employment; own marriage, with notice"],
                 ["Compensatory Off", "1 day per day worked", "For recognised weekend or holiday work with pre-approval; to be availed within 90 days"],
             ]),
            ("h", "2. How leave accrues and balances are maintained"),
            ("p", "Leave accrues monthly from your date of joining and is visible in your HR profile. Employees on probation accrue leave, but EL/CL can be availed during probation only with manager approval. Unused EL is carried forward up to 30 days into the next January; anything beyond that is encashed or lapsed per company rules announced each year."),
            ("h", "3. Applying and approving"),
            ("bullets", [
                "Apply in the leave system; for planned leave, raise the request at least 7 calendar days ahead.",
                "Sick leave may be applied after the fact; attach a medical certificate for 2+ consecutive days.",
                "Your manager replies within 3 working days. For 10+ continuous days or leave during notice period, HR approval is added.",
                "Project criticality is respected — managers may rearrange preferred dates within reason; the reason will be given.",
            ]),
            ("h", "4. Long breaks and sabbatical"),
            ("p", "Unpaid leave of up to 90 days, or a paid sabbatical after five years of continuous service, is possible for higher study, family care or personal reasons. Speak with your manager first, then raise an HR ticket; each case is signed off by HR and your business unit head."),
            ("h", "5. Absence without leave"),
            ("p", "Absence without an approved application or without notice is treated as unauthorized absence and is marked until regularised. 5 consecutive days of absence without response results in abandonment proceedings under the exit policy."),
            ("h", "6. Leaving the company"),
            ("p", "On separation, accrued unused EL is encashed at the per-day rate in your final settlement, subject to policy caps. Negative balances at exit are recovered from final dues."),
            ("note", "Holidays are covered separately in the Public Holidays Calendar (KB-E-06) — public holidays do not deduct from leave balances."),
        ],
    },
]
