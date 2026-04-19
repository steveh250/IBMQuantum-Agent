"""Strategic Decision Engine: queries local Ollama LLM to assess quantum suitability."""

import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a Senior Quantum Architect applying a strict, rules-based checklist. "
    "You follow the decision rules exactly as written. You do NOT invent additional "
    "criteria or apply subjective judgment beyond what is specified. "
    "Your output always begins with exactly [PROCEED] or [ABORT] on the first line."
)

_USER_PROMPT_TEMPLATE = """\
You are evaluating a dataset for Quantum Machine Learning suitability.

Dataset metadata (JSON):
{json_metadata}

═══════════════════════════════════════════════════
STEP 1 — Apply the three hard ABORT rules IN ORDER.
Stop and output [ABORT] at the first rule that fires.
═══════════════════════════════════════════════════

Rule A: IF linear_svc_acc > 0.90  → [ABORT]  reason: "classically trivial"
Rule B: IF pca_95_count   > 16    → [ABORT]  reason: "exceeds QPU qubit limit"
Rule C: IF rows           > 50000 → [ABORT]  reason: "classical methods more efficient"

Evaluating rules against the metadata above:
  Rule A: linear_svc_acc = {linear_svc_acc} → {rule_a_result}
  Rule B: pca_95_count   = {pca_95_count}   → {rule_b_result}
  Rule C: rows           = {rows}           → {rule_c_result}

═══════════════════════════════════════════════════
STEP 2 — If NO rule fired, assess the Classical Gap.
═══════════════════════════════════════════════════

complexity_gap = rf_acc − linear_svc_acc = {complexity_gap}

  • gap < 0.10  → The linear model already captures most structure; quantum kernel unlikely to help → [ABORT]
  • gap ≥ 0.10  → Non-linear structure present that a quantum kernel may exploit              → [PROCEED]

═══════════════════════════════════════════════════
OUTPUT FORMAT (mandatory)
═══════════════════════════════════════════════════

Line 1 must be exactly one of: [PROCEED] or [ABORT]
Then provide exactly 3 bullet points explaining which rules fired (or did not fire) and why.
Do not add any text before [PROCEED] or [ABORT].\
"""


def _build_prompt(metadata: dict) -> str:
    linear_svc_acc = metadata.get("linear_svc_acc", 0)
    pca_95_count   = metadata.get("pca_95_count", 0)
    rows           = metadata.get("rows", 0)
    complexity_gap = metadata.get("complexity_gap", 0)

    return _USER_PROMPT_TEMPLATE.format(
        json_metadata=json.dumps(metadata, indent=2),
        linear_svc_acc=linear_svc_acc,
        pca_95_count=pca_95_count,
        rows=rows,
        complexity_gap=complexity_gap,
        rule_a_result="FIRES → ABORT" if linear_svc_acc > 0.90  else "does not fire",
        rule_b_result="FIRES → ABORT" if pca_95_count   > 16    else "does not fire",
        rule_c_result="FIRES → ABORT" if rows           > 50_000 else "does not fire",
    )


def evaluate(metadata: dict) -> tuple[str, str]:
    """Send metadata to Ollama and return (decision, rationale).

    decision is either 'PROCEED' or 'ABORT'.
    Raises RuntimeError if the LLM response cannot be parsed.
    """
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    model = os.getenv("OLLAMA_MODEL", "llama3")

    client = OpenAI(base_url=base_url, api_key="ollama")

    user_message = _build_prompt(metadata)

    logger.info("Querying Ollama at %s with model '%s'...", base_url, model)
    logger.debug("Ollama user prompt:\n%s", user_message)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
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
