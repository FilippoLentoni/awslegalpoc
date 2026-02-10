# HLD: Agent Observability & Continuous Improvement Platform

## 1. Overview

This document describes the high-level design for an agent observability and continuous improvement platform built on **Langfuse** and **Amazon Bedrock AgentCore**. The platform supports a two-stage lifecycle: **offline experimentation** in a beta environment and **online monitoring** in production, connected by a continuous feedback loop.

```
+-----------------------------------------------------------------------+
|                                                                       |
|   PHASE 1: OFFLINE EXPERIMENTATION (Beta AWS Account)                 |
|                                                                       |
|   Developer builds/iterates on agent (prompt, tools, model)           |
|   CI/CD deploys to beta AgentCore runtime                             |
|   SDK experiment runs against eval dataset                            |
|   LLM-as-a-Judge + human review scores results                       |
|   Gate: accuracy >= threshold --> promote to prod                     |
|                                                                       |
+----------------------------------+------------------------------------+
                                   |
                                   | Promotion
                                   v
+-----------------------------------------------------------------------+
|                                                                       |
|   PHASE 2: ONLINE MONITORING (Prod AWS Account)                       |
|                                                                       |
|   Agent serves real users via prod AgentCore runtime                  |
|   OTEL traces flow to Langfuse [TRACES]                               |
|   Online LLM-as-a-Judge scores every trace [SCORES]                   |
|   User thumbs up/down collected [SCORES]                              |
|   Weekly oncall reviews annotation queue [ANNOTATION QUEUE]           |
|   Annotated traces added to eval dataset [DATASETS]                   |
|   WBR metrics exported from [SCORES]                                  |
|   Gap to ideal? --> back to Phase 1                                   |
|                                                                       |
+-----------------------------------------------------------------------+
```

---

## 2. Architecture

### 2.1 Environment Topology

```
+---------------------------+          +---------------------------+
|   BETA AWS ACCOUNT        |          |   PROD AWS ACCOUNT        |
|                           |          |                           |
|  +---------------------+ |          |  +---------------------+ |
|  | AgentCore Runtime    | |          |  | AgentCore Runtime    | |
|  | (beta agent)         | |          |  | (prod agent)         | |
|  |                      | |          |  |                      | |
|  | - Beta tools config  | |          |  | - Prod tools config  | |
|  | - Beta DB/APIs       | |          |  | - Prod DB/APIs       | |
|  +----------+-----------+ |          |  +----------+-----------+ |
|             |              |          |             |              |
|  +----------+-----------+ |          |  +----------+-----------+ |
|  | Beta UI (Streamlit)  | |          |  | Prod UI (Streamlit)  | |
|  | - Agent owner testing| |          |  | - End users           | |
|  | - Thumbs up/down     | |          |  | - Thumbs up/down      | |
|  +----------------------+ |          |  +----------------------+ |
+-------------+-------------+          +-------------+-------------+
              |                                       |
              |          OTEL traces + scores          |
              +---------------+   +-------------------+
                              |   |
                              v   v
                    +-------------------+
                    |                   |
                    |     LANGFUSE      |
                    |                   |
                    | [TRACES]          |
                    | [SCORES]          |
                    | [DATASETS]        |
                    | [ANNOTATION QUEUE]|
                    | [PROMPT MGMT]     |
                    | [EVALUATORS]      |
                    |                   |
                    +-------------------+
```

### 2.2 Agent Components

Every agent has three independently versioned components:

| Component | Where managed | Change requires redeployment? |
|-----------|--------------|-------------------------------|
| **System Prompt** | Langfuse Prompt Management | No -- fetched at runtime |
| **Model** | `.env` (runtime), Langfuse LLM Connections (experiments) | Yes (runtime), No (experiments) |
| **Tools** | Code (`core/tools.py`) | Yes -- code change + deploy |

### 2.3 Langfuse Tab Mapping

| Langfuse Tab | Role in Platform |
|---|---|
| **TRACES** | All agent interactions (beta + prod). Each trace includes input, output, tool calls, latency, token usage. |
| **SCORES** | All evaluation data: LLM-as-a-Judge quality, user thumbs feedback, human annotations, experiment accuracy. Source for WBR metrics export. |
| **DATASETS** | Evaluation datasets (monthly + global). Input/expected-output pairs curated from annotated production traces. Used for offline experiments and CI/CD gates. |
| **ANNOTATION QUEUE** | Weekly review queue. Oncall annotates traces with correctness, helpfulness, tool-usage scores. Annotated traces feed into datasets. |
| **PROMPT MANAGEMENT** | System prompt versions. Labels control which version is live (`production`) vs testing (`staging`). |
| **EVALUATORS** | LLM-as-a-Judge configurations. Online evaluator (input+output) for live traces. Experiment evaluator (input+output+expected) for dataset runs. |

