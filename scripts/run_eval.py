#!/usr/bin/env python3
"""Run LLM-as-judge evaluation against the deployed AgentCore runtime.

Fetches a Langfuse dataset, invokes the agent for each item, and uses a
Bedrock LLM judge to score correctness against ground truth. Results are
recorded back to Langfuse as a dataset run.

Usage:
    # With .env
    set -a && source .env && set +a
    python3.11 scripts/run_eval.py

    # Custom threshold
    python3.11 scripts/run_eval.py --min-score 0.5 --dataset customer-support-eval
"""

import argparse
import csv
import json
import os
import sys
import urllib.parse
import uuid
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import boto3
import requests
from bedrock_agentcore_starter_toolkit.services.runtime import get_data_plane_endpoint

from core.cognito_auth import authenticate_user, get_or_create_cognito_config
from core.config import (
    AWS_REGION,
    BEDROCK_REGION,
    COGNITO_PASSWORD,
    COGNITO_USERNAME,
)
from core.langfuse_client import get_langfuse_client

JUDGE_PROMPT_TEMPLATE = """\
You are an expert evaluator for an Italian notarial law AI assistant.
You must evaluate whether the assistant's response is correct by comparing it
against the expected output (ground truth written by legal experts).

Evaluation criteria:
- Legal accuracy: Are the cited articles, doctrinal references, and legal principles correct?
- Completeness: Does the response cover the key points from the expected output?
- Source citation: Does the response cite relevant normative sources or doctrinal references?
- No hallucination: Does the response avoid inventing legal provisions or doctrinal positions?

Score with a binary value:
- 1 = CORRECT: Response is legally accurate, covers the key points from the expected output, \
and does not hallucinate legal provisions. Minor wording differences or omissions of \
non-essential details are acceptable.
- 0 = INCORRECT: Response is legally wrong, missing critical information, contains \
hallucinated provisions, or is off-topic.

IMPORTANT: The expected output and the actual response are in Italian. You must evaluate
the legal substance, not the exact wording. Paraphrased correct answers should score 1.

Customer Input: {query}
Expected Output: {ground_truth}
Actual Output: {generation}

Return ONLY a JSON object: {{"score": <int>, "reasoning": "<brief explanation in English>"}}"""


def _region() -> str:
    return AWS_REGION or boto3.session.Session().region_name


def _get_runtime_arn() -> str:
    runtime_arn = os.getenv("AGENTCORE_RUNTIME_ARN")
    if runtime_arn:
        return runtime_arn
    ssm = boto3.client("ssm", region_name=_region())
    return ssm.get_parameter(Name="/app/customersupport/agentcore/runtime_arn")[
        "Parameter"
    ]["Value"]


def _invoke_runtime(
    region: str,
    runtime_arn: str,
    token: str,
    prompt: str,
    session_id: str,
    timeout: int,
) -> str:
    """Invoke the AgentCore runtime and return the response text."""
    endpoint = get_data_plane_endpoint(region)
    url = f"{endpoint}/runtimes/{urllib.parse.quote(runtime_arn, safe='')}/invocations"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
        "Authorization": f"Bearer {token}",
    }
    payload = {"prompt": prompt, "actor_id": "eval_runner"}
    response = requests.post(
        url,
        params={"qualifier": "DEFAULT"},
        headers=headers,
        json=payload,
        timeout=(10, timeout),
    )
    response.raise_for_status()
    if not response.content:
        return ""
    data = response.json()
    if isinstance(data, str):
        return data
    return data.get("response", str(data))


def _run_correctness_judge(
    query: str,
    generation: str,
    ground_truth: str,
    bedrock_client,
    model_id: str,
) -> tuple:
    """Run the LLM judge and return (score, reasoning)."""
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        query=query, generation=generation, ground_truth=ground_truth
    )
    response = bedrock_client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 512, "temperature": 0.0},
    )
    output_text = response["output"]["message"]["content"][0]["text"]

    # Parse JSON — handle markdown code fences
    cleaned = output_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    result = json.loads(cleaned)
    return float(result["score"]), str(result.get("reasoning", ""))


