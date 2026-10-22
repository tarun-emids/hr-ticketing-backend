"""Knowledge base seed content — HR-internal documents, part 1 (KB-HR-01..06).

Audience 'hr': searchable by HR agents and admins only."""
HR_PART1 = [
    {
        "slug": "payroll-processing-sop",
        "ref": "KB-HR-01",
        "title": "Payroll Processing SOP & Calendar (HR)",
        "category": "Compensation & Payroll",
        "audience": "hr",
        "summary": (
            "HR-internal month-end playbook: inputs, cut-offs, validation checks, "
            "payroll run, disbursement reconciliation and payroll-error handling."
        ),
        "keywords": (
            "payroll processing, sop, cut-off date, payroll calendar, fnf, full and final, payslip release, "
            "lop calculation, arrears, reconciliation, bank file, payroll audit"
        ),
        "version": "v3.1",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "This SOP describes how People Operations processes Indian payroll each month. It is the working standard for the payroll pod; treat exceptions (client-calendar deputations, entity changes, terminated mid-cycle runs) as deviation cases needing the payroll head's sign-off, not surprises."),
            ("h", "1. Monthly calendar"),
            ("table",
             ["Date", "Step", "Owner"],
             [
                 ["1st working day", "Attendance / LOP freeze extract from HRIS", "HR Ops analyst"],
                 ["1st–5th", "New joins, exits, transfers, salary changes loaded & checked", "HR Ops"],
                 ["6th–8th", "LOP, arrears, comp-off, overtime and regularization updates", "HR Ops + Location HR"],
                 ["9th", "Input validation meeting (ops + payroll vendor)", "Payroll lead"],
                 ["10th", "Lock input; late items move to next cycle", "Payroll lead"],
                 ["11th–17th", "Trial run 1: statutory outputs, cost-centre summaries", "Vendor"],
                 ["18th–20th", "HR-side checks: exceptions >5% pay delta; deck to finance", "Payroll lead"],
                 ["22nd", "Final run; bank file generated and reviewed", "Vendor + Finance"],
                 ["24th", "Bank file upload (mapped to disbursement date)", "Finance"],
                 ["1st next month", "Salary credit; payslip release; payroll email helpline open", "HR Ops"],
             ]),
            ("h", "2. Standing validation checks (before every final run)"),
            ("bullets", [
                "Zero-tolerance list: negative net pay; >25% delta versus last month; duplicate bank accounts across active employees; LOP >10 days without an exit/leave record.",
                "New-joiner first-pay check: proration basis, PF enrolment (EPAN present), tax regime on record.",
                "Exit reconciliation overlap: FnF files never part of the regular run — separate cycle per the exit SOP.",
                "Comp-off and overtime units only from approved tickets (no manual entries without a ticket id referenced in comments).",
            ]),
            ("h", "3. Errors after disbursement"),
            ("p", "Bank reversals and re-credits are processed in the next run with a correction memo; never adjust informally. An employee-reported pay issue is registered as a payroll ticket, triaged within 1 working day, and resolved or explained before the following credit date. A pattern of similar errors in one cycle (3+) triggers a root-cause review of the failed input."),
            ("h", "4. Statutory outputs"),
            ("p", "Each cycle closes with PF ECR, ESI contribution, PT filings, LWF and professional-tax returns, and Form-16 workings begin after the March reconciliation. Returns calendar is maintained by the compliance calendar sheet linked in the payroll network drive."),
            ("h", "5. Records"),
            ("p", "Bank files, variance memos and approval emails for every cycle are archived 8 years (statutory records retention). Employee payslips are portal-access only — HR never emails payslips, even on request; persistence gets a portal walkthrough instead."),
        ],
    },
    {
        "slug": "attendance-anomaly-handling-sop",
        "ref": "KB-HR-02",
        "title": "Attendance Anomaly & Muster Roll Handling SOP (HR)",
        "category": "HR Operations & Talent",
        "audience": "hr",
        "summary": (
            "How HR regularises swipes, handles chronic late-marking, abuse patterns "
            "and the monthly muster-roll sign-off that feeds payroll."
        ),
        "keywords": (
            "attendance, muster roll, swipe data, regularisation, late marks, biometric, "
            "lop, absent, chronic irregularity, holiday working, on call attendance"
        ),
        "version": "v1.7",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "Attendance data becomes pay data every first working day. This SOP keeps that conversion clean: what HR fixes, what HR escalates, and how the muster roll is signed off for payroll without ambiguity."),
            ("h", "1. Daily hygiene (getting clean inputs)"),
            ("bullets", [
                "Device-sync status is checked every morning; a failed sync at any site is an ops ticket the same day, not a month-end discovery.",
                "Joiners, exits, transfers and shift changes are effective-dated in the HRIS before payday, never corrected in the swipe file.",
                "Regularisation tickets from employees are reviewed and closed within 2 working days; SLA status is reviewed stand-up style each Friday.",
            ]),
            ("h", "2. Regularisation limits"),
            ("table",
             ["Pattern", "HR action"],
             [
                 ["Occasional missed swipe / WFH offline", "Approve on manager confirmation (same day)"],
                 [">4 regularisations in a month", "Manager call to the employee + documented coaching note"],
                 ["Repeated missed swipes at the same window", "Check biometric device fault before treating as an employee issue"],
                 ["Regularised hours always ≥ swipe gap", "Red flag pattern: verify with manager + access-log pulls"],
             ]),
            ("h", "3. Chronic late-coming and absence patterns"),
            ("p", "Late-mark rules (3 lates = 0.5 CL) are applied mechanically by the HRIS; HR manages the exceptions around them. A conversation — documented in the ticket — comes before an absence is treated as misconduct; expected-use discretion rests with the location HR lead, and the pattern evidence must be shareable with the employee verbatim if challenged."),
            ("h", "4. Absence without leave (AWOL) protocol"),
            ("bullets", [
                "Day 3 of unauthorised absence: call + email to registered contacts; record attempts in the ticket.",
                "Day 5: formal warning via email; exit-process trigger per the handbook.",
                "Beyond Day 5 without response: abandonment review with the business head before an exit-decision is published.",
            ]),
            ("h", "5. Muster roll sign-off"),
            ("p", "By the 3rd working day of the month, the location HR signs the monthly muster roll — a named-person endorsement that swipe data, regularisations, LOP and leave records reconcile to the system for that location. The signed sheet is stored with payroll backup; unexplained gaps between sheets and system are resolved before the payroll validation meeting."),
        ],
    },
    {
        "slug": "disciplinary-action-procedure",
        "ref": "KB-HR-03",
        "title": "Disciplinary & Corrective Action Procedure (HR)",
        "category": "HR Operations & Talent",
        "audience": "hr",
        "summary": (
            "HR's case-management standard for conduct breaches: enquiries, honesty "
            "of evidence, progressive discipline ladder, documentation and appeals."
        ),
        "keywords": (
            "disciplinary action, misconduct, enquiry, domestic enquiry, show cause, suspension, "
            "termination, corrective action, escalation, evidence, due process, appeals"
        ),
        "version": "v2.0",
        "effective": (2025, 11, 1),
        "blocks": [
            ("p", "This procedure defines how HR handles alleged misconduct with fairness to the complainant, the respondent and the company. It applies to code-of-conduct breaches; allegations of sexual harassment follow the POSH IC procedure exclusively, and grievance-related friction stays on its own track."),
            ("h", "1. Principles"),
            ("bullets", [
                "No decision on allegations without the respondent's side heard.",
                "Evidence is evaluated on documents and records, not rumour; every file must survive review by someone with an opposite view.",
                "Proportionality: corrective intent first, deterrence of recurrence, punishment only where warranted or statutorily required.",
                "Confidentiality for everyone involved, on a need-to-know basis.",
            ]),
            ("h", "2. Case flow"),
            ("table",
             ["Stage", "What happens", "Target time"],
             [
                 ["Intake", "Details recorded; interim risk assessed", "1 working day"],
                 ["Preliminary check", "Fact verification without the respondent", "3–5 working days"],
                 ["Decision to proceed / mediation / drop", "Recorded rationale either way", "1 working day after check"],
                 ["Show-cause / enquiry", "Written charge sheet, reply window, hearing where warranted", "5–15 working days"],
                 ["Outcome & action", "HR records decision, informs parties, tracks rehabilitation", "As warranted"],
             ]),
            ("h", "3. The action ladder"),
            ("bullets", [
                "Stage 1 — counselling conversation with documented follow-up date.",
                "Stage 2 — written warning with specific conduct described and expectations stated.",
                "Stage 3 — final written warning, possible suspension (up to 4 days India statutory norms / case review).",
                "Stage 4 — termination following due process, signed off by business head, HR head + legal review (where invoked).",
            ]),
            ("h", "4. Evidence discipline"),
            ("p", "Retain screen-shots, device logs, access records and communication extracts with chain-of-custody notes (who collected, when, from where). Where devices are company-issued, collection is via IT. Media shared by the complainant is preserved as received — no cropping."),
            ("h", "5. Documentation standard"),
            ("p", "Every case file: intake note, preliminary check record, charge sheet, respondent's reply, supporting evidence, decision rationale, action letter, follow-up dates. The bar is simple — an outside reader must reconstruct what happened without anybody's memory."),
            ("note", "Careful with language: describe behaviour ('used abusive language' with the quote), not personality ('tends to be arrogant'). Files outlive the people in them."),
        ],
    },
    {
        "slug": "grievance-redressal-sop",
        "ref": "KB-HR-04",
        "title": "Grievance Redressal Handling SOP (HR)",
        "category": "HR Operations & Talent",
        "audience": "hr",
        "summary": (
            "The internal playbook for managing non-statutory grievances: intake, "
            "triage, resolution, escalation thresholds and closure communication."
        ),
        "keywords": (
            "grievance, complaint handling, redressal, escalation, mediation, employees relation, "
            "grievance ticket, hr ticket sla, closure note, satisfaction"
        ),
        "version": "v1.3",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "Grievances are workplace disputes that need resolution — not just answers. This SOP separates them administratively from disciplinary matters (which follow their own procedure) from service requests (which follow the ticket SLA)."),
            ("h", "1. Intake and classification"),
            ("bullets", [
                "Any ticket with grievance or interpersonal-conflict substance is triaged to the ER (employee relations) pod within 1 working day.",
                "Conduct allegations accompany grievance tickets: classify per the disciplinary procedure once facts are初步 discernible; when unsure, ER lead decides.",
                "Compensation disputes route to payroll; they are commonly simultaneously grievance (procedural fairness) and service (accuracy) issues — open two tracks when both exist.",
            ]),
            ("h", "2. The resolution ladder"),
            ("table",
             ["Level", "Forum", "Timeline"],
             [
                 ["L1", "Manager + HR partner conversation", "5 working days"],
                 ["L2", "Formal review with ER pod; written position statements taken", "10 working days"],
                 ["L3", "HR-head review with all parties heard", "15 working days"],
                 ["Review", "Board-level / external facilitation for unresolved L3", "Case by case"],
             ]),
            ("h", "3. Standards through the process"),
            ("bullets", [
                "Both sides get versions of each other's statements; silence equals a decision without a hearing, and is not permitted.",
                "Interim safeguards (seating changes, reporting-line change) are available once allegations are on record, before any finding.",
                "Every escalation records the decision reason in writing; timelines extend only with documented consent of the involved parties.",
            ]),
            ("h", "4. Closure"),
            ("p", "Each grievance closes with a written summary to the involved parties (outcome, actions, follow-up) and a satisfaction checkout after 30 days. Complaints that return within 90 days on the same subject reopen at L2 with the previous file attached, not from scratch."),
        ],
    },
    {
        "slug": "posh-ic-operating-procedure",
        "ref": "KB-HR-05",
        "title": "POSH — Internal Committee Operating Procedure (HR)",
        "category": "Compliance & Security",
        "audience": "hr",
        "summary": (
            "The statutory working procedure for the Internal Committee: constitution, "
            "complaint intakes, inquiry steps, interim measures and annual reporting."
        ),
        "keywords": (
            "posh, internal committee, icc, statutory procedure, inquiry, interrim measures, "
            "annual report, awareness training, act 2013, external member"
        ),
        "version": "v2.4",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "Internal Committee working procedure for compliance with the Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013 and the POSH rules. This is the HR operational companion to the employee-facing POSH handbook."),
            ("h", "1. Committee constitution"),
            ("bullets", [
                "Chairperson: a senior woman employee from the workplace unit.",
                "Two member secretaries with social work / legal-aid experience.",
                "One employee committed to women's / workplace causes.",
                "One external member from an NGO or a person familiar with sexual-harassment issues.",
                "Reconstitution on any vacancy within 90 days; current rosters dated and posted at every office and on the HR portal.",
            ]),
            ("h", "2. Complaint intake"),
            ("p", "A written complaint (email suffices) reaches any IC member or the IC mailbox. The Act requires the complaint within 3 months of the incident — extensions of up to 3 more months at the IC's recorded discretion. Where the complainant is incapacitated, a relative or colleague may file with consent."),
            ("h", "3. First 7 days"),
            ("bullets", [
                "Acknowledge; provide copy of Act + rules on request.",
                "Assess interim measures: transfer of either party, seating separation, up to 3 months paid leave for the complainant if warranted, restraint on respondent access to complainant's work products.",
                "Provide the respondent with the complaint and a 10-day reply window.",
            ]),
            ("h", "4. Inquiry"),
            ("p", "Inquiry concludes within 90 days: statements, evidence, cross-examination where fair, witnesses heard. The Act's conciliation option (only at the complainant's request, before inquiry, no monetary settlement as a term) is recorded verbatim if chosen. Inquiry is quasi-judicial: notes are neutral, verbatim on critical statements, and the record is maintained by the member secretary."),
            ("h", "5. Findings and employer action"),
            ("bullets", [
                "Recommendations to employer within 10 days of inquiry close.",
                "If misconduct proved: action per service rules — warnings to termination, deductions of compensation from the respondent where recommended.",
                "If unproved / malicious: action against the complainant (and proof bar higher).",
                "Employer acts on recommendations within 60 days; the IC monitors non-retaliation for 12 months.",
            ]),
            ("h", "6. Annual compliance"),
            ("p", "Annual report filed with the district officer dated per the Act's deadline drives the annual awareness calendar. Awareness workshops for all employees and induction modules for new joiners are recorded with attendance; the compliance file retains rosters of IC members with the external member's tenure and fees paid."),
        ],
    },
    {
        "slug": "recruitment-selection-guidelines",
        "ref": "KB-HR-06",
        "title": "Recruitment & Selection Guidelines (HR)",
        "category": "HR Operations & Talent",
        "audience": "hr",
        "summary": (
            "How hiring works at Emids: requisitions, sourcing, structured interviews, "
            "offer approvals, agency and referral program administration."
        ),
        "keywords": (
            "recruitment, hiring, requisition, interview panel, interview scorecard, offer approval, "
            "talent acquisition, sourcing, agency recruitment, referral program, jd, hiring matrix"
        ),
        "version": "v2.8",
        "effective": (2026, 2, 1),
        "blocks": [
            ("p", "This guideline covers hiring at Emids Technologies from requisition to offer acceptance. It standardises how we evaluate so that hiring outcomes stay explainable, consistent with the equal-opportunity policy, and defensible."),
            ("h", "1. Getting a requisition approved"),
            ("bullets", [
                "Requisitions are raised in the ATS with headcount, budget, JD and management sign-off before sourcing begins.",
                "Contract roles carry engagement caps and require the same JD and evaluation standards.",
                "Internal-first check: every req is posted internally at least 5 working days unless the role is a confidential replacement.",
            ]),
            ("h", "2. Evaluation standard"),
            ("table",
             ["Stage", "Panel / Owner", "Expected"],
             [
                 ["Screen", "TA", "Fit-vs-JD, compensation band, availability"],
                 ["Technical round(s)", "Two and only two interviewers across rounds", "Structured scorecard, no interview-jumping between rounds"],
                 ["Value / culture round", "HR + one cross-functional interviewer", "Behaviours, not generalities — cited incidents"],
                 ["Manager close", "Hiring manager", "Debrief, ranking against standards, keep warm list"],
             ]),
            ("h", "3. Offer and approvals"),
            ("bullets", [
                "Offers within band: hiring manager approves. Above band: compensation committee (HR + finance + business head).",
                "Joining dates beyond 45 days of offer release require TA head approval (pipeline hygiene).",
                "Any negotiation beyond one explicit revision is a committee topic, not a recruiter's private commitment.",
            ]),
            ("h", "4. Referrals and agencies"),
            ("p", "Referral bonuses pay at the referred employee's 6-month milestone and split (half at 90 days for leadership roles). Agencies come in only through empanelment: fee, replacement window, invoice mechanics fixed before a CV is accepted. CV sourcing fraud — ghost submissions — voids the incentive and the engagement."),
            ("h", "5. Data and confidentiality"),
            ("p", "Candidate data lives in the ATS, retention follows the data-protection annex; interview recordings and notes are never shared with candidates. Rejected-candidate feedback is shared within 5 working days on request (India candidates)."),
        ],
    },
]