---

## 3. Phase 1: Offline Experimentation (Beta)

### 3.1 Flow

```
Developer changes (prompt / tools / model)
          |
          v
    [CI/CD Pipeline]
          |
          +---> [Unit tests for tools] -----> FAIL --> fix code
          |            |
          |          PASS
          |            |
          |            v
          +---> [Deploy to Beta AgentCore Runtime]
          |
          v
    [Eval dataset exists?]
          |
          +--YES--> [SDK Experiment: run agent against dataset]
          |                    |
          |                    v
          |            [LLM-as-a-Judge scores each item]
          |            [Results in SCORES + TRACES tabs]
          |                    |
          |                    v
          |            [Agent owner reviews in Langfuse]
          |            [Correct judge errors via annotation]
          |                    |
          |                    v
          |            [Accuracy >= threshold?]
          |              |              |
          |            YES             NO
          |              |              |
          |              v              v
          |         [Promote       [Iterate on prompt/
          |          to prod]       tools/model --> retry]
          |
          +--NO---> [Agent owner creates dataset]
                         |
                         +---> Option A: Interact via Beta UI,
                         |     curate traces into dataset
                         |
                         +---> Option B: Upload CSV with
                               input/expected-output pairs
                               |
                               v
                         [Dataset created --> re-run from top]
```

### 3.2 CI/CD Pipeline Detail

```yaml
# Pipeline stages
stages:
  - name: unit-tests
    description: Traditional unit tests for tools (no LLM needed)
    command: pytest tests/tools/

  - name: deploy-beta
    description: Deploy agent to beta AgentCore runtime
    command: |
      AGENTCORE_AGENT_NAME=${AGENT_NAME}_beta
      python3.11 scripts/agentcore_deploy.py

  - name: eval-gate
    description: Run eval dataset and check accuracy
    condition: eval dataset exists in Langfuse
    command: |
      python3.11 scripts/run_ci_evaluation.py \
        --dataset ${AGENT_NAME}-eval-global \
        --min-accuracy 0.7 \
        --environment beta
    on_failure: block deployment, notify agent owner

  - name: promote-to-prod
    description: Deploy to prod AgentCore runtime
    condition: eval-gate passed AND agent owner approval
    command: |
      AGENTCORE_AGENT_NAME=${AGENT_NAME}_prod
      python3.11 scripts/agentcore_deploy.py
```

### 3.3 Tool Testing Strategy

Tools that **read data** (get_product_info, get_return_policy) can be tested with unit tests using mocked data.

Tools that **mutate state** (create_order, update_account) require environment isolation:

| Environment | Tool Configuration |
|---|---|
| **Beta** | Tools point to beta databases, sandbox APIs, test accounts |
| **Prod** | Tools point to production databases, live APIs, real accounts |

This is controlled via environment variables in the AgentCore runtime deployment:

```
Beta:  TOOL_API_BASE_URL=https://api.beta.internal
Prod:  TOOL_API_BASE_URL=https://api.prod.internal
```

### 3.4 Creating the Eval Dataset (When None Exists)

**Option A: Interactive (Beta UI)**

1. Agent owner interacts with the beta agent through the Beta UI
2. All interactions are traced to Langfuse
3. Agent owner reviews traces, adds good/bad examples to dataset with correct expected output
4. Build up 30-50 items covering happy paths and edge cases

**Option B: CSV Upload**

1. Agent owner prepares a CSV with columns: `input`, `expected_output`
2. Upload via Langfuse UI (Datasets > Import) or via script:
   ```bash
   python3.11 scripts/seed_langfuse_dataset.py --csv my_eval_data.csv
   ```

### 3.5 Iteration Loop

When the agent doesn't meet accuracy targets, the agent owner iterates on the three components in order of ease:

```
1. PROMPT (easiest -- no redeployment)
   |
   | Edit in Langfuse UI, re-run experiment
   | Still failing?
   v
2. MODEL (medium -- env var change + redeploy)
   |
   | Switch to more capable model
   | Still failing?
   v
3. TOOLS (hardest -- code change + unit tests + redeploy)
   |
   | Fix tool logic, add new tools, improve data sources
   | Re-run full pipeline
```

---

## 4. Phase 2: Online Monitoring (Prod)

### 4.1 Flow

