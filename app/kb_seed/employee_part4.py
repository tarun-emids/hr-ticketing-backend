"""Knowledge base seed content — employee policies, part 4 (KB-E-14..18)."""

EMPLOYEE_PART4 = [
    {
        "slug": "probation-confirmation-policy",
        "ref": "KB-E-14",
        "title": "Probation, Confirmation & Notice Period Policy",
        "category": "Growth & Performance",
        "audience": "employee",
        "summary": (
            "How probation works at Emids, the 30-60-90 goals, what confirmation "
            "requires, extensions, and how notice periods apply to both sides."
        ),
        "keywords": (
            "probation, confirmation, notice period, resignation, 30 60 90, onboarding review, "
            "performance review, probation extension, absorption"
        ),
        "version": "v2.0",
        "effective": (2025, 8, 1),
        "blocks": [
            ("p", "Every new employee joins with a defined probation period — normally six months, or as stated in your offer letter. Probation is not a holding pen: it is where structured goals, honest feedback and support come together to make early employment work."),
            ("h", "1. During probation"),
            ("bullets", [
                "In week one you agree 30-60-90 day goals with your manager; they are recorded and referred to at each checkpoint.",
                "Checkpoints run at 30, 60 and 90 days — 30 minutes each, focused on progress, blockers and coaching.",
                "Leave accrues during probation; annual and casual leave are availed only with manager approval.",
                "Probation-chartered employees carry client and policy obligations identically to confirmed employees.",
            ]),
            ("h", "2. What confirmation requires"),
            ("p", "Two things in combination: the rated outcome of your goal checkpoints, and behavioural evidence of the values in the code of conduct. Confirmation is proposed by your manager, reviewed by HR and signed off by the business-unit head around the month prior to your probation end date."),
            ("h", "3. When things are not on track"),
            ("p", "If performance or conduct falls short, probation may be extended once by up to three months with a written improvement plan: clear gaps, support offered, measurable checkpoints. A decision to exit is made before an extension — not after a second failed cycle."),
            ("h", "4. Notice periods"),
            ("table",
             ["Status", "Resignation notice", "Company notice"],
             [
                 ["On probation", "15 days", "15 days"],
                 ["Confirmed (≤ 5 years tenure)", "60 days", "60 days"],
                 ["Confirmed (> 5 years / leadership)", "90 days", "90 days"],
             ]),
            ("p", "Notice starts on the date your resignation is acknowledged in the HR system, not the day you first tell your manager. The company may waive, shorten or pay in lieu of notice; your exit obligations (handover and asset return) do not shrink with it."),
            ("h", "5. During notice"),
            ("bullets", [
                "Leave balance may be availed only with manager approval; notice does not extend while on leave unless agreed in writing.",
                "Absorption interviews and onboarding elsewhere in the company go ahead as normal while you are on notice within Emids.",
                "Knowledge-transfer signoff is a gate for your final records.",
            ]),
        ],
    },
    {
        "slug": "performance-review-policy",
        "ref": "KB-E-15",
        "title": "Performance Review & Appraisal Policy",
        "category": "Growth & Performance",
        "audience": "employee",
        "summary": (
            "The annual performance cycle: goal setting, mid-year check-in, year-end "
            "reviews, rating calibration, outcomes and the appeal path."
        ),
        "keywords": (
            "performance review, appraisal, rating, calibration, goal setting, okr, kpi, "
            "check-in, promotion cycle, increment, performance improvement, appeal"
        ),
        "version": "v3.0",
        "effective": (2026, 2, 1),
        "blocks": [
            ("p", "Our performance cycle runs March to February for India and calendar-year for US colleagues, and connects goals set at joining or each April to ratings, pay outcomes and promotion decisions. This document explains the cycle, what each phase is for, and where to raise a weak review."),
            ("h", "1. The cycle"),
            ("table",
             ["Phase", "Timing", "Output"],
             [
                 ["Goal setting", "April (or on joining)", "Signed goals — business, role and growth"],
                 ["Mid-year check-in", "August–September", "Non-rated progress conversation, documented"],
                 ["Year-end self review", "January", "Self assessment against goals"],
                 ["Manager review", "February", "Manager commentary + proposed rating"],
                 ["Calibration", "February", "Unit-level moderation for consistency"],
                 ["Feedback & outcomes", "March", "Rating shared, increment/variable outcomes confirmed"],
             ]),
            ("h", "2. How you are assessed"),
            ("p", "Ratings weigh two things together: what was delivered against agreed goals, and how it was delivered — conduct, collaboration and adherence to the code. No single metric, and certainly no last-quarter sprint, decides a rating."),
            ("h", "3. Calibration and fairness"),
            ("p", "Proposed ratings are moderated in calibration panels with multiple managers present, to counter individual harshness or generosity. Panel notes are retained; if two consecutive cycles produce statistically lopsided distribution, HR audits the panel's reasoning."),
            ("h", "4. Outcomes"),
            ("bullets", [
                "Increment and variable amounts follow the Compensation Structure & Payment Policy (KB-E-09).",
                "Promotion cases are decided in the same cycle using potential + sustained delivery, not on rating alone.",
                "A first-cycle low rating triggers a written improvement plan before any exit proposal.",
            ]),
            ("h", "5. If you disagree with your rating"),
            ("p", "First, have the conversation with your manager after the feedback — most differences end there. If it does not, you can appeal in an HR ticket within 10 working days of the rating being shared; a senior reviewer outside the calibration panel re-reads the year's evidence and replies within 15 working days. The reviewer's finding is final for the cycle."),
        ],
    },
    {
        "slug": "learning-development-policy",
        "ref": "KB-E-16",
        "title": "Learning & Development Policy",
        "category": "Growth & Performance",
        "audience": "employee",
        "summary": (
            "Learning entitlements — the annual budget, certification support, "
            "training hours, project learning requests and sharing back to the organisation."
        ),
        "keywords": (
            "learning, development, training, certification, upskilling, budget, stipend, "
            "conference, courses, udemy, lms, mentorship, knowledge sharing"
        ),
        "version": "v1.5",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "Learning at Emids is funded, not merely permitted. Every confirmed employee carries an annual learning budget, utilised through a simple approval flow; your learning plan is part of your mid-year check-in."),
            ("h", "1. Annual budget"),
            ("table",
             ["Tenure / level", "Annual learning budget"],
             [
                 ["Each confirmed employee", "Per published band table (typical ₹25,000–₹60,000)"],
                 ["Extra for certification exams", "Exam fee reimbursed beyond budget for in-role certifications"],
                 ["Event / conference", "Case by case, with a talking-back commitment"],
             ]),
            ("h", "2. What the budget covers"),
            ("bullets", [
                "Self-paced courses and platform subscriptions approved in the LMS catalogue.",
                "Certification exam fees for certifications relevant to your role or next role.",
                "Books and journal access related to your development plan.",
                "Bootcamps or workshops with your manager's recommendation.",
            ]),
            ("h", "3. Requesting learning"),
            ("p", "Raise the request in the LMS with the link, cost and a two-line why-it-matters. Manager approval within 5 working days for spends inside your budget; beyond budget or client-critical timing needs the delivery head. Completed learning is recorded in your profile — supervisors see completed courses during reviews."),
            ("h", "4. Learning hours"),
            ("p", "A minimum of four hours per month of learning time is expected — scheduled like any other commitment. Teams commonly block Friday afternoons; if your project makes a block impossible, your manager should help you find the hours rather than skip the expectation."),
            ("h", "5. Sharing back"),
            ("p", "Learning returns more than personal growth when it is shared: guild talks, brown-bag sessions and internal enablement sessions convert individual budget into team capability (and in some programmes, into recognition awards)."),
            ("note", "Certification bonds are not applied at Emids for standard in-role certifications; long courses (6+ months) or company-initiated programmes may carry a service period stated upfront and in writing."),
        ],
    },
    {
        "slug": "it-assets-acceptable-use-policy",
        "ref": "KB-E-17",
        "title": "IT Assets & Acceptable Use Policy",
        "category": "Compliance & Security",
        "audience": "employee",
        "summary": (
            "Rules for company devices, accounts, networks and data: what you may and "
            "must not do, plus what to do the minute something looks compromised."
        ),
        "keywords": (
            "acceptable use, it policy, laptop, device, email, accounts, password, mfa, "
            "data security, github, software install, personal device, usb, phishing, security incident"
        ),
        "version": "v4.0",
        "effective": (2026, 1, 1),
        "blocks": [
            ("p", "Company systems hold client, patient and business-critical data. This policy states the baseline rules that make it safe; specialised client programs carry their own security annexes that sit on top of, not in place of, this document."),
            ("h", "1. Devices"),
            ("bullets", [
                "Company-issued devices are for company work; family use is not sanctioned.",
                "Operating systems, ED agents and browsers must stay current — patching is automatic and non-negotiable.",
                "Install software only from the approved catalogue; local admin grants are role-based, not default.",
                "Personal devices may touch company systems only through approved apps (approved email / chat / drive clients) — no local downloads to personal storage.",
            ]),
            ("h", "2. Accounts and access"),
            ("bullets", [
                "Your credentials are personal and non-transferable; sharing them is a code-of-conduct breach.",
                "MFA is mandatory on every account that touches client or PII data.",
                "Access beyond your role (production data, client environments) is requested through access workflow with a business justification and an expiry date.",
            ]),
            ("h", "3. Data handling"),
            ("p", "Data leaves Emids only through approved channels. Personal email, personal cloud drives, unapproved AI tools and personal USB drives are prohibited for company data. Screening and demos use company-environment datasets; any download to a live client dataset needs to remain inside the secure enclave."),
            ("h", "4. Networks and remote work"),
            ("p", "Home Wi-Fi must run WPA2/WPA3 with a changed default admin password. On public networks nothing sensitive goes over open Wi-Fi without the VPN, and the VPN must be on continuously during working hours. Physical-carried devices stay with you or in hotel safes — never left in cars."),
            ("h", "5. Email, chat, web"),
            ("bullets", [
                "No company data on external AI chatbots unless the tool is on the approved list.",
                "External sharing via chat needs the same care as email — think who's on the other side.",
                "Suspect emails: report with the built-in phishing button, don't forward them to friends.",
            ]),
            ("h", "6. When something goes wrong"),
            ("p", "Report a lost or stolen device and any suspected data breach to the IT helpdesk and your manager immediately — within a maximum of 4 hours. Speed matters more than certainty: false alarms are thanked, unreported incidents are treated as breaches."),
            ("h", "7. On exit"),
            ("p", "All assets are returned on or before the last working day; accounts close as per the exit checklist. Licences you personally opened for work purposes are transferred to the company."),
        ],
    },
    {
        "slug": "posh-act-employee-handbook",
        "ref": "KB-E-18",
        "title": "Prevention of Sexual Harassment (POSH) — Employee Handbook",
        "category": "Compliance & Security",
        "audience": "employee",
        "summary": (
            "What sexual harassment looks like under the POSH Act 2013, everyone's "
            "rights at Emids, how to complain, and what the Internal Committee does."
        ),
        "keywords": (
            "posh, sexual harassment, icc, internal committee, complaint, redressal, "
            "workplace harassment, act 2013, prevention, interim relief, awareness"
        ),
        "version": "v2.6",
        "effective": (2025, 12, 1),
        "blocks": [
            ("p", "Emids Technologies maintains a workplace free of sexual harassment as required under the Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013. This handbook is written for every employee and intern; it is a legal compliance document, re-issued annually with awareness training."),
            ("h", "1. What counts as sexual harassment"),
            ("p", "Under the Act, any one of these unwelcome acts or behaviour (directly or by implication) is sexual harassment: physical contact and advances; a demand or request for sexual favours; making sexually coloured remarks; showing pornography; or any other unwelcome physical, verbal or non-verbal conduct of a sexual nature."),
            ("bullets", [
                "It is about the impact on the recipient, not the intent of the person doing it.",
                "It covers online conduct — chats, video calls, social messages, shared media.",
                "It applies at the office, client sites, work events, and any context that is sufficiently connected to work.",
                "Both women and men can experience and complain of unwelcome conduct; the Act's statutory committee process gives additional statutory rights in certain cases.",
            ]),
            ("h", "2. Your rights"),
            ("bullets", [
                "A workplace free from harassment — including from clients, vendors and visitors, not only Emids colleagues.",
                "A specified Internal Committee process with defined timelines, confidentiality and no cost to you.",
                "Interim relief measures (work transfer to avoid contact, up to 3 months' paid leave where warranted by law) while an inquiry continues.",
                "No retaliation — for complaining, being a witness, or helping an inquiry.",
            ]),
            ("h", "3. Who to complain to"),
            ("p", "The Internal Committee (IC) at each office is the statutory forum. Its member roster, including an external member, is displayed on notice boards and the HR portal. You may approach any IC member directly, email the IC mailbox, or raise through the HR portal marked confidential. Complaints of this kind made through ordinary HR tickets are routed automatically and unread to the IC."),
            ("h", "4. The inquiry process at a glance"),
            ("table",
             ["Step", "Timeline"],
             [
                 ["Complaint filed (written, to any member)", "Within 3 months of the incident (extensions possible)"],
                 ["IC acknowledgement & interim measures", "7 days"],
                 ["Respondent gets copy + reply window", "10 days"],
                 ["Inquiry with both sides heard", "≤ 90 days"],
                 ["IC report & recommendation to employer", "10 days after inquiry closes"],
                 ["Employer action on recommendations", "60 days"],
             ]),
            ("h", "5. Confidentiality and false complaints"),
            ("p", "Names, details and documents in an IC process are confidential — publishing them further is itself punishable. Complaints made in good faith are protected even if not proven; complaints proven malicious or knowingly false face disciplinary action."),
            ("note", "If you witness harassment of someone else, you can complain too — the Act lets any affected person's colleague report on their behalf with their consent."),
        ],
    },
]
