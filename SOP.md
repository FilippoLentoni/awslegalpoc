# Agent Builder SOP: Langfuse Onboarding & Continuous Improvement

# New Dev

4) prompt can be control from beta [ok] and prompt
5) upload of the documents and control [ok]

10) llm as a judge offline [ok] and online [missing]
1) ci/cd automatic testing [ok]
3) nova to claude [3]
2) rag with real data [4] 
6) metrics calculation and feedback loop [missing]

8) from streamlit ot react
9) thumbs up/down




## Table of Contents

1. [Onboarding a New Agent](#1-onboarding-a-new-agent)
2. [Day-to-Day Operations](#2-day-to-day-operations)
3. [UAT & Data Collection](#3-uat--data-collection)
4. [Accuracy Measurement & Weekly Review](#4-accuracy-measurement--weekly-review)
5. [Prompt Experimentation & Improvement](#5-prompt-experimentation--improvement)
6. [Testing New Tools & Models](#6-testing-new-tools--models)
7. [CI/CD Integration](#7-cicd-integration)
8. [Reference: Score Tab & Accuracy](#8-reference-score-tab--accuracy)
9. [FAQ](#9-faq)

---

## 1. Onboarding a New Agent

### 1.1 Platform Admin: Create Langfuse Project

Before the agent builder starts, the platform admin must:

1. **Create a Langfuse project** for the agent (Langfuse > Settings > Projects > New Project)
   - Naming convention: `<team>-<agent-name>` (e.g., `legal-customer-support`)
2. **Generate API keys** (Project Settings > API Keys)
3. **Share with the agent owner:**
   - `LANGFUSE_PUBLIC_KEY`
   - `LANGFUSE_SECRET_KEY`
   - `LANGFUSE_HOST` (e.g., `https://us.cloud.langfuse.com`)
4. **Create an LLM Connection** for the project (see Section 1.6)

### 1.2 Agent Builder: Environment Setup

Copy `.env.example` and fill in the keys provided by the platform admin:

```bash
cp .env.example .env
```

Required Langfuse variables:

```env
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxx
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

### 1.3 Agent Architecture: The 3 Components

Every agent integrated with Langfuse must have three components that can be independently versioned and tested:

```
+---------------------------------------------------+
|                    AGENT                           |
|                                                    |
|  1. SYSTEM PROMPT  (managed in Langfuse UI)        |
|     - Fetched at runtime via get_system_prompt()   |
|     - Versioned, labeled (production/staging)      |
|     - Editable without redeployment                |
|                                                    |
|  2. MODEL  (configured in .env)                    |
|     - BEDROCK_MODEL_ID or INFERENCE_PROFILE_ARN    |
|     - Swappable via LLM Connections in Langfuse    |
|       for experiments                              |
|                                                    |
|  3. TOOLS  (defined in code)                       |
|     - core/tools.py: get_product_info,             |
|       get_return_policy, web_search, etc.          |
|     - Changes require code update + redeployment   |
|     - Test via staging agent (see Section 6.2)     |
|                                                    |
+---------------------------------------------------+
         |                           |
         v                           v
   [OTEL Traces to Langfuse]   [User Feedback]
   (automatic via Strands)     (thumbs up/down)
```

**Code integration pattern:**

```python
# core/langfuse_client.py -- already provided
from core.langfuse_client import get_system_prompt

# In your agent construction:
agent = Agent(
    model=model,
    tools=[your_tool_1, your_tool_2, ...],
    system_prompt=get_system_prompt(),  # fetches from Langfuse
)
```

### 1.4 Enable Tracing (OTEL)

Tracing is automatic. The agent runtime uses Strands OTEL telemetry which exports traces to Langfuse.

| Component | How tracing is configured |
|-----------|--------------------------|
| **AgentCore Runtime** | `scripts/agentcore_deploy.py` sets `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, and `DISABLE_ADOT_OBSERVABILITY=true` as env vars. `runtime_app.py` calls `StrandsTelemetry().setup_otlp_exporter()`. |
| **Local Agent** | `core/observability.py` > `configure_langfuse_otel()` sets the same OTEL env vars at runtime. Called in `core/agent.py`. |

No code changes needed -- just set the Langfuse env vars and deploy.

### 1.5 Enable Prompt Management

**Step 1: Seed your system prompt into Langfuse**

```bash
set -a && source .env && set +a && python3.11 scripts/seed_langfuse_prompt.py
```

This creates a prompt named `customer-support-agent` in Langfuse with the `production` label.

**Step 2: Verify it works**

The agent code (`core/langfuse_client.py` > `get_system_prompt()`) automatically fetches the prompt from Langfuse at runtime with a fallback to the hardcoded prompt in `core/tools.py`.

**Step 3: Edit in the Langfuse UI**

Go to Langfuse > Prompt Management > `customer-support-agent`. Edit the text, save as a new version, and assign the `production` label. The next agent invocation uses the updated prompt -- no redeployment needed.

### 1.6 Configure LLM Connection in Langfuse

Go to Langfuse > Settings > LLM Connections > New:

| Field | Value |
|-------|-------|
| LLM adapter | `bedrock` |
| Provider name | `aws-bedrock` |
| AWS Region | `us-east-2` |
| AWS Access Key ID | (IAM user with `bedrock:InvokeModel` permission) |
| AWS Secret Access Key | (corresponding secret key) |
| Custom models | `us.amazon.nova-2-lite-v1:0` |

To create the IAM credentials:

```bash
aws iam create-user --user-name langfuse-bedrock-integration
aws iam put-user-policy --user-name langfuse-bedrock-integration \
  --policy-name BedrockInvokePolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": ["arn:aws:bedrock:*::foundation-model/*", "arn:aws:bedrock:*:'$(aws sts get-caller-identity --query Account --output text)':inference-profile/*"]
    }]
  }'
aws iam create-access-key --user-name langfuse-bedrock-integration
```

### 1.7 Configure Evaluators

Set up both evaluators during onboarding so they're ready for day-to-day operations:

**Evaluator 1: Online Quality Check (input + output only)**

See Section 2.1 for full configuration. This runs on every production trace.

**Evaluator 2: Experiment Accuracy (input + output + expected output)**

See Section 5.4 for full configuration. This runs during experiments.

### 1.8 Onboarding Checklist

- [ ] Langfuse project created and API keys shared
- [ ] `.env` configured with Langfuse keys
- [ ] Agent code uses `get_system_prompt()` for system prompt
- [ ] Agent code uses Strands OTEL telemetry for tracing
- [ ] User feedback (thumbs up/down) wired to `create_score()` on traces
- [ ] AgentCore runtime deployed (`python3.11 scripts/agentcore_deploy.py`)
- [ ] ECS app deployed (`docker build` + `docker push` + `ecs update-service`)
- [ ] System prompt seeded in Langfuse (`python3.11 scripts/seed_langfuse_prompt.py`)
- [ ] Evaluation dataset seeded (`python3.11 scripts/seed_langfuse_dataset.py`)
- [ ] LLM Connection configured in Langfuse
- [ ] Online evaluator configured (Section 2.1)
- [ ] Experiment evaluator configured (Section 5.4)
- [ ] Annotation queue created (Section 4.2)
- [ ] Score Configs created (Section 4.2)

---

## 2. Day-to-Day Operations

### 2.1 Configure Online LLM-as-a-Judge (Input + Output Only)

This evaluator runs automatically on every production trace to flag low-quality responses. It only uses the customer input and agent output (no expected output) because this is real-time monitoring.

**Go to:** Langfuse > Evaluators > New Evaluator

| Setting | Value |
|---------|-------|
| Type | LLM-as-a-Judge |
| Name | `online-quality-check` |
| Target | Live Traces |
| Sampling | 100% (or lower to control cost) |
| LLM Connection | `aws-bedrock` / `us.amazon.nova-2-lite-v1:0` |
| Score type | Numeric (0.0 - 1.0) |
| Score name | `quality` |

**Evaluation prompt:**

```
You are an expert evaluator for a customer support AI assistant.

Evaluate the following interaction on a scale of 0.0 to 1.0:
- 1.0 = Excellent: accurate, helpful, professional, uses tools appropriately
- 0.7 = Good: mostly correct, minor issues
- 0.4 = Fair: partially helpful but missing key information or wrong tool usage
- 0.0 = Poor: incorrect, unhelpful, or inappropriate

Customer question: {{input}}
Assistant response: {{output}}

Return ONLY a JSON object: {"score": <float>, "reasoning": "<brief explanation>"}
```

**Variable mapping:**

| Variable | Maps to |
|----------|---------|
| `{{input}}` | `trace.input` |
| `{{output}}` | `trace.output` |

### 2.2 Daily Review Workflow

```
Production Traces
       |
       v
  [Online LLM-as-a-Judge]  --scores every trace-->  Scores Tab
       |
       v
  [User Feedback]  --thumbs up/down-->  Scores Tab
       |
       v
  Filter: quality < 0.5 OR thumbs_feedback = 0
       |
       v
  Review in Traces tab
       |
       +-- False positive? --> Ignore
       |
       +-- Real issue? --> Add to Weekly Annotation Queue
                               |
                               v
                          [Human Review]  (Section 4)
```

**Step-by-step:**

1. **Go to** Langfuse > Traces
2. **Filter** by score: `quality < 0.5` or `thumbs_feedback = 0`
3. **Review** each flagged trace -- read the input/output, check if the issue is real
4. **If real issue:** add to the annotation queue for weekly review

---

## 3. UAT & Data Collection

### 3.1 Running UAT

Before launching an agent to production, run User Acceptance Testing:

1. **Share the agent URL** with test users (internal stakeholders, SMEs)
2. **Ask them to test** common scenarios and edge cases
3. **Ask them to use the thumbs up/down buttons** for every interaction
4. **Collect for at least 50-100 interactions** to build a meaningful dataset

### 3.2 Monitoring UAT in Langfuse

During UAT, monitor:

1. **Traces tab:** watch interactions in real-time
2. **Scores tab:** filter by `thumbs_feedback` to see user satisfaction rate
3. **Online evaluator:** the LLM-as-a-Judge `quality` score runs automatically

### 3.3 Building the Initial Dataset from UAT

After UAT, build your evaluation dataset from real user interactions:

1. Go to Langfuse > Traces
2. Select traces that represent important test cases:
   - Common questions (happy path)
   - Edge cases
   - Failure cases (thumbs down or low quality score)
3. For each trace, click "Add to Dataset" > select your dataset
4. **Set the expected output** to what the correct answer should be (this is the ground truth)

**Dataset naming convention:**

| Dataset | Purpose |
|---------|---------|
| `<agent>-eval-global` | All-time curated test cases. Used for regression testing. |
| `<agent>-eval-2026-02` | Monthly snapshot. Used for monthly accuracy reporting. |

---

## 4. Accuracy Measurement & Weekly Review

### 4.1 The Weekly Review Cycle

```
Monday: Review flagged traces from the past week
          |
          v
    [Annotation Queue]
    Review traces with:
    - quality < 0.5
    - thumbs_feedback = 0
    - random sample of other traces
          |
          v
    [Human Annotator]
    For each trace, score:
    - correctness (0/1)
    - helpfulness (helpful/unhelpful/partial)
    - tool-usage (correct/incorrect/missing)
          |
          v
    [Add to Dataset]
    - Write the correct expected_output (ground truth)
    - Add to monthly dataset: <agent>-eval-2026-02
    - Add to global dataset: <agent>-eval-global
          |
          v
    [Compute Accuracy]  (Section 4.3)
```

### 4.2 Annotation Queue Setup

**Create Score Configs first** (Settings > Score Configs):

| Config Name | Type | Values |
|-------------|------|--------|
| `correctness` | Boolean | 0 (incorrect) / 1 (correct) |
| `helpfulness` | Categorical | helpful, unhelpful, partial |
| `tool-usage` | Categorical | correct, incorrect, missing |

**Create Annotation Queue** (Langfuse > Annotation Queues > New Queue):

| Setting | Value |
|---------|-------|
| Name | `weekly-review` |
| Score Configs | `correctness`, `helpfulness`, `tool-usage` |
| Filter | Traces from the past 7 days |

### 4.3 Computing Monthly Accuracy

**Agent accuracy** = how often the agent gives correct answers.

**LLM-as-a-Judge accuracy** = how often the judge agrees with human annotations.

**Step 1: Export scores from Langfuse**

Go to Langfuse > Scores tab:
- Filter by time range (e.g., February 2026)
- Filter by score name
- Export as CSV

**Step 2: Compute agent accuracy**

```
Agent Accuracy = (# of correctness=1 annotations) / (total annotations)
```

From the exported CSV, count:
- Total traces reviewed by humans (have a `correctness` score)
- Traces scored as `correctness = 1`
- Accuracy = correct / total

**Step 3: Compute LLM-as-a-Judge accuracy (judge calibration)**

Compare the judge's `quality` score against human `correctness` annotations on the same traces:

```
For each trace that has BOTH a quality score AND a correctness annotation:
  - Judge says "good" = quality >= 0.5
  - Human says "correct" = correctness = 1
  - Agreement = (judge good AND human correct) OR (judge bad AND human incorrect)

Judge Accuracy = (# agreements) / (total traces with both scores)
```

**Step 4: Track monthly**

| Month | Agent Accuracy | Judge Accuracy | Traces Reviewed | Dataset Size |
|-------|---------------|----------------|-----------------|--------------|
| Feb 2026 | 85% | 90% | 50 | 60 |
| Mar 2026 | ... | ... | ... | ... |

### 4.4 When to Take Action

| Metric | Threshold | Action |
|--------|-----------|--------|
| Agent accuracy < 80% | Urgent | Run prompt experiments (Section 5) |
| Agent accuracy < 90% | Improvement needed | Review failure patterns, update prompt |
| Judge accuracy < 85% | Recalibrate | Update judge prompt, review disagreements |
| Thumbs down rate > 20% | Investigate | Deep dive into negative feedback traces |

---

## 5. Prompt Experimentation & Improvement

### 5.1 When to Run an Experiment

- Agent accuracy drops below target
- After adding new tools to the agent
- When switching models (e.g., Nova Lite to Nova Pro)
- After significant dataset growth (new edge cases from weekly reviews)
- Before any production deployment

### 5.2 Create a New Prompt Version

1. Go to Langfuse > Prompt Management > `customer-support-agent`
2. Click "New Version"
3. Edit the prompt (e.g., add constraints, change tone, update tool descriptions)
4. Add `{{input}}` placeholder at the end for experiments:
   ```
   Current customer question: {{input}}
   ```
5. Save -- do NOT label as `production` yet
6. Optionally label as `staging` for testing

### 5.3 Run an Experiment (UI)

1. Go to Prompt Management > `customer-support-agent` > select the new version
2. Click "Run Experiment"
3. Select dataset: `<agent>-eval-global` (or a monthly dataset)
4. Select LLM Connection: `aws-bedrock`
5. The experiment evaluator scores each result automatically
6. Run

### 5.4 Configure Experiment Evaluator (Input + Output + Expected Output)

This evaluator is more thorough than the online one because it has access to the ground truth expected output.

**Go to:** Langfuse > Evaluators > New Evaluator

| Setting | Value |
|---------|-------|
| Type | LLM-as-a-Judge |
| Name | `experiment-accuracy` |
| Target | Experiments |
| LLM Connection | `aws-bedrock` / `us.amazon.nova-2-lite-v1:0` |
| Score type | Numeric (0.0 - 1.0) |
| Score name | `accuracy` |

**Evaluation prompt:**

```
You are an expert evaluator for a customer support AI assistant.

Compare the assistant's actual output against the expected output.
Score on a scale of 0.0 to 1.0:
- 1.0 = Output fully aligns with expected output (covers same points, correct info, appropriate tool usage)
- 0.7 = Mostly aligned, minor differences that don't affect quality
- 0.4 = Partially aligned, missing key information or some inaccuracies
- 0.0 = Not aligned, incorrect information, or completely off-topic

Customer Input: {{input}}
Expected Output: {{expected_output}}
Actual Output: {{output}}

Return ONLY a JSON object: {"score": <float>, "reasoning": "<brief explanation>"}
```

**Variable mapping:**

| Variable | Maps to |
|----------|---------|
| `{{input}}` | `dataset_item.input` |
| `{{output}}` | `run.output` |
| `{{expected_output}}` | `dataset_item.expected_output` |

### 5.5 Compare Experiments

After running experiments with different prompt versions:

1. Go to Langfuse > Datasets > select dataset > Experiments tab
2. View side-by-side results: each run shows per-item scores
3. Compare aggregate `accuracy` scores across runs
4. The run with the highest average accuracy is the best candidate

### 5.6 Validation Before Promotion

Before promoting a new prompt version to production:

1. **LLM-as-a-Judge validation:** experiment accuracy must exceed the current production version
2. **Manual validation:** review a sample of experiment outputs (especially items where the judge gave low scores)
3. **Regression check:** ensure no previously passing items now fail

### 5.7 Promote to Production

If the new prompt version passes validation:

1. Go to Prompt Management > `customer-support-agent`
2. Select the winning version
3. Assign the `production` label (automatically removes it from the previous version)
4. The live agent picks up the new prompt on the next request -- no redeployment needed

---

## 6. Testing New Tools & Models

### 6.1 Testing Different Models

To compare models (e.g., Nova Lite vs Nova Pro vs Claude):

1. In Langfuse LLM Connections, add all models you want to test
2. Run separate experiments from the Prompt Management tab, selecting a different model each time
3. Each run creates a separate experiment with its own scores
4. Compare in the Experiments view

**Naming convention for experiment runs:**

```
<prompt-version>-<model>-<date>
```

Example: `v3-nova-lite-2026-02-09`, `v3-nova-pro-2026-02-09`

### 6.2 Testing Different Tools

Tools are defined in code, so testing new tools requires a different approach than prompts/models. You have two options:

**Option A: Staging Agent (Recommended for production safety)**

Deploy a separate staging agent that doesn't affect production:

1. Create a second AgentCore runtime with a different name:
   ```bash
   AGENTCORE_AGENT_NAME=awslegalpoc_staging python3.11 scripts/agentcore_deploy.py
   ```
2. The staging agent gets its own runtime ARN and endpoint
3. Test the new tools on staging
4. Run experiments against the staging agent using the SDK runner (see below)
5. Once validated, deploy the tool changes to the production agent

**Option B: SDK-Based Experiment (Local testing, no deployment needed)**

Run the agent locally with different tool configurations:

```python
# scripts/run_tool_experiment.py
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from langfuse import Evaluation
from core.langfuse_client import get_langfuse_client

langfuse = get_langfuse_client()

def my_agent_task(*, item, **kwargs):
    """Run the agent with a specific tool configuration."""
    from core.agent import run_agent
    return run_agent(item["input"])

def accuracy_evaluator(*, input, output, expected_output, **kwargs):
    """Simple keyword-based accuracy check."""
    if expected_output and any(
        keyword.lower() in output.lower()
        for keyword in expected_output.split()
        if len(keyword) > 4
    ):
        return Evaluation(name="accuracy", value=1.0, comment="Key terms found")
    return Evaluation(name="accuracy", value=0.0, comment="Key terms missing")

dataset = langfuse.get_dataset("customer-support-eval")
result = dataset.run_experiment(
    name="tool-config-v2-2026-02-09",
    task=my_agent_task,
    evaluators=[accuracy_evaluator],
    metadata={"tools": "get_product_info,get_return_policy,web_search,get_technical_support"}
)
print(result.format())
```

Run with:

```bash
set -a && source .env && set +a && python3.11 scripts/run_tool_experiment.py
```

Modify the tool list in the agent construction to test different combinations.

### 6.3 What Changes Require Redeployment?

| Change | Redeployment Required? | How to Test Safely |
|--------|----------------------|-------------------|
| System prompt | No | Edit in Langfuse UI, run experiment |
| Model | No (for experiments) | Select different model in Langfuse experiment |
| Model (production) | Yes | Update `.env` + redeploy |
| Tools | Yes | Deploy staging agent OR run locally via SDK |
| Tool parameters/configs | Yes | Deploy staging agent OR run locally via SDK |

---

## 7. CI/CD Integration

### 7.1 Automated Evaluation in Pipeline

Add an evaluation step to your CI/CD pipeline that runs experiments on every PR or deployment:

```yaml
# Example: GitHub Actions step
- name: Run Langfuse Evaluation
  env:
    LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
    LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
    LANGFUSE_HOST: https://us.cloud.langfuse.com
  run: |
    python3.11 scripts/run_ci_evaluation.py --min-accuracy 0.7
```

### 7.2 Pipeline Decision Flow

```
Code Change / New Prompt Version
          |
          v
    [CI Pipeline Trigger]
          |
          v
    [Run Evaluation Against Global Dataset]
    scripts/run_ci_evaluation.py --min-accuracy 0.7
          |
          +-- avg_accuracy >= 0.7 --> PASS --> Deploy
          |
          +-- avg_accuracy < 0.7  --> FAIL --> Block & Review
```

### 7.3 CI Evaluation Script: `scripts/run_eval.py`

The evaluation script is already implemented and wired into `deploy-all.sh` Step 7 (beta only).

**How it works:**

```
deploy-all.sh Step 7 (beta only)
  └─ scripts/run_eval.py
       ├─ Authenticate via Cognito
       ├─ Fetch Langfuse dataset "customer-support-eval"
       ├─ For each item:
       │    ├─ Invoke AgentCore runtime (HTTPS + JWT)
       │    ├─ Call Bedrock LLM judge (Correctness prompt)
       │    └─ Record score to Langfuse trace
       ├─ Print summary (pass/fail per item)
       └─ Exit 0 (pass) or 1 (fail)
```

**Run manually:**

```bash
set -a && source .env && set +a
python3.11 scripts/run_eval.py --dataset customer-support-eval --min-score 0.7
```

**CLI arguments:**

| Arg | Default | Description |
|-----|---------|-------------|
| `--dataset` | `customer-support-eval` | Langfuse dataset name |
| `--min-score` | `0.7` | Pass threshold (0.0-1.0) |
| `--timeout` | `120` | Seconds per agent invocation |
| `--run-name` | auto (timestamp) | Langfuse run name |

**Pass/fail logic:** Exit 0 if average score >= threshold AND no item below 0.3.

### 7.4 Online Hallucination Evaluator (Production)

The Hallucination evaluator runs automatically on prod traces via Langfuse auto-eval. No code needed — configured entirely in the Langfuse UI.

**Go to:** Langfuse > Evaluators > New Evaluator

| Setting | Value |
|---------|-------|
| Type | LLM-as-a-Judge |
| Name | `hallucination` |
| Target | Live Traces (filter by `APP_VERSION=prod`) |
| Sampling | 100% (adjust for cost) |
| LLM Connection | `aws-bedrock` / `us.amazon.nova-2-lite-v1:0` |
| Score type | Numeric (0.0 - 1.0, where 1.0 = hallucination detected) |
| Score name | `hallucination` |

**Evaluation prompt:**

```
Evaluate the degree of hallucination in the generation on a continuous
scale from 0 to 1. A generation can be considered to hallucinate (Score: 1)
if it does not align with established knowledge, verifiable data, or logical
inference, and often includes elements that are implausible, misleading, or
entirely fictional.

Query: {{query}}
Generation: {{generation}}

Think step by step.
```

**Variable mapping:**

| Variable | Maps to |
|----------|---------|
| `{{query}}` | `trace.input` |
| `{{generation}}` | `trace.output` |

**Monitoring:**

- Filter Langfuse Scores tab by `hallucination > 0.5` to find problematic responses
- Track average hallucination score over time in dashboards
- Set up Langfuse alerts/webhooks for score degradation

### 7.5 Evaluation Architecture Summary

| Mode | Evaluator | Trigger | Ground Truth | Score Name |
|------|-----------|---------|--------------|------------|
| **Offline (CI/CD)** | Correctness | `deploy-all.sh` Step 7 on beta | Yes (Langfuse dataset) | `correctness` |
| **Online (Live)** | Hallucination | Langfuse auto-eval on prod traces | No | `hallucination` |
| **Online (Live)** | Quality | Langfuse auto-eval (Section 2.1) | No | `quality` |
| **Manual** | Human annotation | Weekly review (Section 4) | Yes (human) | `correctness`, `helpfulness` |

---

## 8. Reference: Score Tab & Accuracy

### 8.1 Score Types in Use

| Score Name | Source | Type | Purpose |
|------------|--------|------|---------|
| `quality` | Online LLM-as-a-Judge | Numeric 0-1 | Real-time quality monitoring |
| `thumbs_feedback` | User (Streamlit UI) | Numeric 0/1 | End-user satisfaction |
| `accuracy` | Experiment evaluator | Numeric 0-1 | Prompt version comparison |
| `correctness` | Human annotation | Boolean 0/1 | Ground truth labeling |
| `helpfulness` | Human annotation | Categorical | Qualitative assessment |
| `tool-usage` | Human annotation | Categorical | Tool selection correctness |

### 8.2 Monthly Accuracy Report (from Score Tab)

**Export process:**

1. Go to Langfuse > Scores tab
2. Set date range (e.g., Feb 1-28, 2026)
3. Export all scores as CSV
4. Compute in spreadsheet or script:

| Metric | Formula |
|--------|---------|
| **Agent accuracy** | `correctness=1 count / total correctness annotations` |
| **Judge accuracy** | `% of traces where (quality>=0.5) agrees with (correctness=1)` |
| **User satisfaction** | `thumbs_feedback=1 count / total thumbs_feedback scores` |
| **Experiment accuracy** | `mean(accuracy scores) per experiment run` |

### 8.3 Dashboard Filters

| View | Filter |
|------|--------|
| Low-quality traces | `quality < 0.5` |
| User complaints | `thumbs_feedback = 0` |
| By prompt version | Group by `prompt.version` in traces |
| By model | Group by `model` in trace metadata |
| Recent regressions | Time range: last 24h, `quality < 0.5` |
| Monthly review | Time range: current month, score name: `correctness` |

---

## 9. FAQ

### FAQ 1: How do I calibrate the LLM-as-a-Judge?

The judge is only as good as its prompt and the model powering it. Calibration is an ongoing process:

**Initial calibration:**

1. Take 20-30 traces and have a human annotate them with `correctness` scores
2. Run the same traces through the LLM-as-a-Judge
3. Compare: does the judge agree with the human?
4. If agreement < 85%, adjust the judge's evaluation prompt:
   - Make scoring criteria more specific
   - Add examples of correct vs incorrect responses
   - Adjust the score thresholds

**Ongoing calibration (weekly):**

1. During the weekly annotation review, humans score traces that the judge already scored
2. Track judge vs human agreement rate monthly (see Section 4.3)
3. If judge accuracy drops:
   - Review the disagreements -- is the judge too strict? too lenient?
   - Update the judge prompt with new examples of edge cases
   - Consider using a more capable model for the judge (e.g., Nova Pro instead of Nova Lite)

**Tips:**

- The judge should use a model at least as capable as the agent's model
- Include domain-specific criteria in the judge prompt (e.g., "must mention return window in days")
- Use few-shot examples in the judge prompt for tricky cases
- Track per-category accuracy (the judge might be good at evaluating greetings but bad at technical support)

### FAQ 2: Can we automate parts of the workflow?

Yes. Here's what can be automated today and what requires human involvement:

| Step | Automated | Human Required |
|------|-----------|----------------|
| Trace collection | Yes (OTEL) | No |
| Online quality scoring | Yes (LLM-as-a-Judge) | No |
| User feedback collection | Yes (thumbs up/down UI) | No |
| Flagging low-quality traces | Yes (score filters) | No |
| Annotation & ground truth | No | Yes (weekly review) |
| Dataset curation | Partially (add from UI) | Yes (write expected output) |
| Running experiments | Yes (UI or SDK) | No |
| Experiment scoring | Yes (LLM-as-a-Judge) | No |
| Promoting prompt versions | No | Yes (human decision) |
| CI/CD evaluation gate | Yes (script) | No |

**Automation opportunities:**

1. **Scheduled experiments:** Use a cron job to run `run_ci_evaluation.py` nightly against the global dataset
2. **Alerting:** Set up alerts when `quality` score average drops below threshold (via Langfuse webhooks or score monitoring)
3. **Auto-dataset:** Script that automatically adds traces with `thumbs_feedback = 0` to the monthly dataset (still requires human to write expected output)

### FAQ 3: How does the feedback loop work?

The feedback loop is the core of continuous improvement:

```
                    +---> [Production Agent] ---+
                    |          |                 |
                    |          v                 |
                    |    [User Interactions]     |
                    |          |                 |
                    |          v                 |
                    |    [Traces + Scores]       |
                    |       |        |           |
                    |       v        v           |
                    |  [LLM Judge] [User FB]     |
                    |       |        |           |
                    |       v        v           |
                    |    [Weekly Review]         |
                    |          |                 |
                    |          v                 |
                    |    [Annotation Queue]      |
                    |          |                 |
                    |          v                 |
                    |    [Dataset Growth]        |
                    |          |                 |
                    |          v                 |
                    |    [Experiment with        |
                    |     new prompt/model]      |
                    |          |                 |
                    |          v                 |
                    |    [Validation]            |
                    |     |         |            |
                    |     v         v            |
                    |   PASS      FAIL           |
                    |     |         |            |
                    |     v         +---> Iterate
                    |  [Promote]
                    |     |
                    +-----+
```

**Key principle:** Every production failure becomes a test case. The dataset grows over time, making experiments more comprehensive and making it harder for regressions to slip through.

### FAQ 4: What happens with multiple agents?

Several multi-agent patterns are possible. Here's how Langfuse handles each:

**Pattern A: Multiple independent agents (separate AgentCore runtimes)**

Each agent gets its own Langfuse project (or uses tags/names to separate within one project):

```
Agent A (Customer Support) --> Langfuse Project A
Agent B (Sales Assistant)  --> Langfuse Project B
```

- Each has its own prompt in Prompt Management
- Each has its own evaluation dataset
- Each has its own annotation queue
- LLM-as-a-Judge evaluators are configured per-project

**Pattern B: Nested Strands agents (agent calling sub-agents)**

Strands OTEL telemetry creates nested spans automatically:

```
Parent Agent Trace
  |-- Sub-Agent A Span (tool call)
  |     |-- LLM call
  |     |-- Tool call
  |-- Sub-Agent B Span (tool call)
        |-- LLM call
```

- All spans appear under one trace in Langfuse
- You can score at the trace level (overall quality) or observation level (sub-agent quality)
- The online evaluator sees the full trace input/output
- For per-sub-agent evaluation, use observation-level scoring in your code:
  ```python
  langfuse.create_score(
      trace_id=trace_id,
      observation_id=sub_agent_span_id,  # score specific sub-agent
      name="sub_agent_quality",
      value=0.9,
  )
  ```

**Pattern C: AgentCore Gateway with multiple tool targets**

The gateway routes to different Lambda/MCP targets. From Langfuse's perspective:

```
Agent Trace
  |-- Gateway MCP call (tool: check_warranty)
  |-- Gateway MCP call (tool: web_search)
  |-- Direct tool call (get_product_info)
```

- Each tool invocation appears as a span within the trace
- You can evaluate tool-level accuracy by scoring individual observations
- The `tool-usage` annotation (correct/incorrect/missing) helps track which tools need improvement

**Pattern D: Agent-as-a-tool (one agent calling another via AgentCore)**

```
Orchestrator Agent
  |-- invoke AgentCore Runtime (Agent B)
  |     |-- Agent B's full trace (separate in Langfuse)
  |-- invoke AgentCore Runtime (Agent C)
        |-- Agent C's full trace (separate in Langfuse)
```

- Each AgentCore runtime creates its own trace
- Use `session_id` to correlate traces across agents
- The orchestrator's trace shows the high-level flow
- Each sub-agent's trace shows the detailed execution
- Evaluate at both levels: orchestrator routing quality AND individual agent quality

**Recommendation for multi-agent setups:**

1. Use one Langfuse project per team/domain
2. Use trace `name` or `tags` to distinguish agents within a project
3. Create separate evaluation datasets per agent
4. Create separate annotation queues with filters by trace name
5. Run experiments independently for each agent's prompt

---

## Quick Reference: File Map

```
scripts/
  seed_langfuse_prompt.py     # One-time: seed system prompt to Langfuse
  seed_langfuse_dataset.py    # One-time: seed eval dataset
  agentcore_deploy.py         # Deploy AgentCore runtime
  run_eval.py                 # CI/CD LLM-as-judge evaluation (beta deployments)

core/
  langfuse_client.py          # get_langfuse_client(), get_system_prompt()
  observability.py            # configure_langfuse_otel()
  tools.py                    # Agent tools + hardcoded fallback prompt
  agent.py                    # Local agent (uses get_system_prompt())

agentcore/
  runtime_app.py              # AgentCore runtime (uses get_system_prompt())
  requirements.txt            # Must include langfuse>=3.7.0
```

## Quick Reference: Langfuse UI Navigation

| Task | Where |
|------|-------|
| Edit system prompt | Prompt Management > `customer-support-agent` |
| View traces | Traces tab |
| Review scores | Scores tab (filter by name/value) |
| Run experiment | Prompt Management > select version > Run Experiment |
| Compare experiments | Datasets > select dataset > Experiments tab |
| Annotation queue | Annotation Queues > `weekly-review` |
| LLM connections | Settings > LLM Connections |
| Score configs | Settings > Score Configs |
| Export scores | Scores tab > Export CSV |

## Quick Reference: The Complete Loop

```
Week 1: Deploy agent, seed prompt & dataset, configure evaluators
Week 2: Run UAT, collect user feedback, build initial dataset
Week 3+: Weekly review cycle begins
         - Monday: Review annotation queue, score traces, add to dataset
         - As needed: Run experiments with new prompts/models
         - Monthly: Compute accuracy report, track trends
```
