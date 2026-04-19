#!/usr/bin/env python3
"""Q-Agent CLI: Quantum Suitability Gatekeeper for CSV datasets."""

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner
from rich.status import Status
from rich.text import Text

load_dotenv()

console = Console()


def _configure_logging(log_level: str) -> None:
    level = logging.DEBUG if log_level.lower() == "debug" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="q-agent",
        description="Q-Agent CLI: Assess CSV dataset Quantum Suitability and generate Qiskit code.",
    )
    parser.add_argument(
        "--file",
        required=True,
        type=Path,
        metavar="PATH",
        help="Path to the CSV dataset.",
    )
    parser.add_argument(
        "--target",
        required=True,
        type=str,
        metavar="COLUMN",
        help="Name of the target (label) column in the CSV.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["info", "debug"],
        metavar="LEVEL",
        help="Console verbosity: 'info' (default) or 'debug'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Stop before IBM Quantum submission; save generated code to local tmp/.",
    )
    parser.add_argument(
        "--instance",
        default=None,
        type=str,
        metavar="INSTANCE",
        help=(
            "IBM Quantum Platform instance name or CRN (e.g. 'open-instance'). "
            "Only needed when you have multiple instances and want to target a specific one. "
            "Omit this flag for the free/open plan — the service auto-discovers the correct instance. "
            "Note: the old hub/group/project format (ibm-q/open/main) is NOT valid for ibm_quantum_platform."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _configure_logging(args.log_level)

    console.print(
        Panel.fit(
            "[bold cyan]Q-Agent CLI[/bold cyan] — Quantum Suitability Gatekeeper",
            border_style="cyan",
        )
    )

    csv_path = str(args.file)
    if not Path(csv_path).exists():
        console.print(f"[bold red]Error:[/bold red] File not found: {csv_path}")
        sys.exit(1)

    # ── Stage 1: Statistical Profiler ─────────────────────────────────────────
    from profiler import profile

    with Status("[bold green]Stage 1:[/bold green] Benchmarking data...", console=console):
        try:
            metadata = profile(csv_path, args.target)
        except ValueError as exc:
            console.print(f"[bold red]Profiler error:[/bold red] {exc}")
            sys.exit(1)

    console.print("[bold green]✓[/bold green] Statistical profile complete.")

    if args.log_level == "debug":
        console.print_json(json.dumps(metadata, indent=2))

    # Check local abort flags set by profiler (before calling LLM)
    if "abort" in metadata:
        console.print(
            Panel(
                f"[bold red][ABORT][/bold red] {metadata['abort']}",
                title="Profiler Hard Limit",
                border_style="red",
            )
        )
        sys.exit(0)

    # ── Stage 2: Strategic Decision Engine (Ollama) ────────────────────────────
    from decision import evaluate

    with Status(
        "[bold green]Stage 2:[/bold green] Consulting Quantum Architect (Ollama)...",
        console=console,
    ):
        try:
            decision, rationale = evaluate(metadata)
        except Exception as exc:
            console.print(f"[bold red]Decision engine error:[/bold red] {exc}")
            sys.exit(1)

    if args.log_level == "debug":
        console.print(
            Panel(rationale, title="Ollama Full Response", border_style="yellow")
        )

    if decision == "ABORT":
        console.print(
            Panel(
                f"[bold red][ABORT][/bold red]\n\n{rationale}",
                title="Strategic Decision: ABORT",
                border_style="red",
            )
        )
        sys.exit(0)

    console.print(
        Panel(
            f"[bold green][PROCEED][/bold green]\n\n{rationale}",
            title="Strategic Decision: PROCEED",
            border_style="green",
        )
    )

    # ── Stage 3: Code Architect (Claude / Anthropic) ──────────────────────────
    from generator import generate_circuit_code

    with Status(
        "[bold green]Stage 3:[/bold green] Generating Qiskit circuit code (Claude)...",
        console=console,
    ):
        try:
            code = generate_circuit_code(metadata, args.target, csv_path)
        except EnvironmentError as exc:
            console.print(f"[bold red]Generator error:[/bold red] {exc}")
            sys.exit(1)
        except Exception as exc:
            console.print(f"[bold red]Code generation failed:[/bold red] {exc}")
            sys.exit(1)

    console.print("[bold green]✓[/bold green] Qiskit circuit code generated.")

    if args.log_level == "debug":
        console.print(Panel(code, title="Generated Circuit Code", border_style="blue"))

    # ── Stage 4: Quantum Executor (IBM Quantum) ────────────────────────────────
    from executor import save_and_run

    dry_run_msg = " (dry-run)" if args.dry_run else ""
    with Status(
        f"[bold green]Stage 4:[/bold green] Saving and submitting circuit{dry_run_msg}...",
        console=console,
    ):
        result = save_and_run(code, dry_run=args.dry_run, instance=args.instance)

    console.print(
        f"[bold green]✓[/bold green] Script saved: [cyan]{result['script_path']}[/cyan]"
    )

    if args.dry_run:
        console.print("[yellow]Dry-run complete. IBM Quantum submission skipped.[/yellow]")
    else:
        job_id = result.get("job_id", "N/A")
        status = result.get("status", "UNKNOWN")
        console.print(
            Panel(
                f"Job ID:  [bold cyan]{job_id}[/bold cyan]\n"
                f"Status:  [bold]{status}[/bold]",
                title="IBM Quantum Submission",
                border_style="cyan",
            )
        )

    console.print("\n[bold cyan]Q-Agent pipeline complete.[/bold cyan]")


if __name__ == "__main__":
    main()