```
End Users
    |
    v
[Prod UI] --> [Prod AgentCore Runtime]
    |                    |
    |                    v
    |           [OTEL Traces --> Langfuse TRACES tab]
    |                    |
    |                    v
    |           [Online LLM-as-a-Judge --> SCORES tab]
    |                    (input + output only)
    |
    +--> [Thumbs up/down --> SCORES tab]

                         |
                         v
              [Weekly Oncall Review]
              ANNOTATION QUEUE tab
                    |
                    +---> Annotate traces (correctness, helpfulness, tool-usage)
                    |
                    +---> Correct LLM-as-a-Judge errors
                    |     (human overrides judge score)
                    |
                    +---> Add annotated traces to DATASETS tab
                    |     - Monthly dataset: <agent>-eval-2026-02
                    |     - Global dataset: <agent>-eval-global
                    |     - Include ground truth expected_output
                    |
                    +---> Export SCORES as CSV for WBR metrics
                          - Agent accuracy
                          - Judge accuracy
                          - User satisfaction
                          - Traces reviewed
```

### 4.2 Online Evaluators

Two LLM-as-a-Judge evaluators operate in different contexts:

| Evaluator | Context | Variables | When |
|-----------|---------|-----------|------|
| `online-quality-check` | Live traces | `{{input}}`, `{{output}}` | Every production trace (real-time) |
| `experiment-accuracy` | Experiments | `{{input}}`, `{{output}}`, `{{expected_output}}` | During offline dataset experiments |

### 4.3 Weekly Oncall Responsibilities

**Monday routine:**

1. Open Langfuse > Annotation Queues > `weekly-review`
2. Review traces flagged by:
   - `quality < 0.5` (LLM-as-a-Judge flagged)
   - `thumbs_feedback = 0` (user flagged)
   - Random sample of other traces (spot check)
3. For each trace:
   - Score: `correctness` (0/1), `helpfulness`, `tool-usage`
   - If LLM-as-a-Judge was wrong, the human annotation overrides it
   - If trace is a good test case, add to dataset with expected output
4. Export scores from SCORES tab for WBR metrics

### 4.4 WBR Metrics (Weekly Business Review)

Export from Langfuse SCORES tab and compute:

| Metric | Formula | Target | Source |
|--------|---------|--------|--------|
| **Agent accuracy** | `correctness=1 / total annotations` | >= 90% | Human annotations |
| **Judge accuracy** | `% agreement between quality score and correctness` | >= 85% | Cross-reference judge + human |
| **User satisfaction** | `thumbs_feedback=1 / total feedback` | >= 80% | User feedback scores |
| **Traces reviewed** | Count of annotations this week | >= 30/week | Annotation queue |
| **Dataset growth** | New items added to global dataset | Monotonically increasing | Dataset tab |

### 4.5 When to Go Back to Phase 1

| Signal | Action |
|--------|--------|
| Agent accuracy < 80% | Urgent: iterate on prompt/tools/model in beta |
| Agent accuracy < 90% | Improvement needed: iterate on prompt first |
| Judge accuracy < 85% | Recalibrate: update judge prompt, review disagreements |
| User satisfaction < 80% | Investigate: deep dive negative feedback traces |
| New failure pattern found | Add to dataset, iterate in beta, redeploy |

---

## 5. Data Flow Across Langfuse Tabs

```
                        PHASE 1 (Beta)                    PHASE 2 (Prod)
                        ==============                    ===============

TRACES tab         Beta agent traces                 Prod agent traces
                   (experiment runs)                  (real user interactions)
                        |                                     |
                        v                                     v
SCORES tab         experiment-accuracy               quality (LLM judge)
                   (from SDK experiment)              thumbs_feedback (users)
                        |                             correctness (human)
                        |                             helpfulness (human)
                        |                             tool-usage (human)
                        |                                     |
                        |                                     v
ANNOTATION QUEUE        |                            Weekly oncall reviews
                        |                            traces, scores them,
                        |                            corrects judge errors
                        |                                     |
                        v                                     v
DATASETS tab       Agent owner creates              Oncall adds annotated
                   initial eval dataset              traces with ground truth
                   (from beta testing                expected output to
                   or CSV upload)                    monthly + global datasets
                        |                                     |
                        +----------------+--------------------+
                                         |
                                         v
                              Eval dataset used for:
                              - CI/CD gate (beta deploys)
                              - Prompt experiments
                              - Model comparisons
                              - Regression testing

PROMPT MGMT tab    staging label                     production label
                   (testing new versions)             (live version)
                        |                                     ^
                        +-- experiment passes -->-- promote ---+

EVALUATORS tab     experiment-accuracy               online-quality-check
                   (input+output+expected)            (input+output only)
```

