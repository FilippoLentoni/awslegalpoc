import argparse
import os
import time

import boto3
from bedrock_agentcore.memory import MemoryClient


def _region() -> str:
    return (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or boto3.session.Session().region_name
    )


def _get_ssm_parameter(name: str) -> str:
    ssm = boto3.client("ssm", region_name=_region())
    return ssm.get_parameter(Name=name, WithDecryption=False)["Parameter"]["Value"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-id")
    parser.add_argument("--actor-id", default="customer_001")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    memory_id = args.memory_id or _get_ssm_parameter(
        "/app/customersupport/agentcore/memory_id"
    )

    previous_interactions = [
        (
            "I'm having issues with my MacBook Pro overheating during video editing.",
            "USER",
        ),
        (
            "I can help with that thermal issue. For video editing workloads, let's check your Activity Monitor and adjust performance settings. Your MacBook Pro order #MB-78432 is still under warranty.",
            "ASSISTANT",
        ),
        (
            "What's the return policy on gaming headphones? I need low latency for competitive FPS games",
            "USER",
        ),
        (
            "For gaming headphones, you have 30 days to return. Since you're into competitive FPS, I'd recommend checking the audio latency specs - most gaming models have <40ms latency.",
            "ASSISTANT",
        ),
        (
            "I need a laptop under $1200 for programming. Prefer 16GB RAM minimum and good Linux compatibility. I like ThinkPad models.",
            "USER",
        ),
        (
            "Perfect! For development work, I'd suggest looking at our ThinkPad E series or Dell XPS models. Both have excellent Linux support and 16GB RAM options within your budget.",
            "ASSISTANT",
        ),
    ]

    memory_client = MemoryClient(region_name=_region())
    memory_client.create_event(
        memory_id=memory_id,
        actor_id=args.actor_id,
        session_id="previous_session",
        messages=previous_interactions,
    )

    print("✅ Seeded customer history successfully")

    if args.wait:
        print("🔍 Checking for processed Long-Term Memories...")
        retries = 0
        max_retries = 6

        while retries < max_retries:
            memories = memory_client.retrieve_memories(
                memory_id=memory_id,
                namespace=f"support/customer/{args.actor_id}/preferences/",
                query="can you summarize the support issue",
            )

            if memories:
                print(
                    f"✅ Found {len(memories)} preference memories after {retries * 10} seconds!"
                )
                break

            retries += 1
            if retries < max_retries:
                print(
                    f"⏳ Still processing... waiting 10 more seconds (attempt {retries}/{max_retries})"
                )
                time.sleep(10)
            else:
                print(
                    "⚠️ Memory processing is taking longer than expected. This can happen with overloading.."
                )
                break

        if memories:
            print("🎯 Extracted customer preferences:")
            for i, memory in enumerate(memories, 1):
                content = memory.get("content", {}) if isinstance(memory, dict) else {}
                text = content.get("text", "") if isinstance(content, dict) else ""
                if text:
                    print(f"  {i}. {text}")


if __name__ == "__main__":
    main()
