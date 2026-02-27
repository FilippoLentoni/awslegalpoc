"""Generate config/secrets.json from environment variables.

Used by CodeBuild to bridge Secrets Manager values (injected as env vars)
into the config/secrets.json format that deploy-all.sh expects.
"""

import json
import os
from pathlib import Path


def main() -> None:
    env = os.getenv("DEPLOY_ENV", "beta")
    cognito_password = os.getenv("COGNITO_PASSWORD", "")
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

    if not cognito_password:
        print("Warning: COGNITO_PASSWORD not set, secrets.json will have empty password")

    secrets = {
        env: {
            "cognito": {
                "password": cognito_password,
            },
            "langfuse": {
                "publicKey": langfuse_public_key,
                "secretKey": langfuse_secret_key,
            },
        }
    }

    secrets_path = Path(__file__).parent.parent / "config" / "secrets.json"
    secrets_path.write_text(json.dumps(secrets, indent=2))
    print(f"Generated {secrets_path} for environment '{env}'")


if __name__ == "__main__":
    main()
