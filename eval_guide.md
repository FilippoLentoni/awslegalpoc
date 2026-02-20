# Evaluation Pipeline Guide

This document explains how the LLM-as-judge evaluation pipeline works as part of the deployment process.

## Overview

The pipeline tests the deployed agent against a curated dataset of Italian notarial law questions. For each question, the live agent is invoked, and an LLM judge scores the response against expert-written ground truth. Results are recorded in Langfuse and exported to CSV.

The pipeline has two parts:
1. **Dataset seeding** — one-time setup to load test questions into Langfuse
2. **Eval execution** — runs automatically on every beta deployment (Step 7 in `deploy-all.sh`)

## 1. Dataset Seeding

**Script:** `scripts/seed_langfuse_dataset.py`

### Source Data

The test set is an XLSX file (`test_set.xlsx`) with multiple sheets, each representing a legal domain. Each row contains:

| Column | Description |
|--------|-------------|
| Domanda | The question (input) |
| Risposta | The expected answer written by legal experts (ground truth) |
| Tipologia | Question type/category |
| Riferimenti | Legal references |
| N. | Question number |

### How It Works

1. Loads the XLSX file using `openpyxl`
2. Creates (or updates) a Langfuse dataset via `langfuse.create_dataset()`
3. Archives any existing items to avoid duplicates
4. Inserts each Q&A pair as a dataset item via `langfuse.create_dataset_item()`, with metadata (`domain`, `tipologia`, `riferimenti`)
5. Rate-limits to avoid 429 errors (pauses every 5 items)

### Usage

```bash
# Download test set from S3
aws s3 cp s3://materialpoc/knowledge-base/test_set.xlsx /tmp/test_set.xlsx

# Seed dataset (full)
set -a && source .env && set +a
python3.11 -m poetry run python scripts/seed_langfuse_dataset.py --xlsx /tmp/test_set.xlsx

# Seed with item limit
python3.11 -m poetry run python scripts/seed_langfuse_dataset.py --xlsx /tmp/test_set.xlsx --max-items 10
```

## 2. Eval Execution

**Script:** `scripts/run_eval.py`
**Trigger:** Step 7 in `scripts/deploy-all.sh` (beta deployments only)

### Flow

```
Langfuse Dataset
     |
     v
For each item:
  +-----------------------------------+
  | item.run() opens Langfuse trace   |
  |   -> Invoke deployed agent (HTTPS)|
  |   -> Get agent response           |
  |   -> LLM judge scores response    |
  |     vs ground truth (Bedrock API) |
  |   -> span.score() records result  |
  +-----------------------------------+
     |
     v
Accuracy >= minScore? -> PASS (exit 0) / FAIL (exit 1)
Results -> CSV + Langfuse dashboard
```

### Step-by-Step

#### a) Initialize

- Creates a Langfuse client using `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST`
- Authenticates to the deployed AgentCore runtime via Cognito JWT
- Creates a Bedrock Runtime client for the judge model

#### b) Fetch Dataset

- Calls `langfuse.get_dataset("<dataset-name>")` to pull all active items
- Filters out archived items
- Creates a timestamped run name (e.g., `eval-20260220-143000`)

#### c) Invoke Agent (per item)

- Opens a Langfuse dataset run context via `item.run(run_name=...)` — this links the trace to the dataset item in the Langfuse UI
- Sends the question to the **live deployed agent** over HTTPS (the same endpoint users hit)
- Each invocation uses a unique session ID

#### d) LLM Judge Scoring

The judge (Claude Sonnet via Bedrock `converse` API) receives a structured prompt with three inputs:
- **Customer Input** — the original question
- **Expected Output** — the expert-written ground truth
- **Actual Output** — the agent's response

It evaluates on four criteria:
1. **Legal accuracy** — Are cited articles, doctrinal references, and legal principles correct?
2. **Completeness** — Does the response cover key points from the expected output?
3. **Source citation** — Does it cite relevant normative sources or doctrinal references?
4. **No hallucination** — Does it avoid inventing legal provisions or doctrinal positions?

The judge returns a **binary score**:
- `1` = CORRECT (legally accurate, covers key points, no hallucination)
- `0` = INCORRECT (legally wrong, missing critical info, hallucinated, or off-topic)

The score is recorded on the Langfuse trace via `span.score(name="correctness", value=score)`.

#### e) Pass/Fail Gate

- Computes overall accuracy: `correct / total`
- If accuracy >= `minScore` (default 0.5) → exit 0 (PASS)
- If accuracy < `minScore` → exit 1 (FAIL)
- Also prints per-domain accuracy breakdown
- Exports results to CSV

> **Note:** Currently in `deploy-all.sh`, a failed eval only **warns** but does not block deployment. Change the behavior at line 383 to `exit 1` to gate deployments on eval results.

## 3. Langfuse SDK Methods Used

| Method | Purpose |
|--------|---------|
| `Langfuse()` | Initialize client with API keys and host |
| `langfuse.create_dataset()` | Create or reference a named dataset |
| `langfuse.create_dataset_item()` | Add a Q&A pair to the dataset |
| `langfuse.get_dataset()` | Fetch dataset and its items |
| `item.run(run_name=...)` | Context manager that creates a trace linked to the dataset item |
| `span.update(input=..., output=...)` | Record the agent's input and output on the trace |
| `span.score(name, value, data_type, comment)` | Record the judge's score on the trace |
| `langfuse.flush()` | Ensure all events are sent to Langfuse before exiting |

## 4. Configuration

Eval parameters are defined per-environment in `config/environments.json`:

```json
"eval": {
  "dataset": "italian-legal-eval-quick",
  "judgeModel": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
  "minScore": 0.5,
  "timeout": 180
}
```

| Parameter | Description |
|-----------|-------------|
| `dataset` | Langfuse dataset name to evaluate against |
| `judgeModel` | Bedrock model ID for the LLM judge |
| `minScore` | Minimum accuracy threshold to pass (0.0–1.0) |
| `timeout` | HTTP timeout in seconds for each agent invocation |

Beta uses `italian-legal-eval-quick` (smaller subset) for faster feedback. Prod uses `italian-legal-eval` (full set).

## 5. Running Manually

```bash
# Set environment variables
set -a && source .env && set +a

# Run with defaults
python3.11 -m poetry run python scripts/run_eval.py

# Custom dataset and threshold
python3.11 -m poetry run python scripts/run_eval.py \
  --dataset italian-legal-eval \
  --judge-model us.anthropic.claude-sonnet-4-5-20250929-v1:0 \
  --min-score 0.7 \
  --timeout 180

# Export results to a specific CSV path
python3.11 -m poetry run python scripts/run_eval.py --export results.csv
```

### Required Environment Variables

| Variable | Source |
|----------|--------|
| `LANGFUSE_PUBLIC_KEY` | `config/secrets.json` |
| `LANGFUSE_SECRET_KEY` | `config/secrets.json` |
| `LANGFUSE_HOST` | `config/environments.json` |
| `COGNITO_USERNAME` | `config/environments.json` |
| `COGNITO_PASSWORD` | `config/secrets.json` |
| `COGNITO_CONFIG_SECRET` | Set by `deploy-all.sh` (`<stackPrefix>/cognito-config`) |
| `AWS_REGION` | `config/environments.json` |
| `AGENTCORE_RUNTIME_ARN` | Optional; falls back to SSM parameter |
