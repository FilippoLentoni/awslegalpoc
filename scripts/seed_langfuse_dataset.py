"""Seed an evaluation dataset into Langfuse for prompt experiments.

Usage:
    set -a && source .env && set +a && python3.11 scripts/seed_langfuse_dataset.py
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.langfuse_client import get_langfuse_client

DATASET_NAME = "customer-support-eval"

ITEMS = [
    {
        "input": {"input": "What can you do?"},
        "expected_output": "The assistant should list its capabilities: product info, technical support, warranty/returns, and web search.",
    },
    {
        "input": {"input": "What is the return policy for Dell laptops?"},
        "expected_output": "The assistant should use the get_return_policy tool and provide accurate return window and conditions for Dell laptops.",
    },
    {
        "input": {"input": "I need help troubleshooting my HP printer - it won't connect to WiFi"},
        "expected_output": "The assistant should use get_technical_support to provide step-by-step WiFi troubleshooting for HP printers.",
    },
    {
        "input": {"input": "Tell me about the Samsung Galaxy S24"},
        "expected_output": "The assistant should use get_product_info to retrieve and present Samsung Galaxy S24 specifications.",
    },
    {
        "input": {"input": "Is my warranty still valid? Serial number: ABC123456"},
        "expected_output": "The assistant should attempt to check warranty status using the provided serial number.",
    },
    {
        "input": {"input": "How do I set up my new Sony headphones?"},
        "expected_output": "The assistant should use get_technical_support to provide setup instructions for Sony headphones.",
    },
    {
        "input": {"input": "Can I return a product after 60 days?"},
        "expected_output": "The assistant should use get_return_policy and clearly state whether a 60-day return is possible.",
    },
    {
        "input": {"input": "What are the specs of the MacBook Pro M3?"},
        "expected_output": "The assistant should use get_product_info to retrieve MacBook Pro M3 specifications.",
    },
    {
        "input": {"input": "My laptop battery drains too fast, what should I do?"},
        "expected_output": "The assistant should use get_technical_support to provide battery optimization tips and troubleshooting steps.",
    },
    {
        "input": {"input": "Hello!"},
        "expected_output": "The assistant should greet the customer warmly and offer to help with electronics questions.",
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

# Add items
for i, item in enumerate(ITEMS):
    lf.create_dataset_item(
        dataset_name=DATASET_NAME,
        input=item["input"],
        expected_output=item["expected_output"],
    )
    print(f"  Added item {i + 1}/{len(ITEMS)}: {item['input']['input'][:50]}")

lf.flush()
print(f"\nDone! {len(ITEMS)} items added to dataset '{DATASET_NAME}'.")
print("Go to Langfuse > Datasets > customer-support-eval to view and run experiments.")
