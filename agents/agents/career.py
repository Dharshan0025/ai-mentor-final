"""
AI-Mentor — Career Intelligence Agent
Handles: career domain mapping, strength analysis, roadmap generation,
         certification recommendations, internship/placement guidance.
LLM: AWS Bedrock (ChatGPT 120b) with Groq fallback

Architecture:
  1. compute_career_profile()  — deterministic, data-driven analysis
  2. career_node()             — LangGraph node (LLM narrative)
  3. generate_career_report()  — full structured JSON for Career page
"""
from langchain_core.messages import HumanMessage, SystemMessage
from config import settings
import logging
import json

logger = logging.getLogger(__name__)


def _get_llm(temperature: float = 0.4, max_tokens: int = 600):
    """Return Bedrock ChatGPT first, fall back to Groq."""
    try:
        from langchain_aws import ChatBedrock
        return ChatBedrock(
            model_id=settings.bedrock_model_id,
            region_name=settings.aws_region,
            model_kwargs={"temperature": temperature, "max_tokens": max_tokens},
        ), "bedrock"
    except Exception as e:
        logger.warning(f"Bedrock init failed ({e}), using Groq")
        from langchain_groq import ChatGroq
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=temperature,
            max_tokens=max_tokens,
        ), "groq"


# ── Career Domain Mapping ───────────────────────────────────────────────────
# Maps subject codes and keywords → career domains with 2025 relevance
SUBJECT_DOMAIN_MAP = {
    # CS/CSBS subjects → Career domains
    "machine learning": ["AI/ML Engineer", "Data Scientist", "MLOps Engineer", "AI Researcher"],
    "deep learning": ["AI/ML Engineer", "Computer Vision Engineer", "NLP Engineer", "AI Researcher"],
    "data science": ["Data Scientist", "Analytics Engineer", "BI Developer", "Data Engineer"],
    "operating systems": ["Systems Engineer", "Embedded Developer", "Kernel Developer", "Cloud Engineer"],
    "computer networks": ["Network Engineer", "Cloud Engineer", "DevOps/SRE", "Cybersecurity Analyst"],
    "database systems": ["Database Engineer", "Data Engineer", "Backend Developer", "Cloud Architect"],
    "software engineering": ["Software Developer", "Product Manager", "DevOps Engineer", "SRE"],
    "cloud computing": ["Cloud Architect", "DevOps/SRE", "Platform Engineer", "Solutions Architect"],
    "cybersecurity": ["Security Engineer", "Penetration Tester", "SOC Analyst", "Security Architect"],
    "web development": ["Frontend Engineer", "Full-Stack Developer", "UI/UX Engineer"],
    "algorithms": ["Software Engineer", "Competitive Programmer", "Quant Developer"],
    "computer vision": ["Computer Vision Engineer", "AR/VR Developer", "Robotics Engineer"],
    "natural language processing": ["NLP Engineer", "Conversational AI Developer", "LLM Fine-tuner"],
    "blockchain": ["Blockchain Developer", "Web3 Engineer", "Smart Contract Developer"],
    "internet of things": ["IoT Engineer", "Embedded Systems Developer", "Edge Computing Engineer"],
    "business systems": ["Business Analyst", "ERP Consultant", "Product Manager", "Digital Transformation Consultant"],
    "entrepreneurship": ["Startup Founder", "Product Manager", "Business Development"],
    "digital marketing": ["Growth Engineer", "MarTech Engineer", "Data Analyst"],
}

# 2025 High-demand certifications aligned to each career path
CERT_MAP = {
    "AI/ML Engineer": ["Google ML Engineer Professional", "AWS Machine Learning Specialty", "Deep Learning Specialization (Coursera)", "Hugging Face NLP Course"],
    "Data Scientist": ["Google Data Analytics", "IBM Data Science Professional", "Azure Data Scientist Associate", "Kaggle Competitions"],
    "Cloud Architect": ["AWS Solutions Architect Associate", "Google Cloud Professional Architect", "Azure Solutions Architect Expert"],
    "DevOps/SRE": ["CKA (Certified Kubernetes Admin)", "AWS DevOps Engineer", "HashiCorp Terraform Associate", "GitHub Actions Certification"],
    "Software Developer": ["Meta Backend Developer (Coursera)", "Oracle Java SE 17 Developer", "Spring Professional"],
    "Cybersecurity Analyst": ["CompTIA Security+", "CEH (Certified Ethical Hacker)", "OSCP", "AWS Security Specialty"],
    "Data Engineer": ["dbt Analytics Engineer", "Databricks Associate", "Apache Kafka Confluent Certification"],
    "Full-Stack Developer": ["Meta Full Stack Engineer", "AWS Certified Developer", "MongoDB Developer"],
    "Product Manager": ["Product School PM Certification", "Google PM Certificate", "Pragmatic Marketing"],
    "Network Engineer": ["CCNA", "AWS Advanced Networking", "Juniper JNCIA"],
    "MLOps Engineer": ["AWS ML Engineer – Associate", "MLflow Certification", "Vertex AI Professional"],
}

