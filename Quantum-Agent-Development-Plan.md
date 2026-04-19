# Technical Design Document: Q-Agent CLI
## As-Built Reference (updated to reflect production implementation)

---

## 1. Project Overview

**Q-Agent CLI** is a strategic gatekeeper for Quantum Machine Learning (QML). It assesses CSV datasets locally to determine "Quantum Suitability" before consuming expensive cloud credits or limited QPU time. It uses a local LLM (Ollama) for the strategic decision and Claude (`claude-sonnet-4-6`) for precise code generation.

---

## 2. System Architecture

The application is a Python CLI tool following a four-stage pipeline:

1. **Statistical Profiler** (`profiler.py`) — Computes mathematical benchmarks locally (scikit-learn). No raw data leaves the machine.
2. **Strategic Gatekeeper** (`decision.py`) — Local LLM (Ollama) evaluates benchmark metadata and issues `[PROCEED]` or `[ABORT]`.
3. **Code Architect** (`generator.py`) — Remote LLM (Claude) generates a complete, standalone Qiskit 2.x Python script.
4. **Quantum Executor** (`executor.py`) — Saves the generated script and optionally submits it to IBM Quantum via Qiskit Runtime.

---

## 3. Technical Specifications

### 3.1 Stack

| Component | Technology | Version |
| :--- | :--- | :--- |
| Language | Python | 3.10+ |
| Data | pandas | ≥ 2.0 |
| Classical ML | scikit-learn | ≥ 1.3 |
| Quantum circuits | qiskit | ≥ 2.0 |
| QPU runtime | qiskit-ibm-runtime | ≥ 0.20 |
| Claude SDK | anthropic | ≥ 0.25 |
| Ollama client | openai (SDK) | ≥ 1.0 |
| Config | python-dotenv | ≥ 1.0 |
| Terminal UI | rich | ≥ 13.0 |

**APIs:** Ollama (local, port 11434), Anthropic (remote), IBM Quantum Platform (remote).

### 3.2 CLI Interface

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--file` | Path | Required | Path to the CSV dataset. |
| `--target` | String | Required | The name of the column to predict (label). |
| `--log-level` | String | `info` | Console verbosity: `info` or `debug`. |
| `--dry-run` | Flag | `False` | Stop before IBM submission; save generated code to local `tmp/`. |
| `--instance` | String | None | IBM Quantum Platform instance name or CRN. Omit for the free/open plan (auto-discovers). The old `hub/group/project` format is not valid. |

---

## 4. Module Implementation

### 4.1 Module 1: Statistical Profiler (`profiler.py`)

Performs the following without sending raw data to any LLM:

- **Preprocessing:** Drop rows with missing values. Apply `StandardScaler` to features and `LabelEncoder` to the target (and any categorical feature columns).
- **Linear Separability Score:** Train `LinearSVC(C=1000, max_iter=5000)`. If training accuracy > 0.90, set `abort` flag — dataset is classically trivial.
- **Complexity Gap:** Train `RandomForestClassifier(n_estimators=100)`. Calculate `gap = RF_acc − LinearSVC_acc`. A high gap (≥ 0.10) indicates non-linear structure that a quantum kernel may exploit.
- **PCA Variance:** Compute how many components explain 95% of variance. If > 16, set `abort` flag — exceeds QPU qubit limits.
- **Row Count:** If rows > 50,000, set `abort` flag — classical methods are more efficient at this scale.

Returns a metadata JSON dict. Abort flags are set deterministically in Python before any LLM is consulted.

### 4.2 Module 2: Strategic Decision Engine (`decision.py`)

Uses the **OpenAI SDK** pointed at Ollama (`http://localhost:11434/v1`).

**Key implementation details learned in production:**

- The prompt pre-evaluates all three hard abort rules in Python and injects the `True`/`False` result as plain text into the prompt. This prevents the LLM from reasoning incorrectly about whether a rule fires.
- An explicit numeric threshold for the complexity gap (`gap ≥ 0.10 → PROCEED`) is stated in the prompt to eliminate subjective LLM interpretation.
- `temperature=0.0` is used for fully deterministic output.
- The output format mandates `[PROCEED]` or `[ABORT]` on line 1 with no preamble.

**Effective prompt structure:**
```
STEP 1 — Apply three hard ABORT rules (pre-evaluated by Python, shown as "fires" / "does not fire")
STEP 2 — If no rule fired: gap ≥ 0.10 → PROCEED, gap < 0.10 → ABORT
OUTPUT FORMAT — [PROCEED] or [ABORT] on line 1, then 3 bullet rationale
```

### 4.3 Module 3: Code Architect (`generator.py`)

Uses the **Anthropic SDK** with prompt caching (`cache_control: ephemeral`) on the system prompt.

**Qiskit 2.x API constraints enforced in the prompt (all verified against the live Qiskit 2.4.x source):**

