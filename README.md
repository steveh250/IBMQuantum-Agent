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
| `--instance INSTANCE` | No | — | IBM Quantum Platform instance name or CRN. **Omit for the free/open plan** — the service auto-discovers `open-instance`. The old `hub/group/project` format (`ibm-q/open/main`) is not valid for `ibm_quantum_platform`. |

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

**With a specific IBM Quantum instance** (paid/enterprise plans only — omit for free/open plan):
```bash
python main.py --file data/my_dataset.csv --target label --instance open-instance
```

---

## Test datasets

Two ready-made datasets are included in `data/` to validate the pipeline end-to-end without needing real experimental data.

### `data/test_dataset_abort.csv` — Particle Beam Classification

Simulates a detector classifying **protons** vs **pions** from four clearly separated physical signatures (energy, momentum, transverse momentum, ionisation rate). The two particle types occupy completely distinct regions of feature space, making them trivially separable by a linear classifier.

| Metric | Value | Expected outcome |
|---|---|---|
| Rows | 1,000 | ✓ below 50,000 |
| Features | 4 | ✓ below 16 PCA components |
| LinearSVC accuracy | **1.000** | ⛔ triggers ABORT (> 0.90) |
| Complexity gap | 0.000 | No quantum advantage |

**Target column:** `particle_type`

```bash
python main.py --file data/test_dataset_abort.csv --target particle_type
```

Expected output: the pipeline prints `[ABORT] dataset is classically trivial` after Stage 1 and exits before making any API call.

---

### `data/test_dataset_run.csv` — Quantum Materials Phase Classification (PoC-optimised)

Simulates classifying condensed-matter samples as either a **topological insulator** or a **trivial insulator** phase. The phase boundary is driven by an XOR-like relationship between spin-orbit coupling and crystal field splitting — the two primary topological order parameters. LinearSVC cannot represent a 4-quadrant boundary, so the complexity gap is high.

Deliberately simplified for fast QPU execution: **4 features → 4-qubit circuit**, **200 samples → fewer COBYLA evaluations**, and `reps=1` in the generator for shallow circuit depth. This reduces the circuit from ~96 gates (original 8-qubit, reps=2) to ~20 gates.

| Metric | Value | Expected outcome |
|---|---|---|
| Rows | 200 | ✓ below 50,000 |
| Features | 4 | ✓ 4-qubit circuit — fast on QPU |
| LinearSVC accuracy | **0.530** | ✓ well below 0.90 (can't learn XOR) |
| RandomForest accuracy | 1.000 | Strong non-linear signal |
| Complexity gap | **0.470** | Very high — strong justification for quantum kernel |

**Target column:** `phase`

```bash
# Dry run — inspect the generated Qiskit script without submitting to IBM Quantum
python main.py --file data/test_dataset_run.csv --target phase --dry-run

# Full run — generate code and submit to IBM Quantum (omit --instance for free/open plan)
python main.py --file data/test_dataset_run.csv --target phase

# Debug mode — see raw benchmark JSON, full Ollama rationale, and generated code
python main.py --file data/test_dataset_run.csv --target phase --dry-run --log-level debug
```

Expected output: the pipeline proceeds through all four stages, generating a `zz_feature_map` + `real_amplitudes` Qiskit 2.x circuit with `SamplerV2` and (if not dry-run) submitting it to IBM Quantum.

---

### Regenerating the datasets

The datasets were produced by `generate_test_data.py`. Run it to recreate them or to inspect the sanity-check statistics:

```bash
python generate_test_data.py
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
├── main.py                          # CLI entry point — orchestrates the four-stage pipeline
├── profiler.py                      # Stage 1: statistical benchmarking (scikit-learn)
├── decision.py                      # Stage 2: quantum suitability decision (Ollama via OpenAI SDK)
├── generator.py                     # Stage 3: Qiskit 2.x code generation (Claude / Anthropic SDK)
├── executor.py                      # Stage 4: script saving and IBM Quantum submission
├── data/
│   ├── test_dataset_abort.csv       # Particle beam dataset — triggers ABORT (LinearSVC = 1.00)
│   └── test_dataset_run.csv         # Quantum materials dataset — triggers PROCEED (gap = 0.47)
├── generate_test_data.py            # Script that created the datasets above
├── outputs/                         # Generated circuit scripts (live runs)
├── tmp/                             # Generated circuit scripts (dry-runs)
├── requirements.txt
├── .env.example
└── ARCHITECTURE.md                  # System design and design decisions
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