DOMAIN_SKILLS = {
    "AI/ML Engineer": ["Python", "PyTorch/TensorFlow", "MLflow", "Hugging Face", "Scikit-learn", "CUDA"],
    "Data Scientist": ["Python", "SQL", "Pandas", "Power BI / Tableau", "Statistics", "A/B Testing"],
    "Cloud Architect": ["AWS/GCP/Azure", "Terraform", "Kubernetes", "Docker", "CI/CD pipelines"],
    "DevOps/SRE": ["Docker", "Kubernetes", "Terraform", "Prometheus/Grafana", "Linux", "Shell scripting"],
    "Software Developer": ["Java/Python/Go", "REST APIs", "System Design", "Git", "SQL", "Design Patterns"],
    "Cybersecurity Analyst": ["Linux", "Wireshark", "Metasploit", "Python", "SIEM tools", "OWASP"],
    "Full-Stack Developer": ["React/Next.js", "Node.js", "PostgreSQL", "REST/GraphQL", "Docker", "TypeScript"],
    "Data Engineer": ["Python", "Apache Spark", "Kafka", "Airflow", "dbt", "Snowflake"],
    "MLOps Engineer": ["Docker", "Kubernetes", "MLflow", "Vertex AI", "CI/CD for ML", "Python"],
}

# 2025 Indian job market context
INDIA_JOB_CONTEXT = """
2025 Indian Tech Market Intelligence:
- AI/ML: 40% YoY growth; top hiring: Google, Microsoft, Flipkart, Meesho, Sarvam AI
- Cloud: #1 skill shortage in India; AWS/Azure certs = 30-50% salary premium
- MAANG India offices expanding: Hyderabad, Bengaluru, Pune, Chennai
- Product companies vs. Service companies: 3-5x salary difference
- GATE 2025 cutoffs trending up for CS/CSBS; high demand for research profiles
- Startup ecosystem: 100+ unicorns; product + full-stack most wanted
- CSBS/CS: Strong placement rates 80-95% at top engineering colleges
- Internship portals: LinkedIn, Internshala, LeetCode Jobs, GFG Jobs, Unstop
- CGPA threshold: 6.5+ for most product companies; 7.5+ for MAANG/top product
"""


# ── Deterministic Career Profile Computation ────────────────────────────────

