"""
Concept Graph Builder — Phase 5 V7 Knowledge Engine
Builds prerequisite dependency graphs for subjects using NetworkX + Groq LLM.
Exports to Mermaid syntax for frontend rendering.
"""
import json
import re
import logging
from typing import Optional
from groq import AsyncGroq
from config import settings

logger = logging.getLogger(__name__)


async def _get_prerequisites_from_llm(
    subject_code: str, topics: list[str]
) -> list[dict]:
    """
    Ask Groq LLM to define prerequisite relationships between topics.
    Returns: [{ from: str, to: str, label: str }]
    """
    topics_str = "\n".join(f"- {t}" for t in topics[:40])  # cap at 40 topics

    prompt = f"""You are an expert curriculum designer for engineering education.
Subject: {subject_code}
Topics:
{topics_str}

Define the prerequisite relationships between these topics.
Which topics MUST be understood BEFORE another topic can be learned?

Return ONLY valid JSON:
{{
  "edges": [
    {{ "from": "<prerequisite topic>", "to": "<dependent topic>", "label": "needed for" }}
  ],
  "study_order": ["<topic 1>", "<topic 2>", ...]
}}

Rules:
- Only use topic names from the list above (exact match)
- A → B means "A must be learned before B"
- study_order should be a topological sort (prerequisites first)
- Include only meaningful dependencies, not all possible pairs
- Maximum 60 edges
"""

    try:
        groq = AsyncGroq(api_key=settings.groq_api_key)
        resp = await groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a curriculum expert. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        data = json.loads(match.group() if match else raw)
        return data.get("edges", []), data.get("study_order", topics)
    except Exception as e:
        logger.error(f"Concept graph LLM error: {e}")
        return [], topics


def _build_mermaid(nodes: list[str], edges: list[dict], mastery_map: dict = None) -> str:
    """
    Convert nodes + edges to Mermaid graph TD syntax.
    mastery_map: { topic_name: 'mastered' | 'learning' | 'not_started' }
    """
    lines = ["graph TD"]

    # Node IDs (sanitize for Mermaid)
    def node_id(name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9]', '_', name)[:30]

    mastery = mastery_map or {}

    for n in nodes:
        nid = node_id(n)
        label = n[:35]
        m = mastery.get(n, "not_started")
        if m == "mastered":
            lines.append(f'    {nid}["{label}"]:::mastered')
        elif m == "learning":
            lines.append(f'    {nid}["{label}"]:::learning')
        else:
            lines.append(f'    {nid}["{label}"]:::notStarted')

    for e in edges:
        frm = node_id(e.get("from", ""))
        to  = node_id(e.get("to", ""))
        lbl = e.get("label", "")
        if frm and to:
            if lbl:
                lines.append(f'    {frm} -->|"{lbl}"| {to}')
            else:
                lines.append(f'    {frm} --> {to}')

    # Class definitions
    lines.append("    classDef mastered   fill:#065F46,color:#fff,stroke:#034732")
    lines.append("    classDef learning   fill:#FF7A00,color:#fff,stroke:#CC5500")
    lines.append("    classDef notStarted fill:#F4F1EC,color:#1C1410,stroke:#E8E0D5")

    return "\n".join(lines)


async def build_concept_graph(
    subject_code: str,
    topics: list[str],
    mastery_map: dict = None,   # { topic: 'mastered'|'learning'|'not_started' }
) -> dict:
    """
    Build a full concept dependency graph for a subject.
    Returns:
        {
            nodes: [{ id, label, mastery }],
            edges: [{ from, to, label }],
            mermaid_code: str,
            study_order: [str]
        }
    """
    if not topics:
        return {"nodes": [], "edges": [], "mermaid_code": "", "study_order": []}

    # Deduplicate topics
    topics = list(dict.fromkeys(topics))

    # Get edges from LLM
    edges, study_order = await _get_prerequisites_from_llm(subject_code, topics)

    # Only keep edges with valid topic references
    valid_set = set(topics)
    edges = [
        e for e in edges
        if e.get("from") in valid_set and e.get("to") in valid_set
    ]

    # Build node objects
    mastery = mastery_map or {}
    nodes = [
        {
            "id":      re.sub(r'[^a-zA-Z0-9]', '_', t)[:30],
            "label":   t,
            "mastery": mastery.get(t, "not_started"),
        }
        for t in topics
    ]

    # Build Mermaid code
    mermaid = _build_mermaid(topics, edges, mastery)

    return {
        "nodes":        nodes,
        "edges":        edges,
        "mermaid_code": mermaid,
        "study_order":  study_order,
    }


async def save_concept_graph(
    pool, student_db_id: int, subject_code: str, graph: dict
) -> int:
    """Upsert a concept graph to the database. Returns row ID."""
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            """
            INSERT INTO concept_graphs
                (student_db_id, subject_code, mermaid_code, nodes_json, edges_json, study_order)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb)
            ON CONFLICT (student_db_id, subject_code) DO UPDATE
                SET mermaid_code = EXCLUDED.mermaid_code,
                    nodes_json   = EXCLUDED.nodes_json,
                    edges_json   = EXCLUDED.edges_json,
                    study_order  = EXCLUDED.study_order,
                    created_at   = NOW()
            RETURNING id
            """,
            student_db_id,
            subject_code,
            graph["mermaid_code"],
            json.dumps(graph["nodes"]),
            json.dumps(graph["edges"]),
            json.dumps(graph["study_order"]),
        )
    return row_id


async def get_cached_graph(pool, student_db_id: int, subject_code: str) -> Optional[dict]:
    """Fetch cached concept graph from DB. Returns None if not found."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT mermaid_code, nodes_json, edges_json, study_order, created_at
            FROM concept_graphs
            WHERE student_db_id = $1 AND subject_code = $2
            """,
            student_db_id, subject_code,
        )
    if not row:
        return None
    return {
        "mermaid_code": row["mermaid_code"],
        "nodes":        row["nodes_json"],
        "edges":        row["edges_json"],
        "study_order":  row["study_order"],
        "cached_at":    str(row["created_at"]),
    }
