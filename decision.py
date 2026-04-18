"""Strategic Decision Engine: queries local Ollama LLM to assess quantum suitability."""

import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a Senior Quantum Architect. Your role is to evaluate whether a dataset "
    "is suitable for Quantum Machine Learning. You apply strict decision rules and "
    "provide concise, evidence-based rationale."
)

_USER_PROMPT_TEMPLATE = (
    "Analyze this JSON metadata: {json_metadata}.\n\n"
    "**Decision Rules:**\n"
    "- If `linear_svc_acc` > 0.90: ABORT (Classically trivial).\n"
    "- If `pca_95_count` > 16: ABORT (Hardware qubit limit).\n"
    "- If `rows` > 50,000: ABORT (Classical efficiency).\n\n"
    "**Objective:** Does the 'Classical Gap' justify a Quantum Kernel?\n\n"
    "**Output:** Start with [PROCEED] or [ABORT] then give a 3-bullet rationale."
)


def evaluate(metadata: dict) -> tuple[str, str]:
    """Send metadata to Ollama and return (decision, rationale).

    decision is either 'PROCEED' or 'ABORT'.
    Raises RuntimeError if the LLM response cannot be parsed.
    """
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.getenv("OLLAMA_MODEL", "llama3")

    client = OpenAI(base_url=base_url, api_key="ollama")

    json_metadata = json.dumps(metadata, indent=2)
    user_message = _USER_PROMPT_TEMPLATE.format(json_metadata=json_metadata)

    logger.info("Querying Ollama at %s with model '%s'...", base_url, model)
    logger.debug("Ollama user prompt:\n%s", user_message)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
    )

    raw_text = response.choices[0].message.content.strip()
    logger.debug("Ollama raw response:\n%s", raw_text)

    # Circuit breaker: parse first word for [PROCEED] or [ABORT]
    first_word = raw_text.split()[0].upper().strip("[]") if raw_text else ""

    if first_word == "PROCEED":
        decision = "PROCEED"
    elif first_word == "ABORT":
        decision = "ABORT"
    else:
        # Fall back to scanning the full text
        upper_text = raw_text.upper()
        if "[ABORT]" in upper_text or "ABORT" in upper_text.split()[:5]:
            decision = "ABORT"
        elif "[PROCEED]" in upper_text or "PROCEED" in upper_text.split()[:5]:
            decision = "PROCEED"
        else:
            raise RuntimeError(
                f"Could not parse [PROCEED] or [ABORT] from Ollama response:\n{raw_text}"
            )

    # Strip the decision tag from rationale for clean display
    rationale = raw_text
    return decision, rationale
