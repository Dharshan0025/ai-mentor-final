import logging
from config import settings

logger = logging.getLogger(__name__)

def get_llm(temperature: float = 0.2, max_tokens: int = 1500):
    """
    Return Groq LLM (fast). Falls back to NVIDIA NIM if Groq is unavailable.
    Returns: (llm_instance, provider_name_string)
    """
    if settings.groq_api_key:
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                temperature=temperature,
                max_tokens=max_tokens,
                request_timeout=30,
            ), "groq"
        except Exception as e:
            logger.warning(f"Groq init failed ({e}), falling back to NVIDIA")

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        model=settings.nvidia_model,
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout=60,
    ), "nvidia"
