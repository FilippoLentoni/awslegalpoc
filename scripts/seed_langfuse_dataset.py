"""Seed an evaluation dataset into Langfuse for prompt experiments.

Re-running this script upserts items (same ID = overwrite, not duplicate).

Usage:
    set -a && source .env && set +a && python3.11 scripts/seed_langfuse_dataset.py
"""

import hashlib
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.langfuse_client import get_langfuse_client

DATASET_NAME = "customer-support-eval"

ITEMS = [
    {
        "input": {"input": "Hello!"},
        "expected_output": "The assistant should greet the user warmly and professionally, and offer to help with HR or candidate-related questions.",
    },
    {
        "input": {"input": "What can you do?"},
        "expected_output": "The assistant should describe its capabilities: searching the knowledge base for candidate CVs and providing information about candidates' experience, skills, and background.",
    },
    {
        "input": {"input": "Tell me about Filippo Lentoni"},
        "expected_output": "The assistant should search the knowledge base and provide a summary of Filippo Lentoni: Senior Applied Scientist at Amazon, based in New York, with experience in supply chain science, ML, and GenAI.",
    },
    {
        "input": {"input": "What is Filippo's educational background?"},
        "expected_output": "The assistant should search the knowledge base and report that Filippo holds an MSc in Mathematical Engineering (Statistical Learning) and a BSc in Mathematical Engineering, both from Politecnico di Milano.",
    },
    {
        "input": {"input": "What programming tools and technologies has Filippo worked with?"},
        "expected_output": "The assistant should search the knowledge base and list technologies such as AWS CDK, PyTorch, SageMaker, Bedrock Agents, Lambda, EC2, S3, Streamlit, SQL, Redshift, QuickSight, XGBoost, GluonTS, and DeepAR.",
    },
    {
        "input": {"input": "Does Filippo have experience with generative AI?"},
        "expected_output": "The assistant should search the knowledge base and confirm that Filippo has GenAI experience: deploying LLM (Claude) and agentic workflows for supply chain automation, and defining the GenAI automation roadmap at Amazon with VP-level visibility.",
    },
    {
        "input": {"input": "What languages does Filippo speak?"},
        "expected_output": "The assistant should search the knowledge base and report that Filippo speaks English (C2 level) and Italian (native).",
    },
    {
        "input": {"input": "Has Filippo published any research?"},
        "expected_output": "The assistant should search the knowledge base and mention that Filippo's research papers were accepted at the Amazon Machine Learning Conference (AMLC) and the Amazon Computer Vision Conference (ACVC) in 2024.",
    },
    {
        "input": {"input": "What mentoring or community activities has Filippo been involved in?"},
        "expected_output": "The assistant should search the knowledge base and mention Filippo's role as a mentor at LeadTheFuture, organizing Amazon Data Science Week in Italy, AWS GenAI workshops at University of Leuven, and science lead at TU Munich Data Innovation Lab.",
    },
    {
        "input": {"input": "Tell me about a candidate with machine learning experience"},
        "expected_output": "The assistant should search the knowledge base and identify Filippo Lentoni as a candidate with extensive ML experience including XGBoost forecasting, multimodal deep neural networks, anomaly detection with CLIP embeddings, and ensemble methods.",
    },
]

lf = get_langfuse_client()
if not lf:
    print("ERROR: Langfuse client not configured.")
    sys.exit(1)

# Create dataset
try:
    dataset = lf.create_dataset(
        name=DATASET_NAME,
        description="Evaluation dataset for customer support agent prompt experiments",
    )
    print(f"Created dataset '{DATASET_NAME}'")
except Exception:
    print(f"Dataset '{DATASET_NAME}' already exists, adding items...")

# Archive existing items that won't be overwritten
try:
    existing = lf.get_dataset(DATASET_NAME)
    new_ids = set()
    for item in ITEMS:
        item_id = hashlib.md5(item["input"]["input"].encode()).hexdigest()
        new_ids.add(item_id)
    for old_item in existing.items:
        if old_item.id not in new_ids:
            lf.create_dataset_item(
                dataset_name=DATASET_NAME,
                id=old_item.id,
                input=old_item.input,
                status="ARCHIVED",
            )
            print(f"  Archived old item: {old_item.id}")
except Exception:
    pass

# Add/upsert items (deterministic ID from input text)
for i, item in enumerate(ITEMS):
    item_id = hashlib.md5(item["input"]["input"].encode()).hexdigest()
    lf.create_dataset_item(
        dataset_name=DATASET_NAME,
        id=item_id,
        input=item["input"],
        expected_output=item["expected_output"],
    )
    print(f"  Added item {i + 1}/{len(ITEMS)}: {item['input']['input'][:50]}")

lf.flush()
print(f"\nDone! {len(ITEMS)} items added to dataset '{DATASET_NAME}'.")
print("Go to Langfuse > Datasets > customer-support-eval to view and run experiments.")
