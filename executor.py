"""Quantum Executor: saves generated code and optionally submits to IBM Quantum."""

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).parent / "outputs"
TMP_DIR = Path(__file__).parent / "tmp"


def save_and_run(
    code: str,
    dry_run: bool = False,
    instance: str | None = None,
) -> dict:
    """Save generated circuit code and optionally execute it.

    Args:
        code: Python source code string for the quantum circuit.
        dry_run: If True, save to local tmp/ folder and return without submitting.
        instance: IBM Quantum hub/group/project string (e.g. 'ibm-q/open/main').

    Returns:
        dict with keys: 'script_path', 'job_id' (if submitted), 'status'.
    """
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_name = f"{timestamp}_circuit.py"

    if dry_run:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        script_path = TMP_DIR / script_name
        logger.info("Dry-run mode: saving circuit code to %s", script_path)
    else:
        script_path = OUTPUTS_DIR / script_name
        logger.info("Saving circuit code to %s", script_path)

    script_path.write_text(code, encoding="utf-8")
    logger.info("Circuit script saved: %s", script_path)

    if dry_run:
        logger.info("Dry-run enabled — stopping before IBM Quantum submission.")
        return {"script_path": str(script_path), "status": "dry_run"}

    # Inject the IBM_TOKEN and optional instance env vars before running
    env = os.environ.copy()
    ibm_token = os.getenv("IBM_QUANTUM_TOKEN")
    if ibm_token:
        env["IBM_TOKEN"] = ibm_token
    if instance:
        env["IBM_INSTANCE"] = instance
        logger.info("Using IBM Quantum instance: %s", instance)

    logger.info("Submitting circuit to IBM Quantum...")
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes max
        )
    except subprocess.TimeoutExpired:
        logger.error("IBM Quantum job timed out after 600 seconds.")
        return {"script_path": str(script_path), "status": "timeout"}

    if result.returncode != 0:
        logger.error("Circuit execution failed:\n%s", result.stderr)
        return {
            "script_path": str(script_path),
            "status": "error",
            "stderr": result.stderr,
        }

    stdout = result.stdout
    logger.debug("Circuit execution output:\n%s", stdout)

    # Extract Job ID from stdout (generated code prints it)
    job_id = _extract_job_id(stdout)
    if job_id:
        logger.info("IBM Quantum Job ID: %s", job_id)
    else:
        logger.warning("Could not extract Job ID from execution output.")

    # Extract queue status
    status = _extract_status(stdout)
    logger.info("IBM Quantum Queue Status: %s", status)

    return {
        "script_path": str(script_path),
        "job_id": job_id,
        "status": status,
        "stdout": stdout,
    }


def _extract_job_id(text: str) -> str | None:
    """Try to parse a Job ID from execution output."""
    import re
    match = re.search(r"job[_\s]?id[:\s]+([a-z0-9]+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    # IBM job IDs are typically long hex strings
    match = re.search(r"\b([a-f0-9]{20,})\b", text)
    return match.group(1) if match else None


def _extract_status(text: str) -> str:
    """Try to parse queue/job status from execution output."""
    import re
    match = re.search(
        r"(QUEUED|RUNNING|COMPLETED|DONE|FAILED|CANCELLED)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).upper() if match else "UNKNOWN"