def compute_career_profile(profile: dict) -> dict:
    """
    Data-driven career analysis using student profile.
    Returns structured career intelligence without LLM.
    """
    subjects = profile.get("subjects", [])
    cgpa = profile.get("currentCGPA", 0.0)
    semester = profile.get("semester", 7)
    year = profile.get("year", 4)
    arrears = profile.get("arrearsHistory", [])

    # 1. Identify strength subjects (grade > 7.5, attendance > 80%)
    strength_subjects = [
        s for s in subjects
        if s.get("grade", 0) >= 7.5 and s.get("attendance", 0) >= 80
    ]

    # 2. Map strengths to career domains
    career_scores: dict[str, float] = {}
    for s in strength_subjects:
        name_lower = s.get("name", "").lower()
        for keyword, domains in SUBJECT_DOMAIN_MAP.items():
            if keyword in name_lower:
                grade_weight = s.get("grade", 7.0) / 10.0
                bloom_weight = s.get("bloomLevel", 2) / 6.0
                score = grade_weight * 0.6 + bloom_weight * 0.4
                for domain in domains:
                    career_scores[domain] = career_scores.get(domain, 0) + score

    # Normalize and sort
    top_domains = sorted(career_scores.items(), key=lambda x: x[1], reverse=True)[:4]

    # 3. Primary career path
    primary_domain = top_domains[0][0] if top_domains else "Software Developer"
    secondary_domain = top_domains[1][0] if len(top_domains) > 1 else "Data Engineer"

    # 4. Certifications
    recommended_certs = CERT_MAP.get(primary_domain, [])[:3]
    secondary_certs = CERT_MAP.get(secondary_domain, [])[:2]

    # 5. Required skills
    primary_skills = DOMAIN_SKILLS.get(primary_domain, [])
    missing_skills = primary_skills[:4]  # Skills likely to build toward

    # 6. Placement eligibility — richer tiering
    cgpa_eligible = cgpa >= 6.5
    cgpa_maang = cgpa >= 7.5
    cgpa_top_tier = cgpa >= 8.0
    has_active_arrears = len([a for a in arrears if "cleared" not in a.lower()]) > 0
    att_ok = profile.get("attendanceOverall", 0) >= 75

    if has_active_arrears:
        placement_tier = "Tier 3 — Service (after arrear clearance)"
        tier_detail = "Clear arrears first — most product companies filter them out."
    elif cgpa_top_tier and att_ok:
        placement_tier = "Tier 1 — MAANG / Unicorn / Top Product"
        tier_detail = "Strong profile — target Google, Microsoft, Flipkart, CRED, startups."
    elif cgpa_maang and att_ok:
        placement_tier = "Tier 1 — MAANG / Top Product"
        tier_detail = "Eligible for campus drives — focus on DSA, projects, referrals."
    elif cgpa_eligible and att_ok:
        placement_tier = "Tier 2 — Mid-tier Product / Service"
        tier_detail = "Push CGPA to 7.5+ to unlock MAANG; build projects meanwhile."
    elif cgpa_eligible:
        placement_tier = "Tier 2 — Eligibility at risk (attendance)"
        tier_detail = "Improve attendance to ≥75% — critical for placement eligibility."
    else:
        placement_tier = "Tier 3 — Focus on CGPA improvement"
        tier_detail = "Target 6.5+ CGPA for service companies; 7.5+ for product."

    # 7. Readiness score (0-100)
    readiness_score = int(
        (cgpa / 10.0) * 40 +
        (len(strength_subjects) / max(len(subjects), 1)) * 30 +
        (1 if not has_active_arrears else 0) * 20 +
        (min(semester, 8) / 8) * 10
    )

    # 8. Action timeline based on semester
    weeks_to_placement = max(1, (8 - semester) * 6)  # Rough estimate
    urgent_actions = _get_urgent_actions(semester, cgpa, has_active_arrears, primary_domain)

    # 9. Next actions — prioritized with impact
    next_actions = _build_next_actions(
        semester, cgpa, has_active_arrears, att_ok,
        primary_domain, placement_tier, strength_subjects, subjects,
    )

    return {
        "primary_domain": primary_domain,
        "secondary_domain": secondary_domain,
        "top_domains": [{"domain": d, "match_score": round(s * 100)} for d, s in top_domains],
        "strength_subjects": [{"name": s.get("name"), "grade": s.get("grade"), "code": s.get("code")} for s in strength_subjects],
        "recommended_certifications": recommended_certs,
        "secondary_certifications": secondary_certs,
        "primary_skills": primary_skills,
        "missing_skills": missing_skills,
        "placement_tier": placement_tier,
        "placement_tier_detail": tier_detail,
        "placement_eligible": cgpa_eligible,
        "maang_eligible": cgpa_maang,
        "has_active_arrears": has_active_arrears,
        "readiness_score": readiness_score,
        "urgent_actions": urgent_actions,
        "next_actions": next_actions,
        "weeks_to_placement": weeks_to_placement,
        "cgpa": cgpa,
        "semester": semester,
    }


def _get_urgent_actions(semester: int, cgpa: float, has_arrears: bool, domain: str) -> list[str]:
    actions = []
    if semester >= 7:
        actions.append("Build 2-3 GitHub projects showcasing your primary domain")
        actions.append("Start LeetCode DSA practice — 2 problems/day minimum")
        actions.append("Update LinkedIn profile with projects and skills")

    if cgpa < 7.5:
        actions.append(f"Push CGPA to 7.5+ — opens MAANG and top product companies")
    if has_arrears:
        actions.append("Clear pending arrears immediately — most product companies filter them out")
    if semester >= 6:
        actions.append(f"Get 1 domain-specific certification ({domain})")
        actions.append("Apply for internships on LinkedIn, Internshala, and Unstop")
    if semester >= 7:
        actions.append("Register for campus placements — prepare resume, referrals")

    return actions[:5]


