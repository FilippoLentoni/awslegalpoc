#!/usr/bin/env python3
"""Seed a small (2-case) evaluation dataset into Langfuse for CI pipeline runs.

Usage:
    set -a && source .env && set +a
    python3.11 scripts/seed_eval_ci_dataset.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.langfuse_client import get_langfuse_client

DATASET_NAME = "italian-legal-eval-ci"

# Two representative test cases for quick CI validation
CI_ITEMS = [
    {
        "input": {"input": "Quali sono le differenze tra debito di valuta e debito di valore?"},
        "expected_output": (
            "Il debito di valuta ha ad oggetto una somma di denaro determinata fin dall'origine "
            "ed è soggetto al principio nominalistico (art. 1277 c.c.): il debitore si libera "
            "pagando la somma nominale, indipendentemente dalle variazioni del potere d'acquisto. "
            "Il debito di valore ha invece ad oggetto un valore reale (es. risarcimento del danno) "
            "che deve essere tradotto in denaro solo al momento della liquidazione. "
            "Fino alla liquidazione il debito di valore non è soggetto al principio nominalistico; "
            "una volta liquidato si converte in debito di valuta."
        ),
        "metadata": {"domain": "Le obbligazioni", "tipologia": "Media"},
    },
    {
        "input": {"input": "Che cos'è la remissione del debito?"},
        "expected_output": (
            "La remissione del debito è un negozio giuridico unilaterale recettizio (artt. 1236-1240 c.c.) "
            "con cui il creditore rinuncia al proprio diritto di credito, determinando l'estinzione "
            "dell'obbligazione. La dichiarazione di remissione produce effetto quando giunge a "
            "conoscenza del debitore, il quale può opporsi entro un termine congruo. "
            "La remissione estingue anche le garanzie e i privilegi che assistono il credito."
        ),
        "metadata": {"domain": "Le obbligazioni", "tipologia": "Facile"},
    },
]


def main():
    lf = get_langfuse_client()
    if not lf:
        print("ERROR: Langfuse client not configured.")
        sys.exit(1)

    # Create dataset
    try:
        lf.create_dataset(
            name=DATASET_NAME,
            description="Small CI evaluation dataset (2 cases) for pipeline validation",
        )
        print(f"Created dataset '{DATASET_NAME}'")
    except Exception:
        print(f"Dataset '{DATASET_NAME}' already exists, updating items...")

    # Add items
    for i, item in enumerate(CI_ITEMS):
        lf.create_dataset_item(
            dataset_name=DATASET_NAME,
            input=item["input"],
            expected_output=item["expected_output"],
            metadata=item["metadata"],
        )
        print(f"  [{i + 1}/{len(CI_ITEMS)}] {item['input']['input'][:60]}")

    lf.flush()
    print(f"\nDone! {len(CI_ITEMS)} items added to dataset '{DATASET_NAME}'.")


if __name__ == "__main__":
    main()