---

## 6. Agent Promotion: Beta to Prod

### 6.1 Promotion Criteria

All must be true before promoting to production:

- [ ] Tool unit tests pass (CI/CD)
- [ ] SDK experiment accuracy >= threshold against global eval dataset
- [ ] Agent owner has reviewed experiment results in Langfuse
- [ ] Agent owner has corrected any LLM-as-a-Judge errors via annotation
- [ ] No regressions on previously passing test cases
- [ ] Agent owner explicitly approves promotion

### 6.2 What Gets Promoted

| Component | How it's promoted |
|-----------|------------------|
| **System prompt** | Change label from `staging` to `production` in Langfuse Prompt Management |
| **Model** | Update `BEDROCK_MODEL_ID` in prod `.env` + redeploy |
| **Tools** | Code merge to main + CI/CD deploys to prod AgentCore runtime |

### 6.3 Promotion Diagram

```
Beta Account                     Langfuse                      Prod Account
============                     =======                       ============

Agent code ----merge to main---> CI/CD ----deploy-----------> Prod AgentCore
(tools)                            |                            Runtime
                                   |
                                   +---> run_ci_evaluation.py
                                   |     against eval dataset
                                   |           |
                                   |         PASS?
                                   |        /    \
                                   |      YES     NO --> block
                                   |       |
                                   v       v
                              Prompt: label=production
                              (takes effect immediately)
```

---

## 7. Dual Accuracy Tracking

The platform tracks the accuracy of **two systems** independently:

### 7.1 Agent Accuracy

How often the agent gives correct, helpful responses.

```
Ground truth: human correctness annotations
Measurement:  correctness=1 count / total annotations
Improvement:  iterate on prompt, tools, model
```

### 7.2 LLM-as-a-Judge Accuracy

How often the automated judge agrees with human reviewers.

```
Ground truth: human correctness annotations
Measurement:  % of traces where (quality>=0.5) == (correctness=1)
Improvement:  iterate on judge prompt, judge model, scoring criteria
```

Both are tracked monthly:

| Month | Agent Accuracy | Judge Accuracy | Traces Reviewed | Dataset Size |
|-------|---------------|----------------|-----------------|--------------|
| Feb 2026 | 85% | 90% | 50 | 60 |
| Mar 2026 | 88% | 92% | 65 | 95 |
| Apr 2026 | 91% | 91% | 40 | 115 |

The judge is a force multiplier -- once calibrated above 85%, it can reliably flag issues at scale. But it must always be validated against human annotations.

---

## 8. Multi-Agent Considerations

### 8.1 Independent Agents (Separate Runtimes)

Each agent gets its own:
- Langfuse project (or tags within a shared project)
- AgentCore runtime (beta + prod)
- Evaluation dataset
- Annotation queue
- Prompt in Prompt Management
- LLM-as-a-Judge evaluators

### 8.2 Nested Agents (Strands sub-agents)

```
Parent Agent Trace
  |-- Sub-Agent A Span
  |-- Sub-Agent B Span
```

- Single trace in Langfuse with nested observations
- Score at trace level (overall) and observation level (per sub-agent)
- Each sub-agent's prompt managed separately in Prompt Management

### 8.3 Agent-as-a-Tool (AgentCore calling AgentCore)

```
Orchestrator Runtime --> Agent B Runtime --> Agent C Runtime
      |                       |                    |
   Trace 1               Trace 2              Trace 3
```

- Each runtime creates its own trace
- Correlate via `session_id` across traces
- Evaluate at both levels: orchestrator routing + individual agent quality
- Each agent has its own eval dataset and improvement cycle

### 8.4 AgentCore Gateway (Multiple Tool Targets)

```
Agent --> Gateway --> Lambda A (tool: check_warranty)
                 --> Lambda B (tool: web_search)
```

- Tool invocations appear as spans within the agent trace
- Score per-tool accuracy via `tool-usage` annotation
- Gateway tools tested via the same beta/prod environment isolation

---

## 9. Production Sampling Strategy

### 9.1 Problem

In production, two automated signals are available for every trace:

| Signal | Source | Values |
|--------|--------|--------|
| **Thumbs feedback** | User (via UI) | Up (1), Down (0), or Missing |
| **Judge score** | Online LLM-as-a-Judge | Good (1) or Bad (0) |