def _build_next_actions(
    semester: int,
    cgpa: float,
    has_arrears: bool,
    att_ok: bool,
    domain: str,
    tier: str,
    strength_subjects: list,
    subjects: list,
) -> list[dict]:
    """
    Prioritized next actions with impact and timeline.
    Each: { action, impact, priority, timeline }
    """
    actions = []
    priority = 1

    if has_arrears:
        actions.append({
            "action": "Clear all pending arrears",
            "impact": "Unblocks placement eligibility — product companies filter arrears",
            "priority": priority,
            "timeline": "Immediate",
        })
        priority += 1

    if not att_ok:
        actions.append({
            "action": "Raise attendance to ≥75% in all subjects",
            "impact": "Required for placement eligibility",
            "priority": priority,
            "timeline": "This semester",
        })
        priority += 1

    if cgpa < 6.5:
        actions.append({
            "action": "Target CGPA 6.5+ for service company eligibility",
            "impact": "Opens TCS, Infosys, Wipro, Accenture campus drives",
            "priority": priority,
            "timeline": "Next 2 semesters",
        })
        priority += 1
    elif cgpa < 7.5 and "Tier 1" not in tier:
        actions.append({
            "action": "Push CGPA to 7.5+",
            "impact": "Unlocks MAANG and top product companies",
            "priority": priority,
            "timeline": "Next 1–2 semesters",
        })
        priority += 1

    risk_subjects = [s for s in subjects if s.get("status") in ("risk", "watch")]
    if risk_subjects:
        sub_names = ", ".join((str(s.get("name") or s.get("code") or "Subject")[:25] for s in risk_subjects[:2]))
        actions.append({
            "action": f"Focus on at-risk subjects: {sub_names}",
            "impact": "Prevents grade drop and protects CGPA",
            "priority": priority,
            "timeline": "Ongoing",
        })
        priority += 1

    if semester >= 6:
        actions.append({
            "action": f"Get 1 certification in {domain}",
            "impact": "Differentiates resume; 30–50% salary premium for cloud/AI certs",
            "priority": priority,
            "timeline": "Next 3 months",
        })
        priority += 1

    if semester >= 7:
        actions.append({
            "action": "Build 2–3 GitHub projects + LeetCode 2 problems/day",
            "impact": "Resume strength; DSA is table stakes for product companies",
            "priority": priority,
            "timeline": "Before placement season",
        })
        priority += 1
        actions.append({
            "action": "Apply for internships on LinkedIn, Internshala, Unstop",
            "impact": "Pre-placement experience; converts to PPO",
            "priority": priority,
            "timeline": "Now",
        })

    return actions[:6]


# ── LangGraph Career Node ───────────────────────────────────────────────────

CAREER_SYSTEM = """You are the Career Intelligence Agent for an AI academic mentor system for Indian engineering students.

Your role:
- Deliver personalized, data-grounded career roadmaps based on the student's actual academic performance
- Map subject strengths → specific, high-demand 2025 career paths in the Indian tech market
- Recommend certifications, skills, and concrete next steps with timelines
- Be realistic but motivating about CGPA, arrears, and placement eligibility
- Reference actual companies hiring in India (MAANG India, startups, product companies)

Student Career Intelligence Report:
{career_data}

India 2025 Job Market Context:
{market_context}

Response rules:
- Be SPECIFIC: name actual companies, certification courses, skills with versions
- NEVER be generic — ground every recommendation in their actual grades and subject performance
- Use markdown: **bold** key terms, numbered steps for roadmaps
- Maximum 400 words
- End with ONE high-impact, actionable step they can take TODAY"""

def career_node(state: dict) -> dict:
    """Career intelligence agent — academic-to-career mapping with LLM narrative."""
    llm, provider = _get_llm()

    profile = state.get("student_profile", {})
    career_data = compute_career_profile(profile)

    system_prompt = CAREER_SYSTEM.format(
        career_data=json.dumps(career_data, indent=2),
        market_context=INDIA_JOB_CONTEXT,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["message"]),
    ]

    result = llm.invoke(messages)

    return {
        **state,
        "career_output": result.content,
        "primary_agent": "career",
        "model_used": provider,
        "citations": [
            {"label": f"CGPA: {career_data['cgpa']}", "source": "ERP Academic Record"},
            {"label": f"Primary Path: {career_data['primary_domain']}", "source": "Career Intelligence Engine"},
            {"label": f"Placement Tier: {career_data['placement_tier']}", "source": "Market Eligibility Analysis"},
        ],
    }