def main():
    parser = argparse.ArgumentParser(description="Run LLM-as-judge eval pipeline")
    parser.add_argument("--dataset", default="italian-legal-eval")
    parser.add_argument("--judge-model", default="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                        help="Bedrock model ID for LLM judge")
    parser.add_argument("--min-score", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--export", default=None, help="Export results to CSV file path")
    args = parser.parse_args()

    # 1. Initialize clients
    langfuse = get_langfuse_client()
    if not langfuse:
        print("ERROR: Langfuse client not configured.")
        sys.exit(1)

    config = get_or_create_cognito_config()
    token = authenticate_user(COGNITO_USERNAME or "admin", COGNITO_PASSWORD, config)
    runtime_arn = _get_runtime_arn()
    region = _region()
    bedrock_region = BEDROCK_REGION or region
    bedrock_client = boto3.client("bedrock-runtime", region_name=bedrock_region)
    judge_model_id = args.judge_model

    print(f"Runtime: {runtime_arn}")
    print(f"Dataset: {args.dataset}")
    print(f"Judge model: {judge_model_id}")
    print(f"Min score: {args.min_score}")
    print()

    # 2. Fetch dataset and filter to active items only
    dataset = langfuse.get_dataset(args.dataset)
    active_items = [
        item for item in dataset.items
        if getattr(item, "status", "ACTIVE") != "ARCHIVED"
    ]
    run_name = args.run_name or f"eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print(f"Running evaluation: {run_name}")
    print(f"Items: {len(active_items)} (of {len(dataset.items)} total)")
    print("=" * 60)

    # 3. Run evaluation using item.run() context manager
    results = []  # list of (query, score, reasoning, domain, tipologia)

    for i, item in enumerate(active_items):
        query = item.input.get("input", "") if isinstance(item.input, dict) else str(item.input)
        ground_truth = str(item.expected_output) if item.expected_output else ""
        metadata = getattr(item, "metadata", {}) or {}
        domain = metadata.get("domain", "")
        tipologia = metadata.get("tipologia", "")
        print(f"\n[{i + 1}/{len(active_items)}] [{domain}|{tipologia}] \"{query[:60]}\"")

        # Invoke agent inside item.run() so the trace is linked to the dataset
        try:
            with item.run(run_name=run_name) as span:
                span.update(input={"input": query})
                session_id = str(uuid.uuid4())
                print(f"  Invoking agent...")
                generation = _invoke_runtime(
                    region, runtime_arn, token, query, session_id, args.timeout
                )
                span.update(output=generation)

                # Run LLM judge
                try:
                    score, reasoning = _run_correctness_judge(
                        query, generation, ground_truth, bedrock_client, judge_model_id
                    )
                except Exception as e:
                    score, reasoning = 0.0, f"Judge error: {e}"

                # Record score on the trace
                span.score(
                    name="correctness",
                    value=score,
                    data_type="NUMERIC",
                    comment=reasoning,
                )

                status = "CORRECT" if score >= args.min_score else "INCORRECT"
                print(f"  [{status}] {int(score)} — {reasoning}")
                results.append((query, score, reasoning, domain, tipologia))

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append((query, 0.0, f"Runtime error: {e}", domain, tipologia))

    # 4. Summary
    langfuse.flush()

    print()
    print("=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)

    scores = [s for _, s, _, _, _ in results]
    for query, score, reasoning, domain, tipologia in results:
        status = "CORRECT" if score >= args.min_score else "INCORRECT"
        print(f"  [{status}] {int(score)} | [{domain}|{tipologia}] {query[:50]}")

    correct = sum(1 for s in scores if s >= args.min_score)
    total = len(scores)
    accuracy = correct / total if total else 0.0

    print()
    print(f"Accuracy: {accuracy:.1%} ({correct}/{total} correct)")
    print(f"Langfuse run: {run_name}")

    # Per-domain breakdown
    domain_scores = {}
    for _, score, _, domain, _ in results:
        domain_scores.setdefault(domain, []).append(score)
    if domain_scores:
        print("\nPer-domain accuracy:")
        for domain, d_scores in sorted(domain_scores.items()):
            d_correct = sum(1 for s in d_scores if s >= args.min_score)
            d_acc = d_correct / len(d_scores) if d_scores else 0.0
            print(f"  {domain}: {d_acc:.1%} ({d_correct}/{len(d_scores)})")

    # Export to CSV
    export_path = args.export or f"eval-results-{run_name}.csv"
    with open(export_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["query", "score", "result", "domain", "tipologia", "reasoning"])
        for query, score, reasoning, domain, tipologia in results:
            status = "CORRECT" if score >= args.min_score else "INCORRECT"
            writer.writerow([query, int(score), status, domain, tipologia, reasoning])
        writer.writerow([])
        writer.writerow(["SUMMARY", f"{accuracy:.1%}", f"{correct}/{total} correct", "", "", run_name])
    print(f"Results exported to: {export_path}")

    if accuracy >= args.min_score:
        print(f"\nRESULT: PASSED (accuracy {accuracy:.1%} >= {args.min_score})")
        sys.exit(0)
    else:
        print(f"\nRESULT: FAILED (accuracy {accuracy:.1%} < {args.min_score})")
        sys.exit(1)


if __name__ == "__main__":
    main()
