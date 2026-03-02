"""
AI-Mentor — Visual Teaching Engine (Phase 10)
Generates Mermaid diagrams for concept visualization.
Used by the Step Teaching Engine when a concept needs visual explanation.

LLM priority: Bedrock (Claude Haiku 4.5) → Groq
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODEL
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DiagramResult:
    """Result of diagram generation."""
    mermaid_code: str           # valid Mermaid syntax
    explanation: str            # teacher explanation of the diagram (2-4 sentences)
    diagram_question: str       # question about the diagram for student
    visual_type: str            # flowchart | sequence | state | class | etc.


# ═══════════════════════════════════════════════════════════════════════════════
# MERMAID TEMPLATES — used as few-shot examples for the LLM
# ═══════════════════════════════════════════════════════════════════════════════

MERMAID_TEMPLATES = {
    "flowchart": '''flowchart TD
    A["Start"] --> B["Process Input"]
    B --> C{{"Decision?"}}
    C -->|Yes| D["Action A"]
    C -->|No| E["Action B"]
    D --> F["End"]
    E --> F''',

    "sequence": '''sequenceDiagram
    participant C as Client
    participant S as Server
    participant D as Database
    C->>S: Request
    S->>D: Query
    D-->>S: Result
    S-->>C: Response''',

    "state": '''stateDiagram-v2
    [*] --> Idle
    Idle --> Processing : input received
    Processing --> Success : valid
    Processing --> Error : invalid
    Success --> [*]
    Error --> Idle : retry''',

    "class": '''classDiagram
    class Animal {
        +String name
        +int age
        +makeSound()
    }
    class Dog {
        +fetch()
    }
    Animal <|-- Dog''',

    "er": '''erDiagram
    STUDENT ||--o{ ENROLLMENT : has
    ENROLLMENT }o--|| COURSE : for
    STUDENT {
        string id
        string name
    }
    COURSE {
        string code
        string title
    }''',

    "mindmap": '''mindmap
  root((Topic))
    Concept A
      Detail 1
      Detail 2
    Concept B
      Detail 3
    Concept C''',

    "timeline": '''timeline
    title Process Timeline
    Step 1 : Description
    Step 2 : Description
    Step 3 : Description''',

    "pie": '''pie title Distribution
    "Category A" : 40
    "Category B" : 35
    "Category C" : 25''',

    "gantt": '''gantt
    title Project Schedule
    dateFormat  YYYY-MM-DD
    section Phase 1
    Task A : a1, 2024-01-01, 7d
    Task B : a2, after a1, 5d
    section Phase 2
    Task C : a3, after a2, 3d''',

    "graph": '''flowchart LR
    A["Node 1"] --- B["Node 2"]
    B --- C["Node 3"]
    A --- C
    C --- D["Node 4"]''',

    "tree": '''flowchart TD
    A["Root"] --> B["Left Child"]
    A --> C["Right Child"]
    B --> D["Leaf 1"]
    B --> E["Leaf 2"]
    C --> F["Leaf 3"]''',

    "array": '''flowchart LR
    A["1"] --> B["3"]
    B --> C["5"]
    C --> D["7"]
    D --> E["9"]''',

    "process": '''flowchart TD
    A["Input"] --> B["Step 1"]
    B --> C["Step 2"]
    C --> D["Step 3"]
    D --> E["Output"]''',
}

# Valid Mermaid diagram type keywords (first line must start with one)
VALID_MERMAID_TYPES = {
    "flowchart", "graph", "sequenceDiagram", "classDiagram",
    "stateDiagram-v2", "stateDiagram", "erDiagram", "pie",
    "gantt", "mindmap", "timeline",
}


# ═══════════════════════════════════════════════════════════════════════════════
# MERMAID VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def validate_mermaid(code: str) -> tuple[bool, str]:
    """
    Basic syntax validation for Mermaid code.
    Returns (is_valid, cleaned_code_or_error_msg).
    """
    if not code or not code.strip():
        return False, "Empty diagram code"

    cleaned = code.strip()

    # Remove markdown fences if accidentally included
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    if not cleaned:
        return False, "Empty after cleanup"

    # Check first line starts with valid Mermaid type
    first_line = cleaned.split("\n")[0].strip()
    has_valid_type = any(first_line.startswith(t) for t in VALID_MERMAID_TYPES)

    if not has_valid_type:
        return False, f"Invalid diagram type: '{first_line}'"

    # Check for common syntax errors
    if cleaned.count("```") > 0:
        return False, "Contains markdown code fences inside diagram"

    # Check minimum content (at least 2 lines)
    lines = [l for l in cleaned.split("\n") if l.strip()]
    if len(lines) < 2:
        return False, "Diagram too short — needs at least 2 lines"

    return True, cleaned


def _sanitize_mermaid(code: str) -> str:
    """Clean up common LLM Mermaid mistakes."""
    # Remove any markdown fences
    clean = re.sub(r'```(?:mermaid)?\s*', '', code).strip()
    clean = re.sub(r'```\s*$', '', clean).strip()

    # Remove inline CSS/style blocks that break rendering
    clean = re.sub(r'style\s+\w+\s+.*$', '', clean, flags=re.MULTILINE)
    clean = re.sub(r'classDef\s+.*$', '', clean, flags=re.MULTILINE)

    # Remove empty lines at start/end
    lines = clean.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGRAM GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

DIAGRAM_SYSTEM = """You are a visual teaching assistant that creates Mermaid diagrams.
You must return ONLY a valid JSON object — no preamble, no markdown fences.

