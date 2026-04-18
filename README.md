# Q-Agent CLI

**Q-Agent CLI** is a strategic gatekeeper for Quantum Machine Learning (QML). It assesses a CSV dataset locally to determine whether it is worth submitting to IBM Quantum hardware, before consuming expensive cloud credits or limited QPU time.

The tool runs a four-stage pipeline: statistical profiling → local LLM decision → Qiskit code generation → IBM Quantum submission.

---

## How it works

```
CSV dataset ──► Statistical Profiler ──► Ollama (local LLM) ──► Claude (code gen) ──► IBM Quantum
                  (scikit-learn)           [ABORT / PROCEED]      (Anthropic API)      (Qiskit Runtime)
```

1. **Statistical Profiler** — benchmarks the dataset locally using scikit-learn (LinearSVC, RandomForest, PCA). No raw data leaves the machine.
2. **Strategic Decision Engine** — a locally-running Ollama LLM evaluates the benchmark metadata and decides `[PROCEED]` or `[ABORT]` with a 3-bullet rationale. If `[ABORT]`, the pipeline stops here.
3. **Code Architect** — Claude (Anthropic API) generates a complete, standalone Qiskit 2.x Python script tailored to the dataset's profile.
4. **Quantum Executor** — saves the generated script and, unless `--dry-run` is set, submits it to IBM Quantum via Qiskit Runtime, logging the Job ID and queue status.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | |
| [Ollama](https://ollama.com) | latest | Must be running locally on port 11434 |
| Ollama model | `llama3` (default) | Change via `OLLAMA_MODEL` env var |
| Anthropic API key | — | For Claude code generation (Stage 3) |
| IBM Quantum account | — | Required only for live QPU submission |

---

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/steveh250/IBMQuantum-Agent.git
cd IBMQuantum-Agent
```

**2. Create and activate a virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Configure environment variables**

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```bash
ANTHROPIC_API_KEY=sk-ant-...          # Anthropic API key
IBM_QUANTUM_TOKEN=...                 # IBM Quantum API token
OLLAMA_BASE_URL=http://localhost:11434/v1  # Default; change if Ollama runs elsewhere
OLLAMA_MODEL=llama3                   # Optional: override the Ollama model
```

**5. Start Ollama** (if not already running)

```bash
ollama serve
ollama pull llama3      # or whichever model you set in OLLAMA_MODEL
```

---

## Usage

```
python main.py --file PATH --target COLUMN [options]
```

### Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--file PATH` | Yes | — | Path to the CSV dataset |
| `--target COLUMN` | Yes | — | Name of the label/target column in the CSV |
| `--log-level LEVEL` | No | `info` | Verbosity: `info` or `debug` |
| `--dry-run` | No | `False` | Generate code but skip IBM Quantum submission; saves script to `tmp/` |
| `--instance HUB/GROUP/PROJECT` | No | — | IBM Quantum hub/group/project (e.g. `ibm-q/open/main`) |

### Examples

**Standard run** — profile, decide, generate code, and submit to IBM Quantum:
```bash
python main.py --file data/my_dataset.csv --target label
```

**Dry run** — generate and inspect the Qiskit script without submitting:
```bash
python main.py --file data/my_dataset.csv --target label --dry-run
```

**Debug mode** — print raw benchmark JSON, full Ollama response, and generated code:
```bash
python main.py --file data/my_dataset.csv --target label --log-level debug
```

**With a specific IBM Quantum instance:**
```bash
python main.py --file data/my_dataset.csv --target label --instance ibm-q/open/main
```

---

## Output files

| Location | Contents |
|---|---|
| `outputs/{timestamp}_circuit.py` | Generated Qiskit script (live run) |
| `outputs/circuit_diagram.txt` | Text-art circuit diagram (written by the generated script) |
| `tmp/{timestamp}_circuit.py` | Generated Qiskit script (dry-run only; survives reboots) |

---

## Abort conditions

The pipeline will stop early and print a rationale if any of the following are true:

| Condition | Threshold | Reason |
|---|---|---|
| LinearSVC accuracy | > 0.90 | Dataset is classically trivial — quantum offers no advantage |
| PCA 95% variance components | > 16 | Exceeds current QPU qubit limits |
| Row count | > 50,000 | Classical methods are more efficient at this scale |

These checks are applied twice: first by the local profiler (hard cutoff), then by the Ollama LLM (reasoned rationale).

---

## Project structure

```
IBMQuantum-Agent/
├── main.py              # CLI entry point — orchestrates the four-stage pipeline
├── profiler.py          # Stage 1: statistical benchmarking (scikit-learn)
├── decision.py          # Stage 2: quantum suitability decision (Ollama via OpenAI SDK)
├── generator.py         # Stage 3: Qiskit 2.x code generation (Claude / Anthropic SDK)
├── executor.py          # Stage 4: script saving and IBM Quantum submission
├── outputs/             # Generated circuit scripts (live runs)
├── tmp/                 # Generated circuit scripts (dry-runs)
├── requirements.txt
├── .env.example
└── ARCHITECTURE.md      # System design and design decisions
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `pandas` | CSV loading and preprocessing |
| `scikit-learn` | LinearSVC, RandomForest, PCA, StandardScaler, LabelEncoder |
| `qiskit>=2.0` | Quantum circuit construction (`zz_feature_map`, `real_amplitudes`) |
| `qiskit-ibm-runtime` | IBM Quantum job submission via `SamplerV2` |
| `anthropic` | Claude API client with prompt caching |
| `openai` | Ollama client (OpenAI-compatible API) |
| `python-dotenv` | `.env` file loading |
| `rich` | Terminal progress spinners and formatted output |