| Constraint | Correct form |
| :--- | :--- |
| Feature map | `zz_feature_map(feature_dimension=n, reps=1)` — parameter is `feature_dimension`, NOT `num_qubits` |
| Ansatz | `real_amplitudes(num_qubits=n, reps=1)` — parameter IS `num_qubits` |
| Sampler | `SamplerV2(mode=backend)` — parameter is `mode`, NOT `backend` |
| Auth channel | `channel='ibm_quantum_platform'` — NOT the retired `'ibm_quantum'` |
| Auth token env var | `QISKIT_IBM_TOKEN` |
| Instance env var | `QISKIT_IBM_INSTANCE` — `or None` guard prevents empty-string errors |
| Circuit composition | Compose feature map + ansatz into **one** `QuantumCircuit` BEFORE transpiling |
| Transpilation | Call `transpile(qc, backend, optimization_level=1)` exactly **once** on the combined circuit |

**Why single-pass transpilation matters:** `transpile()` maps logical qubits to physical backend qubits. Two circuits transpiled independently receive different physical qubit mappings and cannot be composed — doing so raises `CircuitError: "Trying to compose with another QuantumCircuit which has more 'in' edges."` The correct order is: build → compose → transpile once → run.

### 4.4 Module 4: Quantum Executor (`executor.py`)

- Saves generated scripts to `outputs/{timestamp}_circuit.py` (live runs) or `tmp/{timestamp}_circuit.py` (dry-runs).
- `tmp/` is project-local (not `/tmp`) so scripts survive reboots.
- Executes the generated script via `subprocess.run` with a 600-second timeout.
- Injects `QISKIT_IBM_TOKEN` and `QISKIT_IBM_INSTANCE` into the subprocess environment from the parent process's `IBM_QUANTUM_TOKEN` and `--instance` flag.
- Parses Job ID and queue status from subprocess stdout via regex.

---

## 5. Execution & Guardrails

### 5.1 The "Circuit Breaker" (two layers)

**Layer 1 — Hard limits (profiler.py):** Deterministic Python checks. Run before any network call. Fast and free.

**Layer 2 — LLM reasoning (decision.py):** Ollama evaluates the complexity gap with a structured, rules-based prompt. Can `[ABORT]` on negligible gap even when hard limits pass.

The circuit breaker parses the **first word** of the Ollama response. If `[ABORT]`, the pipeline terminates before calling the Anthropic API.

### 5.2 File & Session Management

- Live run scripts: `outputs/{timestamp}_circuit.py`
- Dry-run scripts: `tmp/{timestamp}_circuit.py` (gitignored; project-local)
- Circuit diagram: `outputs/circuit_diagram.txt` (written by the generated script)
- IBM Job ID and Queue Status logged to console on submission

### 5.3 Logging Protocol

| Level | Output |
| :--- | :--- |
| `INFO` (default) | Progress spinner with stage name and high-level status |
| `DEBUG` | Raw profiler JSON, full Ollama response, full generated Python code |

---

## 6. Environment Variables (`.env`)

```bash
ANTHROPIC_API_KEY=your_key_here       # Required for Stage 3 (Claude code generation)
IBM_QUANTUM_TOKEN=your_token_here     # Required for Stage 4 (live QPU submission)
OLLAMA_BASE_URL=http://localhost:11434/v1  # Default; override if Ollama runs elsewhere
OLLAMA_MODEL=llama3                   # Optional; default is 'llama3'
```

The executor automatically maps `IBM_QUANTUM_TOKEN` → `QISKIT_IBM_TOKEN` in the subprocess environment, matching the Qiskit 2.x convention.

---

## 7. Test Datasets

| Dataset | File | Target col | Trigger | LinearSVC acc | Gap |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Particle beam | `data/test_dataset_abort.csv` | `particle_type` | ABORT (Stage 1) | 1.000 | 0.000 |
| Quantum materials | `data/test_dataset_run.csv` | `phase` | PROCEED → IBM QPU | 0.530 | 0.470 |

The PROCEED dataset is deliberately sized for fast QPU execution: 4 features (4-qubit circuit), 200 samples, `reps=1`.

---

## 8. Deviations from Original Specification

| Spec item | Original | As-built | Reason |
| :--- | :--- | :--- | :--- |
| Qiskit version | 1.x | **2.x (≥ 2.0)** | Qiskit 2.0 released; 1.x APIs deprecated |
| Circuit classes | `ZZFeatureMap`, `RealAmplitudes` (classes) | `zz_feature_map`, `real_amplitudes` (functions) | Class forms deprecated Qiskit 2.1 |
| IBM channel | `ibm_quantum` | **`ibm_quantum_platform`** | Legacy channel retired |
| Auth env var | `IBM_TOKEN` | **`QISKIT_IBM_TOKEN`** | Qiskit 2.x standard |
| `--instance` format | `hub/group/project` | **Instance name or CRN** | Old format invalid on new platform |
| Dry-run save path | `/tmp` | **`tmp/`** (project-local) | Survives reboots |
| Ollama prompt style | Open-ended question | **Structured rules with pre-computed verdicts** | Open-ended caused spurious ABORTs |
| Circuit reps | 2 | **1** | Reduces circuit depth for faster QPU execution |
| Dataset size (PROCEED) | (not specified) | **200 rows, 4 features** | Minimises QPU circuit executions |