Schema:
{
  "mermaid_code": "<valid Mermaid diagram code — NO ```mermaid fences, just the raw code>",
  "explanation": "<2-4 sentence teacher explanation of the diagram. Start with 'Look at this diagram.' Refer to specific parts by name.>",
  "diagram_question": "<One question about the diagram for the student to answer>"
}

Mermaid rules:
- Use ONLY these types: flowchart TD, flowchart LR, sequenceDiagram, stateDiagram-v2, classDiagram, erDiagram, pie, gantt, mindmap, timeline
- Max 10 nodes. Keep labels short (2-4 words per node).
- NO inline styles, NO CSS, NO fill colors, NO classDef.
- Use double quotes for labels containing special characters: A["Label (info)"]
- For flowcharts: use --> for arrows, --- for lines
- Ensure all node IDs are unique.
- Do NOT wrap the code in ```mermaid fences.

Explanation rules:
- Start with "Look at this diagram."
- Point to specific nodes or arrows: "Notice how X connects to Y."
- Be conversational — this will be spoken aloud.
- Keep to 2-4 sentences maximum.

Question rules:
- Ask about a specific part of the diagram.
- Example: "Looking at the diagram, what happens after the decision node?"
"""


async def generate_mermaid_diagram(
    topic: str,
    concept_title: str,
    visual_type: str,
    description: str,
    ctx: dict,
) -> DiagramResult:
    """
    Generate a Mermaid diagram for a teaching concept.

    Args:
        topic: The lesson topic (e.g. "Binary Search")
        concept_title: The specific concept (e.g. "Midpoint Calculation")
        visual_type: Diagram type from visual plan (e.g. "flowchart", "array")
        description: What the diagram should show
        ctx: build_tutor_context() output

    Returns: DiagramResult with mermaid_code, explanation, diagram_question
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    # Get the teacher LLM (import here to avoid circular deps)
    from teacher_brain import get_teacher_llm

    profile = ctx.get("profile", {})
    student_name = profile.get("name", "Student").split()[0]
    bloom = ctx.get("bloom_level", 2)

    # Get a template example for the requested type
    template_key = visual_type.lower()
    template = MERMAID_TEMPLATES.get(template_key, MERMAID_TEMPLATES.get("flowchart", ""))

    user_prompt = f"""Topic: {topic}
Concept: {concept_title}
Diagram type requested: {visual_type}
Description: {description}
Student: {student_name} | Bloom level: {bloom}/6

Here is an example of the "{visual_type}" diagram type for reference:
{template}

Now generate a diagram specifically for "{concept_title}" in the topic "{topic}".
Make it educational and clear. Return JSON only."""

    llm = get_teacher_llm(temperature=0.3, max_tokens=800)

    try:
        result = await llm.ainvoke([
            SystemMessage(content=DIAGRAM_SYSTEM),
            HumanMessage(content=user_prompt),
        ])
        raw = (result.content or "").strip()

        # Parse JSON robustly
        clean = raw
        if "```json" in clean:
            clean = clean.split("```json", 1)[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```", 1)[1].split("```")[0].strip()
        if not clean.startswith("{"):
            m = re.search(r"\{.*\}", clean, re.DOTALL)
            if m:
                clean = m.group(0)

        data = json.loads(clean)
        mermaid_raw = data.get("mermaid_code", "")
        explanation = data.get("explanation", f"Look at this diagram showing {concept_title}.")
        question = data.get("diagram_question", f"What can you learn from this {visual_type} diagram?")

        # Sanitize and validate
        mermaid_clean = _sanitize_mermaid(mermaid_raw)
        is_valid, validated = validate_mermaid(mermaid_clean)

        if not is_valid:
            logger.warning(f"Generated Mermaid invalid ({validated}), using template fallback")
            mermaid_clean = _build_fallback_diagram(visual_type, concept_title, topic)

        return DiagramResult(
            mermaid_code=mermaid_clean if is_valid else mermaid_clean,
            explanation=explanation,
            diagram_question=question,
            visual_type=visual_type,
        )

    except Exception as e:
        logger.error(f"Diagram generation failed for '{concept_title}': {e}", exc_info=True)
        fallback_code = _build_fallback_diagram(visual_type, concept_title, topic)
        return DiagramResult(
            mermaid_code=fallback_code,
            explanation=f"Look at this {visual_type} diagram for {concept_title}. It shows the core structure of this concept.",
            diagram_question=f"Looking at this diagram, can you identify the main components of {concept_title}?",
            visual_type=visual_type,
        )


def _build_fallback_diagram(visual_type: str, concept_title: str, topic: str) -> str:
    """Build a simple fallback diagram using templates."""
    template_key = visual_type.lower()

    if template_key in ("flowchart", "process"):
        return f"""flowchart TD
    A["{topic}"] --> B["{concept_title}"]
    B --> C["Key Idea"]
    C --> D["Application"]"""
    elif template_key in ("tree",):
        return f"""flowchart TD
    A["{topic}"] --> B["Part 1"]
    A --> C["Part 2"]
    B --> D["{concept_title}"]"""
    elif template_key in ("sequence",):
        return f"""sequenceDiagram
    participant S as Student
    participant T as {concept_title}
    S->>T: Input
    T-->>S: Output"""
    elif template_key in ("array", "graph"):
        return f"""flowchart LR
    A["Element 1"] --> B["Element 2"]
    B --> C["Element 3"]
    C --> D["Element 4"]"""
    elif template_key in ("mindmap",):
        return f"""mindmap
  root(({topic}))
    {concept_title}
      Key Idea 1
      Key Idea 2
    Related Concept"""
    else:
        # Default to flowchart
        return f"""flowchart TD
    A["{concept_title}"] --> B["Step 1"]
    B --> C["Step 2"]
    C --> D["Result"]"""
