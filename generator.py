"""Code Architect: uses Anthropic Claude with prompt caching to generate Qiskit 1.x code."""

import logging
import os

import anthropic

logger = logging.getLogger(__name__)

_CACHED_SYSTEM_PROMPT = """You are an expert Quantum Computing Engineer specialising in Qiskit 1.x and IBM Quantum.
Your task is to generate complete, standalone, production-ready Python scripts for Quantum Machine Learning.

Strict coding constraints you MUST follow:
- Use Qiskit 1.x APIs only (no deprecated Qiskit 0.x patterns).
- Use `qiskit_ibm_runtime.SamplerV2` for circuit execution.
- Use `ZZFeatureMap` (reps=2) as the feature map.
- Use `RealAmplitudes` as the variational ansatz.
- Limit `shots` to 1024.
- IBM Quantum authentication: `QiskitRuntimeService(channel='ibm_quantum', token=os.getenv('IBM_TOKEN'))`.
- The script must be self-contained: include all imports, data loading, circuit construction, execution, and result printing.
- Include a `if __name__ == '__main__':` guard.
- Do NOT include placeholder comments like '# your code here' — emit complete, runnable code.

Output ONLY valid Python code with no markdown fences, no explanations before or after the code block."""

_USER_PROMPT_TEMPLATE = """Generate a standalone Python script using Qiskit 1.x for a Quantum Machine Learning classification task.

Dataset metadata:
{json_metadata}

Target column: {target_column}
CSV file path: {csv_path}

Requirements:
- Load the CSV, preprocess with StandardScaler and LabelEncoder.
- Build a `ZZFeatureMap` (reps=2) + `RealAmplitudes` ansatz circuit.
- Use COBYLA optimiser with `maxiter=100`.
- Use `SamplerV2` via `QiskitRuntimeService` to execute the circuit.
- Print final training accuracy and the IBM Job ID after execution.
- Save the circuit diagram to 'outputs/circuit_diagram.txt' using circuit.draw(output='text').
"""


def generate_circuit_code(metadata: dict, target_column: str, csv_path: str) -> str:
    """Call Claude with prompt caching and return the generated Python code string."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)

    import json
    json_metadata = json.dumps(metadata, indent=2)
    user_message = _USER_PROMPT_TEMPLATE.format(
        json_metadata=json_metadata,
        target_column=target_column,
        csv_path=csv_path,
    )

    logger.info("Requesting Qiskit circuit code from Claude (with prompt caching)...")
    logger.debug("Generator user prompt:\n%s", user_message)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _CACHED_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {"role": "user", "content": user_message},
        ],
    )

    generated_code = response.content[0].text.strip()

    # Strip markdown code fences if Claude included them despite the instruction
    if generated_code.startswith("```"):
        lines = generated_code.splitlines()
        # Remove opening fence (```python or ```)
        lines = lines[1:] if lines[0].startswith("```") else lines
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        generated_code = "\n".join(lines)

    logger.debug("Generated code (%d chars):\n%s", len(generated_code), generated_code)

    cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0)
    cache_read = getattr(response.usage, "cache_read_input_tokens", 0)
    logger.info(
        "Claude usage — input: %d, output: %d, cache_created: %d, cache_read: %d",
        response.usage.input_tokens,
        response.usage.output_tokens,
        cache_creation,
        cache_read,
    )

    return generated_code