Human annotation capacity is limited (e.g., 30-50 traces/week). A random sample wastes budget on uninformative traces. Instead, we use **stratified sampling with importance weights** to prioritize the most informative traces for human review.

### 9.2 Signal Matrix & Expected Accuracy

Combining the two signals produces 6 categories. The expected agent accuracy column is the approximate proportion of truly correct responses you would observe if you reviewed every trace in that bucket.

```
                       Judge Score
                    0 (Bad)    1 (Good)
                 +-----------+-----------+
Thumbs Down (0)  |    W1     |    W2     |
                 +-----------+-----------+
Thumbs Up (1)    |    W3     |    W4     |
                 +-----------+-----------+
Missing          |    W5     |    W6     |
                 +-----------+-----------+
```

| Category | Thumbs | Judge | Expected Agent Accuracy | Interpretation |
|----------|--------|-------|------------------------|----------------|
| **W1** | Down | Bad (0) | ~15% | Consensus failure — both signals agree the agent failed. Almost always truly wrong. |
| **W2** | Down | Good (1) | ~20% | Judge miscalibrated — user says bad, judge says good. Agent is still mostly wrong. Judge needs recalibration. |
| **W3** | Up | Bad (0) | ~80% | Judge miscalibrated — user says good, judge says bad. Agent is mostly right. Judge is overly harsh. |
| **W4** | Up | Good (1) | ~100% | Consensus success — both signals agree. Agent is almost always right. |
| **W5** | Missing | Bad (0) | ~20% | Unconfirmed flag — judge flagged it, no user signal. Likely bad. |
| **W6** | Missing | Good (1) | ~95% | Likely fine — judge passed, no contradicting signal. Bulk of traffic. |

### 9.3 Sampling Strategy: Two Tiers

**Tier 1: Full coverage (W1-W4)**

Traces with user feedback are the minority of traffic (~20% of users leave thumbs up/down). Because this volume is small, **review 100% of traces that have user feedback**. These traces are the most valuable because:

- They provide the ground truth for measuring **judge accuracy** (human annotation vs judge score)
- They validate whether user sentiment aligns with actual correctness
- W2 and W3 (disagreements) directly calibrate the judge

**Tier 2: Capacity-based sampling (W5-W6)**

After reviewing all Tier 1 traces, allocate remaining annotation capacity to W5 and W6. Weight the sampling toward W5 because:

- W5 (judge=bad, ~20% accuracy) — likely contains real failures worth reviewing
- W6 (judge=good, ~95% accuracy) — mostly fine, but a small sample catches silent failures

Recommended split of remaining capacity: **~80% to W5, ~20% to W6**.

### 9.4 Worked Example

Assuming 1,000 traces/week, 20% user feedback rate, 85% judge pass rate:

| Category | Est. % of Traffic | Traces/Week | Sampling | Annotations/Week |
|----------|------------------|-------------|----------|-----------------|
| W1 | ~2% | 20 | 100% | 20 |
| W2 | ~1% | 10 | 100% | 10 |
| W3 | ~2% | 20 | 100% | 20 |
| W4 | ~15% | 150 | 100% | 150 |
| | | | **Tier 1 subtotal** | **200** |

If annotation capacity is 250/week, remaining budget = 50:

| Category | Traces/Week | Budget Allocation | Sampling Rate | Annotations/Week |
|----------|-------------|-------------------|---------------|-----------------|
| W5 | 120 | 80% of 50 = 40 | 33% | 40 |
| W6 | 680 | 20% of 50 = 10 | 1.5% | 10 |
| | | **Tier 2 subtotal** | | **50** |

**Total: ~250 annotations/week.**

> **Scaling note:** If Tier 1 volume exceeds capacity (e.g., high-traffic agent where 20% feedback = thousands of traces), introduce sub-sampling within Tier 1 — prioritize W2 and W3 (disagreements) over W1 and W4 (consensus), since disagreements are more informative for judge calibration.

### 9.5 What Each Category Teaches You

| Category | Primary learning | Action on finding |
|----------|-----------------|-------------------|
| **W1** (both bad) | Confirms failure patterns, identifies common failure modes | Add to dataset as negative example. If recurring, escalate to Phase 1. |
| **W2** (user bad, judge good) | Judge is too lenient — specific blind spots | Update judge prompt to catch this failure type. |
| **W3** (user good, judge bad) | Judge is too strict — false positive patterns | Update judge prompt to reduce false flags. |
| **W4** (both good) | Validates happy path. Confirms judge + agent alignment. | Add strong examples to dataset. Low-priority review. |
| **W5** (no feedback, judge bad) | Validates judge catches real issues without user signal | Confirms or refutes judge flags. Feeds judge accuracy metric. |
| **W6** (no feedback, judge good) | Catches silent failures the judge missed | If errors found, high signal for judge improvement. |

