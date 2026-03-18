"""
Skill Gap Analyzer — Phase 6 V10 Career Intelligence
Cross-references SM-2 mastery data vs. career domain required skills.
"""
import json
import logging
from groq import AsyncGroq
from config import settings

logger = logging.getLogger(__name__)

# Import career domain skill map from existing career.py (avoid duplication)
try:
    from agents.career import DOMAIN_SKILLS, CERT_MAP
except ImportError:
    # Fallback if import path differs
    DOMAIN_SKILLS = {
        "AI/ML Engineer":        ["Python", "PyTorch/TensorFlow", "MLflow", "Hugging Face", "Scikit-learn", "CUDA"],
        "Data Scientist":        ["Python", "SQL", "Pandas", "Power BI / Tableau", "Statistics", "A/B Testing"],
        "Cloud Architect":       ["AWS/GCP/Azure", "Terraform", "Kubernetes", "Docker", "CI/CD pipelines"],
        "DevOps/SRE":            ["Docker", "Kubernetes", "Terraform", "Prometheus/Grafana", "Linux", "Shell scripting"],
        "Software Developer":    ["Java/Python/Go", "REST APIs", "System Design", "Git", "SQL", "Design Patterns"],
        "Full-Stack Developer":  ["React/Next.js", "Node.js", "PostgreSQL", "REST/GraphQL", "Docker", "TypeScript"],
        "Cybersecurity Analyst": ["Linux", "Wireshark", "Metasploit", "Python", "SIEM tools", "OWASP"],
        "Data Engineer":         ["Python", "Apache Spark", "Kafka", "Airflow", "dbt", "Snowflake"],
        "MLOps Engineer":        ["Docker", "Kubernetes", "MLflow", "Vertex AI", "CI/CD for ML", "Python"],
    }
    CERT_MAP = {}


async def analyze_skill_gap(
    student_db_id: int,
    primary_domain: str,
    pool,
    subject_names: list[str] = None,
) -> dict:
    """
    Cross-reference student's academic subjects vs. required skills
    for their career domain. Uses SM-2 mastery data for coverage estimation.

    Returns:
        {
            domain, required_skills, covered_skills, gap_skills,
            gap_score (0-100, lower is better),
            gap_breakdown: [{ skill, coverage, source, action }],
            action_items: [str],
            estimated_weeks_to_close: int
        }
    """
    required_skills = DOMAIN_SKILLS.get(primary_domain, DOMAIN_SKILLS["Software Developer"])

    # Pull SM-2 memory to estimate subject coverage
    covered_concepts: set[str] = set()
    mastery_scores: dict[str, float] = {}

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT concept, ease_factor, repetitions
                FROM student_learning_memory
                WHERE student_db_id = $1
                """,
                student_db_id,
            )
        for r in rows:
            concept = (r["concept"] or "").lower()
            reps    = r["repetitions"] or 0
            ease    = float(r["ease_factor"] or 2.5)
            # Well-learned: 3+ reps, ease >= 2.5
            if reps >= 3 and ease >= 2.5:
                covered_concepts.add(concept)
                mastery_scores[concept] = min(1.0, ease / 3.0)
            elif reps >= 1:
                mastery_scores[concept] = 0.4
    except Exception as e:
        logger.warning(f"SM-2 fetch for skill gap: {e}")

    # Subject names also count as coverage signals
    if subject_names:
        for sn in subject_names:
            covered_concepts.add(sn.lower())

    # LLM-enhanced skill coverage analysis
    try:
        groq = AsyncGroq(api_key=settings.groq_api_key)
        prompt = f"""You are a career skills analyst for engineering students.

Career Domain: {primary_domain}
Required Skills: {required_skills}
Student's known concepts (from their learning history): {list(covered_concepts)[:40]}
Student's subjects/courses: {subject_names or []}

For each required skill, estimate coverage:
- covered: student's learning history/subjects clearly covers this skill
- partial: some related knowledge exists
- gap: not covered at all

Return ONLY valid JSON:
{{
  "skill_analysis": [
    {{
      "skill": "<skill name>",
      "coverage": "covered|partial|gap",
      "confidence": 0-100,
      "action": "<specific 1-line action to address this if gap/partial>"
    }}
  ]
}}"""

        resp = await groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a career skills analyst. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1500,
        )
        import re
        raw = resp.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        skill_data = json.loads(match.group() if match else raw)
        skill_analysis = skill_data.get("skill_analysis", [])
    except Exception as e:
        logger.error(f"Skill gap LLM error: {e}")
        # Deterministic fallback
        skill_analysis = [
            {
                "skill":      s,
                "coverage":   "covered" if any(kw in " ".join(covered_concepts) for kw in s.lower().split("/")) else "gap",
                "confidence": 60,
                "action":     f"Study {s} fundamentals and build a project",
            }
            for s in required_skills
        ]

    # Aggregate
    covered = [s for s in skill_analysis if s.get("coverage") == "covered"]
    partial  = [s for s in skill_analysis if s.get("coverage") == "partial"]
    gaps     = [s for s in skill_analysis if s.get("coverage") == "gap"]

    total = len(skill_analysis) or 1
    gap_score = int(((len(gaps) + len(partial) * 0.5) / total) * 100)

    # Weeks estimate: ~2 weeks per gap skill, ~1 week per partial
    est_weeks = len(gaps) * 2 + len(partial) * 1

    action_items = [
        s["action"]
        for s in sorted(skill_analysis, key=lambda x: {"gap": 0, "partial": 1, "covered": 2}[x.get("coverage", "gap")])
        if s.get("action") and s.get("coverage") != "covered"
    ][:6]

    return {
        "domain":                  primary_domain,
        "required_skills":         required_skills,
        "covered_skills":          [s["skill"] for s in covered],
        "partial_skills":          [s["skill"] for s in partial],
        "gap_skills":              [s["skill"] for s in gaps],
        "gap_score":               gap_score,
        "gap_breakdown":           skill_analysis,
        "action_items":            action_items,
        "estimated_weeks_to_close": est_weeks,
        "coverage_pct":            int((len(covered) / total) * 100),
    }
