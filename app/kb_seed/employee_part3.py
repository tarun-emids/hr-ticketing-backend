"""Knowledge base seed content — employee policies, part 3 (KB-E-10..13)."""

EMPLOYEE_PART3 = [
    {
        "slug": "payroll-calendar-payslip-guide",
        "ref": "KB-E-10",
        "title": "Payroll Calendar & Payslip Guide",
        "category": "Compensation & Payroll",
        "audience": "employee",
        "summary": (
            "When each payroll month closes, how to read every line of your payslip, "
            "how to raise corrections and which declarations matter when."
        ),
        "keywords": (
            "payroll calendar, payslip, salary slip, pay date, cut-off, correction, tds declaration, "
            "investment proof, form 16, reimbursement, arrears, lop, loss of pay"
        ),
        "version": "v2.0",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "This guide explains how a payroll month flows at Emids and what each line on your payslip means. For the structure of your pay itself see the Compensation Structure & Payment Policy (KB-E-09)."),
            ("h", "1. Payroll calendar"),
            ("table",
             ["Milestone", "Date"],
             [
                 ["Attendance / leave freeze", "1st of the following month"],
                 ["Late join-requests & corrections lock", "10th of the following month"],
                 ["Tax declaration change window", "10th–15th of the month"],
                 ["Investment proof submission (Dec cycle)", "10 January"],
                 ["Payroll cut", "25th / last working day"],
                 ["Salary credited", "1st working day of the next month"],
             ]),
            ("note", "Missed the cut? Anything raised after the lock (missing LOP, arrears, new declaration) flows into the next payroll — arrear lines on later payslips show it."),
            ("h", "2. Reading your payslip"),
            ("table",
             ["Line", "Meaning"],
             [
                 ["Basic", "Base-salary component; pension-able"],
                 ["HRA", "House rent allowance — partly tax-exempt if you pay rent"],
                 ["Special Allowance", "Balance fixed pay"],
                 ["LOP (loss of pay)", "Day deductions from unapproved absence / non-availed leave"],
                 ["Employee PF", "Your 12% contribution (Basic + DA, capped)"],
                 ["Professional Tax", "State slabs where applicable"],
                 ["TDS / Income Tax", "Monthly withholding on projected annual computation"],
                 ["Arrears", "Retro corrections — increments, missed amounts, backdated change"],
                 ["Reimbursements", "Approved claims flowing via payroll (fuel/telecom where eligible)"],
             ]),
            ("h", "3. Declarations and proofs"),
            ("bullets", [
                "Regime selection (old / new) is re-declared each April or on joining.",
                "Investment declarations through the portal; proof release deadline is 10 January; late proofs revise TDS in Feb payroll.",
                "Rent receipts are required for HRA claims above ₹1 lakh p.a.; PAN of landlord above ₹1 lakh rent p.a.",
            ]),
            ("h", "4. Corrections and clarifications"),
            ("p", "If something looks wrong — an LOP you did not expect, missing arrear, wrong bank credit — raise a payroll ticket within the month you notice it. Successful corrections are reprocessed in the next run; Form 16 for the year reflects finalised numbers only after the March reconciliation."),
            ("h", "5. Annual tax documents"),
            ("p", "Form 16 (India) is issued from the payroll portal by end of May. US colleagues receive W-2s by 31 January. Retain payslips for your own records for at least three years."),
        ],
    },
    {
        "slug": "employee-benefits-overview",
        "ref": "KB-E-11",
        "title": "Employee Benefits Overview",
        "category": "Benefits & Insurance",
        "audience": "employee",
        "summary": (
            "The full benefits stack at Emids: insurance covers, wellness, learning "
            "stipends, referral rewards, commuting support and where each one is enroled."
        ),
        "keywords": (
            "benefits, employee benefits, insurance, wellbeing, wellness, stipend, referral bonus, "
            "commuting, meal card, perks, flex benefits, parental support"
        ),
        "version": "v2.5",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "This is the one map of everything Emids provides beyond salary. Individual programs open on enrolment dates announced by HR; amounts below are the standard plan per calendar year."),
            ("h", "1. Insurance covers"),
            ("table",
             ["Cover", "Who", "Standard sum"],
             [
                 ["Group Health Insurance (GHI)", "Employee + nominated dependants", "Family floater per plan sheet"],
                 ["Term Life / Accident", "Employee", "3× annual fixed pay"],
                 ["Personal Accident", "Employee", "2× annual fixed pay"],
                 ["Maternity Covered", "Employee (under GHI)", "Sub-limit per insurer"],
             ]),
            ("p", "Details, exclusions, enrolment windows and claim routes are in the Group Health Insurance — Employee Guide (KB-E-12)."),
            ("h", "2. Wellness"),
            ("bullets", [
                "Annual health check-up reimbursement up to the published cap, on presenting a receipt in the portal.",
                "Wellness allowance for fitness / mental-health platforms (annual, per enrolled plan).",
                "24×7 Employee Assistance Program (EAP) — confidential counselling by phone or chat.",
            ]),
            ("h", "3. Everyday support"),
            ("bullets", [
                "Meal plan through the office cafeteria / meal-card partner.",
                "Cab facility or reimbursement on late-night / shift work per office norms.",
                "Telephone & internet reimbursement for eligible delivery roles, billed monthly through the claims tool.",
            ]),
            ("h", "4. Family and life events"),
            ("bullets", [
                "Maternity / paternity / adoption leave per the Leave & Time-Off Policy (KB-E-05).",
                "Creche reimbursement where statutorily applicable and by employee request.",
                "Relocation assistance and travel crossover benefits on transfer — issued case by case.",
            ]),
            ("h", "5. Growth money"),
            ("bullets", [
                "Learning & certification budget per the Learning & Development Policy (KB-E-16).",
                "Referral bonus for successful referrals through the referral portal (per open-requisition rules).",
                "Certification exam fee reimbursement for in-role certifications.",
            ]),
            ("h", "6. Enrolling and using benefits"),
            ("p", "Most benefits enrol automatically at joining; election ones (dependants, family add-ons, accrued meal-plan top-ups) are set in the benefits portal window each April. Enrolment window misses default to standard individual cover; special enrolment (marriage, child birth) within 30 days of the event."),
            ("note", "Benefits carry tax: components received in cash (allowance-style benefits) are added to salary for tax; insurance premiums paid by the company are not taxable to you."),
        ],
    },
    {
        "slug": "group-health-insurance-guide",
        "ref": "KB-E-12",
        "title": "Group Health Insurance — Employee Guide",
        "category": "Benefits & Insurance",
        "audience": "employee",
        "summary": (
            "Who is covered under the group health plan, what's included and excluded, "
            "how to add dependants, and the step-by-step claim and cashless process."
        ),
        "keywords": (
            "health insurance, ghi, mediclaim, cashless, dependants, claim, tpa, e-card, "
            "hospitalisation, maternity claim, pre existing, network hospital, reimbursement claims"
        ),
        "version": "v1.9",
        "effective": (2026, 4, 1),
        "blocks": [
            ("p", "The company arranges group health cover with a leading insurer through a licensed TPA. This guide covers day-to-day use; the detailed policy wording and the plan sheet for your location live on the benefits portal."),
            ("h", "1. Who is covered"),
            ("bullets", [
                "You — from your date of joining (enrolment within 30 days of joining).",
                "Your spouse, dependent children and, in the standard plan, up to two dependent parents — dependant definitions follow the insurer's sheet.",
                "Coverage for dependants completes when their enrolment form is submitted; anniversary change windows apply for late adds.",
            ]),
            ("h", "2. What's covered, briefly"),
            ("bullets", [
                "In-patient hospitalisation, daycare procedures and prescribed daycare treatments in network hospitals.",
                "Pre-hospitalisation (30/60 days) and post-hospitalisation expenses per plan sheet.",
                "Maternity and newborn cover for the employee and spouse up to the plan sub-limit.",
                "Ambulance charges up to plan cap; domiciliary care where specifically allowed.",
            ]),
            ("h", "3. What is not covered"),
            ("p", "Standard exclusions apply: non-prescribed treatments, cosmetic procedures, dental unless accident-related, self-inflicted harm, war-risk, and treatments during the waiting period on listed pre-existing conditions. The exclusion schedule in the policy wording is definitive."),
            ("h", "4. Using cashless service at network hospitals"),
            ("bullets", [
                "Planned admission: notify the TPA at least 48 hours ahead; your e-card is on the benefits portal.",
                "Emergency: show the e-card at the hospital insurance desk; the TPA is notified within 24 hours.",
                "Network hospital + insured admission = majority of cases settle cashless without any reimbursement paperwork.",
            ]),
            ("h", "5. Reimbursement claims"),
            ("p", "If you use a non-network hospital or pay first, claim within 30 days of discharge: claim form, discharge summary, final bill, itemised bills for consumables, prescriptions, diagnostics and payment proof. Attach all of it in the claims portal — you get the settled amount (or deficiency note) within the TPA's service periods."),
            ("h", "6. Common triggers and fixes"),
            ("table",
             ["Situation", "What to do"],
             [
                 ["Marriage / childbirth", "Add within 30 days via benefits portal (special enrolment)"],
                 ["Parent ageing out", "Notify HR; parent becomes chargeable per exit norms"],
                 ["Exit from Emids", "Cover ends on your last day; convert to retail policy through TPA portability"],
                 ["Claim rejected", "Read the deficiency note in the portal; most are documentation gaps that can be re-filed"],
             ]),
            ("note", "The insurance helpdesk responds fastest through the portal; escalating to an HR ticket is the right path only when portal threads have stalled."),
        ],
    },
    {
        "slug": "travel-expense-policy",
        "ref": "KB-E-13",
        "title": "Travel & Expense Reimbursement Policy",
        "category": "Compensation & Payroll",
        "audience": "employee",
        "summary": (
            "What the company pays for on business travel and how claims flow: "
            "approvals, booking channels, per-diem, caps and reimbursement timelines."
        ),
        "keywords": (
            "travel policy, expense reimbursement, per diem, hotel, cab, flight, conveyance, "
            "client visit, international travel, advance, gst, receipts, claims, trip itinerary"
        ),
        "version": "v2.2",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "Emids reimburses reasonable business expenses incurred for approved work travel and client engagements. Two rules carry the document: travel needs pre-approval, and reimbursement needs receipts. Everything else explains whose approval, what caps and what timeline."),
            ("h", "1. Pre-approval"),
            ("bullets", [
                "Domestic travel needs your manager's approval in the travel tool before booking.",
                "International travel needs business-unit head approval and an HR immigration pre-check (visa, tax, payroll impact).",
                "Emergency travel on verbal approval must be logged within 24 hours of speaking to your manager.",
            ]),
            ("h", "2. Booking and standards"),
            ("table",
             ["Item", "Standard"],
             [
                 ["Air (domestic)", "Economy, booked via the travel desk; fares beyond lowest +15% need justification"],
                 ["Rail", "AC II tier / AC I on eligible grades"],
                 ["Hotel", "Grade-wise city caps published by HR; hotel beyond cap = you pay the delta"],
                 ["Local transport", "Cabs via empanelled vendor; self-drive fuel at published rates"],
                 ["Meals & per-diem", "Domestic per-diem rate sheet; client-hosted meals are not claimed again"],
             ]),
            ("h", "3. Claims and receipts"),
            ("bullets", [
                "Submit within 30 days of trip end in the claims tool; claims expire after 90 days.",
                "Original itemised receipts for everything above petty-cash thresholds; GST-compliant bills to company GSTIN where registered.",
                "One trip = one claim with all its bills; exceptions split at the approver's mention.",
            ]),
            ("h", "4. Advances"),
            ("p", "Cash advance up to 50% of estimated trip cost is available against an approved travel request. A settled advance must be fully accounted; unused advance recovered from the next claim or payroll, and repeat advances blocked until earlier ones reconcile."),
            ("h", "5. What is not reimbursable"),
            ("bullets", [
                "Personal entertainment, minibar, movies, room service beyond meal caps — unless trip-period norms allow.",
                "Traffic / parking fines, lost receipts without a signed recon form (capped once per FY).",
                "Companion travel, lounge access unless eligible grade, and equipment we already issued you.",
            ]),
            ("h", "6. Timelines and payments"),
            ("p", "Verified claims are paid with the next payroll run or the fortnightly expense payout cycle, whichever you note in the claim; disputed claims route to the expense audit team with response within 5 working days. Continuous non-compliance (late, fictitious or padded claims) is a code-of-conduct breach, not merely a claim issue."),
            ("note", "If the situation is grey (client invite hosting, joint team dinner with partner companies), email the ask to your approver before spending — a one-line record beats a rejected ₹8,000 claim."),
        ],
    },
]