### 9.6 Calibration Feedback Loop

As human annotations accumulate:

1. **Measure judge accuracy per category** — e.g., if W2 annotations show the judge is mostly right (user was wrong), the expected accuracy for W2 shifts upward
2. **Rebalance Tier 2 weights quarterly** — as the judge improves, W5 volume may decrease (fewer false flags), allowing more budget for W6 spot-checks
3. **Track annotation yield** — what % of sampled traces lead to dataset additions or judge corrections? Low yield in a category means reduce its weight

---

## 10. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **SDK experiments for tool testing** (not Langfuse UI experiments) | Langfuse UI experiments are raw LLM calls without tools. Only SDK experiments invoke the full agent with tool access. |
| **Separate beta/prod AgentCore runtimes** | Agents that mutate state need environment isolation. Beta tools point to sandbox systems. |
| **Two LLM-as-a-Judge evaluators** | Online (input+output) for real-time monitoring. Experiment (input+output+expected) for offline accuracy measurement. Different contexts require different prompts. |
| **Human-in-the-loop for dataset curation** | Expected output (ground truth) requires domain expertise. LLM-as-a-Judge can flag issues but cannot write authoritative ground truth. |
| **Monthly + global datasets** | Monthly datasets enable trend tracking. Global dataset enables regression testing. Both grow from the same annotation workflow. |
| **Prompt labels (production/staging)** | Prompts can be tested without redeployment. Labels provide instant rollback capability. |
| **Dual accuracy tracking (agent + judge)** | The judge is a tool, not ground truth. Its accuracy must be measured and improved alongside the agent. |

---

## 11. Appendix A: Feedback Loop Agent (Proposed)

### 11.1 Concept

Today the link between Phase 2 (online monitoring) and Phase 1 (offline experimentation) is manual: a human reviews the weekly metrics, reads annotation notes, and decides what to improve. The **Feedback Loop Agent** automates this analysis. It ingests production signals, the codebase, and initiative goals, then produces a prioritised list of improvement proposals that developers can act on immediately.

```
Phase 2 (Prod)                  Feedback Loop Agent               Phase 1 (Beta)
===============                 ===================               ===============

Annotated traces ──┐
                   │
Score trends ──────┤
                   │
Failure clusters ──┼──► [ Analyse ] ──► [ Propose ] ──► Improvement backlog
                   │         ▲                              │
Weekly events ─────┤         │                              │
                   │    Codebase context                    v
Success metric ────┘    (prompt, tools, model)         Developer picks up
  gaps                                                  proposal, iterates
                                                        in beta, redeploys
```

### 11.2 Inputs

The agent consumes six input categories, each pulled automatically:

| Input | Source | What it provides |
|-------|--------|-----------------|
| **Annotated traces** | Langfuse Annotation Queue (completed items) | Ground-truth labels, human comments, failure examples from the past week |
| **Score trends** | Langfuse Scores API | Week-over-week delta for agent accuracy, judge accuracy, user satisfaction |
| **Failure clusters** | Langfuse Traces + Scores (W1, W2 categories) | Recurring failure patterns grouped by topic, tool, or error type |
| **Success metric gaps** | Initiative targets vs. current actuals | Which KPIs are below target and by how much |
| **Events of the week** | Changelog / deployment log / incident log | Recent deploys, prompt changes, tool updates, incidents — context for regressions |
| **Codebase** | Git repo (prompt text, tool implementations, model config) | Current system prompt, tool logic, model ID — so proposals reference real code |

### 11.3 Analysis Pipeline

The agent runs weekly (after annotation review is complete) through four stages:

