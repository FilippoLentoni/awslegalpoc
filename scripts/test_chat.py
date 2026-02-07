import os
import sys
from pathlib import Path
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.agent import run_agent

PROMPTS = [
    "What's the return policy for laptops?",
    "I bought an iphone 14 last month. I don't like it because it heats up. How do I solve it?",
]


def main() -> None:
    session_id = str(uuid.uuid4())
    actor_id = os.getenv("TEST_ACTOR_ID", "customer_001")

    print(f"Using session_id={session_id} actor_id={actor_id}")
    for prompt in PROMPTS:
        print("\nPROMPT:", prompt)
        try:
            response = run_agent(prompt, session_id=session_id, actor_id=actor_id)
            print("RESPONSE:", response)
        except Exception as exc:
            print("ERROR:", exc)


if __name__ == "__main__":
    main()
