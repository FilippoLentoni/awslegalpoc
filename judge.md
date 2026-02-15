# LLM-as-a-Judge Evaluation Pipeline — Action Plan

## Overview

Two evaluation modes using Langfuse LLM evaluators:

| Mode | Evaluator | When | Ground Truth | Implementation |
|------|-----------|------|--------------|----------------|
| **Offline (CI/CD)** | Correctness | Every beta deployment | Yes — from Langfuse dataset | `scripts/run_eval.py` called by `deploy-all.sh` Step 7 |
| **Online (Live)** | Hallucination | Continuously on prod | No | Langfuse UI auto-eval on traces |

---

## Part 1: Offline Correctness Evaluation (CI/CD)

### How It Works

```
deploy-all.sh (Step 7, beta only)
  └─ scripts/run_eval.py
       ├─ 1. Authenticate via Cognito
       ├─ 2. Fetch Langfuse dataset "customer-support-eval"
       ├─ 3. For each dataset item:
       │    ├─ Invoke AgentCore runtime (HTTPS + JWT)
       │    ├─ Get agent response
       │    ├─ Call Bedrock LLM judge (Correctness prompt)
       │    ├─ Parse score (0.0 - 1.0)
       │    └─ Record score to Langfuse trace
       ├─ 4. Print summary table
       └─ 5. Exit 0 (pass) or 1 (fail)
```

### Correctness Judge Prompt

```
Compare the assistant's actual output against the expected output.
Score 0.0-1.0:
- 1.0 = Fully aligned with expected output
- 0.7 = Mostly aligned, minor differences
- 0.4 = Partially aligned, missing key info
- 0.0 = Not aligned, incorrect, or off-topic

Customer Input: {query}
Expected Output: {ground_truth}
Actual Output: {generation}

Return ONLY JSON: {"score": <float>, "reasoning": "<brief explanation>"}
```

### Pass/Fail Criteria
- **Pass**: Average score >= 0.7 AND no individual item below 0.3
- **Fail**: Otherwise → logs warning, deployment continues (configurable to hard-fail)

### Files to Create/Modify

#### `scripts/run_eval.py` (NEW)
- CLI: `python scripts/run_eval.py --dataset customer-support-eval --min-score 0.7`
- Reuses auth pattern from `scripts/test_agentcore_runtime.py`
- Reuses Langfuse client from `core/langfuse_client.py`
- Each dataset item gets a fresh `session_id` (prevents memory contamination)
- Uses `actor_id="eval_runner"` (distinguishes from real users)
- Judge calls Bedrock directly (`invoke_model` with `us.amazon.nova-2-lite-v1:0`)
- Results linked to Langfuse dataset via `item.run()` / `item.link()` API

#### `scripts/seed_langfuse_dataset.py` (MODIFY)
- Update all 10 expected_output strings
- Old: references `get_product_info`, `get_return_policy`, `get_technical_support`
- New: references `search_knowledge_base` tool and KB-based responses
- Example: `"The assistant should search the knowledge base for return policy information..."`

#### `scripts/deploy-all.sh` (MODIFY — Step 7)
- Only runs on `beta` deployments
- Exports Langfuse + Cognito credentials
- Waits 30s for runtime stabilization
- Calls `scripts/run_eval.py`
- Logs pass/fail (soft-fail by default, configurable to hard-fail)

---

## Part 2: Online Hallucination Evaluation (Production)

### How It Works

This is configured entirely in the Langfuse UI — no code changes needed.

```
User query → AgentCore Runtime → Response
                                    │
                                    ▼
                         Langfuse Trace (via OTEL)
                                    │
                                    ▼
                     Langfuse Auto-Evaluator (Hallucination)
                                    │
                                    ▼
                         Score attached to trace
```

### Langfuse UI Configuration

1. **Evaluators → New Evaluator**
   - Name: `hallucination`
   - Type: LLM-as-a-Judge
   - Target: All traces (or filter by `APP_VERSION=prod`)
   - Sampling: 100% (adjust for cost)
   - Model: `us.amazon.nova-2-lite-v1:0` via Bedrock

2. **Variable Mapping**
   - `{{query}}` → `trace.input`
   - `{{generation}}` → `trace.output`

3. **Hallucination Judge Prompt** (already configured by user):
   ```
   Evaluate the degree of hallucination in the generation on a continuous
   scale from 0 to 1. Score 1.0 = hallucination detected, 0.0 = no hallucination.

   Query: {{query}}
   Generation: {{generation}}

   Think step by step.
   ```

### Monitoring
- Langfuse Scores tab → filter `hallucination > 0.5` to find problematic responses
- Set up Langfuse alerts/webhooks for score degradation
- Dashboard: track average hallucination score over time

---

## Implementation Order

| Step | File | Action | Dependency |
|------|------|--------|------------|
| 1 | `scripts/seed_langfuse_dataset.py` | Update 10 test items | None |
| 2 | `scripts/run_eval.py` | Create eval script | Step 1 (dataset) |
| 3 | `scripts/deploy-all.sh` | Wire Step 7 | Step 2 (script) |
| 4 | `SOP.md` | Document Hallucination setup | None |

## Verification

```bash
# 1. Re-seed the updated dataset
set -a && source .env && set +a
python3.11 scripts/seed_langfuse_dataset.py

# 2. Run eval locally against beta
python3.11 scripts/run_eval.py --dataset customer-support-eval --min-score 0.5

# 3. Check results in Langfuse > Datasets > customer-support-eval

# 4. Full deploy test (Step 7 runs automatically)
./scripts/deploy-all.sh --env beta
```