```
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: COLLECT                                               │
│  Pull last 7 days of annotated traces, scores, and events       │
│  via Langfuse API + git log                                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: CLUSTER                                               │
│  Group failures by:                                             │
│    - Topic (product info, returns, troubleshooting, etc.)       │
│    - Component (prompt gap, tool bug, model limitation)         │
│    - Root cause (missing knowledge, wrong tool selected,        │
│      hallucination, formatting, tone)                           │
│  Use embedding similarity to merge near-duplicate failures      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: DIAGNOSE                                              │
│  For each cluster, determine the most likely component to fix:  │
│                                                                 │
│    Prompt issue?                                                │
│      - Missing instruction, ambiguous guidance, wrong tone      │
│      - Signal: failures span multiple tools/topics              │
│                                                                 │
│    Tool issue?                                                  │
│      - Wrong data returned, tool not invoked, tool error        │
│      - Signal: failures concentrate on one tool                 │
│                                                                 │
│    Model issue?                                                 │
│      - Hallucination despite correct prompt + tools             │
│      - Signal: correct tool called, correct data returned,      │
│        but agent synthesised wrong answer                       │
│                                                                 │
│    Knowledge gap?                                               │
│      - No tool exists for the user's question                   │
│      - Signal: agent says "I don't have that information"       │
│                                                                 │
│  Read the relevant code (prompt text, tool functions) to        │
│  ground the diagnosis in actual implementation                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────┐
│  Stage 4: PROPOSE                                               │
│  For each diagnosed cluster, generate a concrete proposal:      │
│                                                                 │
│    - What to change (specific prompt edit, tool fix, new tool)  │
│    - Why (link to failure cluster + example traces)             │
│    - Expected impact (estimated accuracy lift based on cluster  │
│      size relative to total traffic)                            │
│    - Effort (prompt-only = low, tool change = medium,           │
│      new tool/model = high)                                     │
│    - Priority score = impact × (1 / effort)                     │
└─────────────────────────────────────────────────────────────────┘
```

### 11.4 Output: Weekly Improvement Report

The agent produces a structured report delivered to the agent owner (e.g., via Slack, email, or a Langfuse annotation).

```
══════════════════════════════════════════════════════════════
  WEEKLY IMPROVEMENT REPORT — customer-support-agent
  Week of 2026-02-09  |  Generated by Feedback Loop Agent
══════════════════════════════════════════════════════════════

METRICS SNAPSHOT
  Agent accuracy:     82% (target: 90%)  ▼ 3% from last week
  Judge accuracy:     88% (target: 85%)  ── stable
  User satisfaction:  76% (target: 80%)  ▼ 2% from last week
  Traces reviewed:    45 / 50 target

──────────────────────────────────────────────────────────────
PROPOSAL 1  [Priority: HIGH]  [Component: Prompt]
──────────────────────────────────────────────────────────────
Cluster:   "Accessory return conditions" (12 failures this week)
Root cause: System prompt says "help with returns" but does not
            instruct the agent to always call get_return_policy
            before answering return questions. Agent hallucinated
            return windows for accessories in 8/12 cases.
Proposal:  Add to system prompt:
           "For ANY question about returns, refunds, or exchanges,
            you MUST call get_return_policy before responding.
            Never state return windows from memory."
Evidence:  trace_id: abc123, def456, ghi789 (3 examples linked)
Impact:    ~12 traces/week → est. +2.5% agent accuracy
Effort:    Low (prompt-only, no redeployment)

──────────────────────────────────────────────────────────────
PROPOSAL 2  [Priority: MEDIUM]  [Component: Tool]
──────────────────────────────────────────────────────────────
Cluster:   "Warranty lookup failures" (7 failures this week)
Root cause: get_technical_support tool returns generic steps when
            asked about warranty. No warranty-specific tool exists.
            Agent tries to help but cannot check warranty status.
Proposal:  Create new tool `check_warranty_status(serial_number)`
           that queries the warranty database.
Evidence:  trace_id: jkl012, mno345 (2 examples linked)
Impact:    ~7 traces/week → est. +1.5% agent accuracy
Effort:    High (new tool + API integration + deploy)

──────────────────────────────────────────────────────────────
PROPOSAL 3  [Priority: LOW]  [Component: Judge]
──────────────────────────────────────────────────────────────
Cluster:   W3 disagreements — judge flags correct greetings
           as low quality (5 false positives this week)
Root cause: Judge prompt penalises short responses. Simple
            greetings like "Hello! How can I help?" score 0.
Proposal:  Update judge prompt to exclude greeting-only
           interactions from quality scoring, or add exception:
           "Short greetings are acceptable for greeting inputs."
Evidence:  trace_id: pqr678, stu901 (2 examples linked)
Impact:    Reduces W3 noise, improves judge accuracy by ~2%
Effort:    Low (judge prompt edit in Langfuse Evaluators)

══════════════════════════════════════════════════════════════
  EVENTS THIS WEEK
  - Mon: Prompt v3 deployed (added multilingual greeting)
  - Wed: 15% spike in "accessory return" queries (marketing campaign?)
  - Thu: Judge accuracy dip to 84% (recovered Fri after W3 review)
══════════════════════════════════════════════════════════════
```

### 11.5 Agent Architecture

