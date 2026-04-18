My final quality review identified three "blind spots" that would likely cause **Claude Code** to stall or produce buggy code if not addressed:

1.  **The "Target" Column:** A CSV doesn't inherently tell the script which column is the label ($y$) and which are the features ($X$). I’ve added a `--target` argument.
2.  **Data Encoding:** Quantum circuits only accept numerical values. If your CSV has strings (e.g., "Yes/No"), the script will crash. I added a requirement for **StandardScaler** and **LabelEncoder**.
3.  **Qiskit Authentication:** Modern Qiskit 1.x uses the `QiskitRuntimeService` which often requires a specific `hub/group/project` string (instance) to access dedicated QPU time.

Here is your finalized, copy-paste ready Technical Design Document.

---

# Technical Design Document: Q-Agent CLI

## 1. Project Overview
**Q-Agent CLI** is a strategic gatekeeper for Quantum Machine Learning (QML). It assesses CSV datasets locally to determine "Quantum Suitability" before consuming expensive cloud credits or limited QPU time. It uses a local LLM (Ollama) for the strategic decision and Claude 3.5 Sonnet for precise code generation.

## 2. System Architecture
The application is a Python CLI tool following a four-stage pipeline:
1.  **Statistical Profiler:** Computes mathematical benchmarks locally (Scikit-Learn).
2.  **Strategic Gatekeeper:** Local LLM (Ollama) evaluates suitability.
3.  **Code Architect:** Remote LLM (Claude) generates Qiskit 1.x code.
4.  **Quantum Executor:** Submits the job to IBM Quantum via Qiskit Runtime.

---

## 3. Technical Specifications

### 3.1 Stack
* **Python:** 3.10+
* **Libraries:** `pandas`, `scikit-learn`, `qiskit>=1.0`, `qiskit-ibm-runtime`, `anthropic`, `openai` (for Ollama).
* **APIs:** Ollama (Local:11434), Anthropic (Remote), IBM Quantum (Remote).

### 3.2 CLI Interface
| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--file` | Path | Required | Path to the CSV dataset. |
| `--target` | String | Required | The name of the column to predict (Label). |
| `--log-level` | String | `info` | Console verbosity: `info` or `debug`. |
| `--dry-run` | Flag | `False` | Stop before IBM submission; save code to `/tmp`. |
| `--instance` | String | None | IBM Quantum hub/group/project string. |

---

## 4. Module Implementation Requirements

### 4.1 Module 1: Statistical Profiler (`profiler.py`)
This module must perform the following without sending raw data to the LLM:
* **Preprocessing:** Drop rows with missing values. Apply `StandardScaler` to features and `LabelEncoder` to the target.
* **Linear Separability Score:** Train a `LinearSVC(C=1000)`. If accuracy > 0.90, flag for **ABORT**.
* **Complexity Gap:** Train a `RandomForestClassifier`. Calculate `Gap = RF_Score - Linear_Score`. A high gap indicates non-linear potential.
* **PCA Variance:** Calculate how many components explain 95% of variance. If > 16, flag for **ABORT**.

### 4.2 Module 2: Strategic Decision Engine (`decision.py`)
Use the **OpenAI SDK** pointing to Ollama.
**Prompt:**
> "You are a Senior Quantum Architect. Analyze this JSON metadata: {json_metadata}.
> **Decision Rules:**
> - If `linear_svc_acc` > 0.90: ABORT (Classically trivial).
> - If `pca_95_count` > 16: ABORT (Hardware qubit limit).
> - If `rows` > 50,000: ABORT (Classical efficiency).
> **Objective:** Does the 'Classical Gap' justify a Quantum Kernel?
> **Output:** Start with [PROCEED] or [ABORT] then give a 3-bullet rationale."

### 4.3 Module 3: Code Architect (`generator.py`)
Use the **Anthropic SDK** with Prompt Caching.
**Prompt:**
> "Generate a standalone Python script using **Qiskit 1.x**.
> **Constraints:**
> - Use `qiskit_ibm_runtime.SamplerV2`.
> - Use `ZZFeatureMap` (reps=2) and `RealAmplitudes` ansatz.
> - Limit `shots` to 1024.
> - Authentication: Use `QiskitRuntimeService(channel='ibm_quantum', token=os.getenv('IBM_TOKEN'))`."

---

## 5. Execution & Guardrails (Instructions for Claude Code)

### 5.1 The "Circuit Breaker"
* The script **must** parse the first word of the Ollama response. If it is `[ABORT]`, print the rationale to the console and **terminate** before calling the Anthropic API.

### 5.2 File & Session Management
* Save all generated quantum scripts to `outputs/{timestamp}_circuit.py`.
* Log the IBM **Job ID** and **Queue Status** if a submission is made.

### 5.3 Logging Protocol
* **INFO:** Display a progress spinner and high-level status (e.g., "Benchmarking data...").
* **DEBUG:** Print the raw JSON statistics, the full Ollama "Thinking" block, and the generated Python code to the console.

---

## 6. Environment Variables (`.env`)
```bash
ANTHROPIC_API_KEY=your_key_here
IBM_QUANTUM_TOKEN=your_token_here
OLLAMA_BASE_URL=http://localhost:11434/v1
```
