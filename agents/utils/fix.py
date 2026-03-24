import os

def replace_in_file(filepath, replacements):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    for old_str, new_str in replacements:
        if old_str in content:
            content = content.replace(old_str, new_str)
            print(f"Replaced a chunk in {filepath[-20:]}")
        else:
            print(f"WARNING: Chunk not found in {filepath[-20:]}")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

base = r"d:\Ai-mentor\agents"

# 1. schedule.py
sched = os.path.join(base, "agents", "schedule.py")
sched_repl = [
    ("from langchain_groq import ChatGroq", "from utils.llm import get_llm"),
    (
"""    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.4,
        max_tokens=3000,
    )""", 
"""    llm, provider = get_llm(temperature=0.4, max_tokens=3000)"""
    ),
    (
"""        logger.info("✅ LLM schedule generated successfully")
        return week

    except Exception as e:
        logger.warning(f"LLM schedule generation failed ({e}), using deterministic fallback")
        return _deterministic_fallback(profile, peak_hour)""",
"""        logger.info("✅ LLM schedule generated successfully")
        return week, provider

    except Exception as e:
        logger.warning(f"LLM schedule generation failed ({e}), using deterministic fallback")
        return _deterministic_fallback(profile, peak_hour), "deterministic\""""
    ),
    (
"""    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.5,
        max_tokens=600,
    )""",
"""    llm, provider = get_llm(temperature=0.5, max_tokens=600)"""
    ),
    (
"""    try:
        week = await generate_ai_schedule(profile, learning_dna)
    except Exception as e:
        logger.error(f"schedule_node generate_ai_schedule failed ({e}), using fallback")
        peak = learning_dna.get("peak_hour") or 8
        week = _deterministic_fallback(profile, peak)""",
"""    try:
        week, provider = await generate_ai_schedule(profile, learning_dna)
    except Exception as e:
        logger.error(f"schedule_node generate_ai_schedule failed ({e}), using fallback")
        peak = learning_dna.get("peak_hour") or 8
        week = _deterministic_fallback(profile, peak)
        provider = "deterministic\""""
    )
]

# 2. orchestrator.py
orch = os.path.join(base, "orchestrator.py")
orch_repl = [
    ("from langchain_groq import ChatGroq", "from agents.utils.llm import get_llm"),
    (
"""    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.1,
        max_tokens=800,
    )""",
"""    llm, provider = get_llm(temperature=0.1, max_tokens=800)"""
    ),
    (
"""    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.4,
        max_tokens=800,
    )""",
"""    llm, provider = get_llm(temperature=0.4, max_tokens=800)"""
    )
]

# 3. agents/prediction.py, emotional.py, career.py
for f in ["prediction.py", "emotional.py", "career.py"]:
    fpath = os.path.join(base, "agents", f)
    replace_in_file(fpath, [
        ("from langchain_groq import ChatGroq", ""),
        ("from langchain_openai import ChatOpenAI", "from utils.llm import get_llm"), # it will complain if duplicated but it's simpler
    ])

replace_in_file(sched, sched_repl)
replace_in_file(orch, orch_repl)