# ── Standalone Career Report Generator ─────────────────────────────────────

def generate_career_report(profile: dict) -> dict:
    """
    Full structured career report for the Career dashboard page.
    Returns rich JSON consumed by the React frontend.
    """
    intel = compute_career_profile(profile)

    return {
        "student_id": profile.get("id"),
        "student_name": profile.get("name"),
        "cgpa": intel["cgpa"],
        "semester": intel["semester"],
        "readiness_score": intel["readiness_score"],
        "placement_tier": intel["placement_tier"],
        "placement_tier_detail": intel.get("placement_tier_detail", ""),
        "placement_eligible": intel["placement_eligible"],
        "maang_eligible": intel["maang_eligible"],
        "has_active_arrears": intel["has_active_arrears"],
        "primary_domain": intel["primary_domain"],
        "secondary_domain": intel["secondary_domain"],
        "career_paths": intel["top_domains"],
        "strength_subjects": intel["strength_subjects"],
        "certifications": {
            "primary": intel["recommended_certifications"],
            "secondary": intel["secondary_certifications"],
        },
        "skills_to_build": intel["primary_skills"],
        "urgent_actions": intel["urgent_actions"],
        "next_actions": intel.get("next_actions", []),
        "weeks_to_placement": intel["weeks_to_placement"],
        "market_context": {
            "top_hiring_companies": _get_hiring_companies(intel["primary_domain"]),
            "salary_range_lpa": _get_salary_range(intel["cgpa"], intel["primary_domain"]),
            "internship_portals": ["LinkedIn", "Internshala", "Unstop", "LeetCode Jobs", "GFG Jobs"],
        },
    }


def _get_hiring_companies(domain: str) -> list[str]:
    companies = {
        "AI/ML Engineer": ["Google DeepMind India", "Microsoft AI", "Sarvam AI", "Meesho", "Flipkart AI", "CRED"],
        "Data Scientist": ["Google", "Amazon", "Walmart Global Tech", "PhonePe", "Razorpay", "Swiggy"],
        "Cloud Architect": ["AWS India", "Microsoft Azure", "Infosys Cloud", "TCS Digital", "Wipro Cloud"],
        "DevOps/SRE": ["Google SRE India", "Atlassian", "Zomato", "Dunzo", "Juspay"],
        "Software Developer": ["Google", "Microsoft", "Amazon", "Flipkart", "Zepto", "Meesho", "Groww"],
        "Full-Stack Developer": ["CRED", "Razorpay", "BrowserStack", "Postman", "Hasura"],
        "Cybersecurity Analyst": ["IBM Security", "Palo Alto Networks India", "Quick Heal", "Wipro Cybersecurity"],
        "Data Engineer": ["Walmart Global Tech", "PhonePe", "Airtel", "ShareChat", "Dream11"],
    }
    return companies.get(domain, ["TCS", "Infosys", "Wipro", "Accenture", "Cognizant"])[:5]


def _get_salary_range(cgpa: float, domain: str) -> dict:
    # LPA ranges for 2025 Indian market
    base_ranges = {
        "AI/ML Engineer": (12, 45),
        "Data Scientist": (10, 35),
        "Cloud Architect": (10, 30),
        "DevOps/SRE": (8, 28),
        "Software Developer": (6, 40),
        "Full-Stack Developer": (6, 30),
        "Cybersecurity Analyst": (7, 25),
        "Data Engineer": (8, 30),
    }
    low, high = base_ranges.get(domain, (5, 20))
    # CGPA multiplier
    if cgpa >= 8.0:
        modifier = 1.2
    elif cgpa >= 7.5:
        modifier = 1.0
    elif cgpa >= 6.5:
        modifier = 0.8
    else:
        modifier = 0.6

    return {
        "min_lpa": round(low * modifier, 1),
        "max_lpa": round(high * modifier, 1),
        "fresher_average_lpa": round((low * modifier + high * modifier) / 2.5, 1),
    }