The Feedback Loop Agent is itself a Strands agent with tools:

| Tool | Purpose |
|------|---------|
| `query_langfuse_scores` | Pull score trends and compute WoW deltas |
| `query_langfuse_traces` | Fetch annotated traces with human labels and comments |
| `query_langfuse_annotations` | Get completed annotation queue items for the week |
| `cluster_failures` | Group failure traces by embedding similarity + metadata |
| `read_codebase` | Read current system prompt, tool implementations, model config from git |
| `read_changelog` | Parse recent git commits and deployment events |
| `generate_proposal` | Produce a structured improvement proposal for a failure cluster |

System prompt (simplified):

```
You are the Feedback Loop Agent. Your job is to analyse the past week's
production data for an AI agent and propose concrete improvements.

For each failure cluster you identify:
1. Diagnose the root cause (prompt, tool, model, or knowledge gap)
2. Read the relevant source code to ground your diagnosis
3. Write a specific, actionable proposal with code-level detail
4. Estimate impact (based on cluster size) and effort
5. Link to example trace IDs as evidence

Prioritise proposals by impact/effort ratio. A prompt fix that
addresses 15 failures/week is better than a new tool that addresses 3.

Never propose changes you cannot justify with data from the traces.
```

### 11.6 Execution Modes

| Mode | Trigger | Output |
|------|---------|--------|
| **Weekly scheduled** | Cron (e.g., Monday 8 AM after annotation review) | Full report → Slack channel + stored in Langfuse as annotation |
| **On-demand** | Developer runs `python scripts/run_feedback_loop.py` | Full report → stdout |
| **Continuous (future)** | Real-time stream of annotated traces | Incremental proposals as failures accumulate above threshold |

### 11.7 Guardrails

The Feedback Loop Agent **proposes** but never **executes**:

- It does NOT edit the system prompt in Langfuse
- It does NOT commit code changes
- It does NOT trigger deployments
- It does NOT modify datasets or annotation queues

All proposals require human approval before action. The agent is an advisor, not an actor. This preserves the human-in-the-loop principle established in the main HLD.

### 11.8 Measuring the Agent's Own Value

Track whether the Feedback Loop Agent's proposals are useful:

| Metric | How to measure |
|--------|---------------|
| **Proposal acceptance rate** | % of proposals the developer acts on |
| **Accuracy lift per proposal** | Delta in agent accuracy after implementing a proposal |
| **Time to action** | How quickly proposals are picked up (days from report to beta experiment) |
| **False positive rate** | % of proposals that turn out to be wrong or unhelpful after investigation |

If acceptance rate drops below 50%, recalibrate the agent's clustering thresholds or diagnostic prompts.

### 11.9 Relationship to the Main Loop

```
                    ┌──────────────────────────────────┐
                    │                                  │
                    v                                  │
            Phase 2: Online                            │
            (prod traces, scores,                      │
             annotations, events)                      │
                    │                                  │
                    v                                  │
         ┌──────────────────────┐                      │
         │  Feedback Loop Agent │                      │
         │  (analyse + propose) │                      │
         └──────────┬───────────┘                      │
                    │                                  │
                    v                                  │
         Improvement backlog                           │
         (prioritised proposals)                       │
                    │                                  │
                    v                                  │
         Developer picks proposal ──► Phase 1: Offline │
                                      (experiment,     │
                                       validate,       │
                                       promote) ───────┘
```

The Feedback Loop Agent replaces the manual "gap to ideal? → back to Phase 1" step in Section 1 with an automated, data-driven analysis that tells the developer **what** to fix, **where** in the code, and **why** it matters.

---

## 12. Appendix B: Langfuse Tab Quick Reference

```
+------------------+----------------------------------------------+----------------------+
| Tab              | Phase 1 (Beta)                               | Phase 2 (Prod)       |
+------------------+----------------------------------------------+----------------------+
| TRACES           | Beta agent experiment traces                  | Prod user traces     |
| SCORES           | experiment-accuracy (SDK)                     | quality (judge)      |
|                  |                                              | thumbs_feedback      |
|                  |                                              | correctness (human)  |
| DATASETS         | Initial dataset (created by agent owner)      | Growing dataset      |
|                  |                                              | (from annotations)   |
| ANNOTATION QUEUE | Agent owner reviews experiment results        | Weekly oncall review  |
| PROMPT MGMT      | staging label (testing)                       | production label     |
| EVALUATORS       | experiment-accuracy                           | online-quality-check |
+------------------+----------------------------------------------+----------------------+
```
