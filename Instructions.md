# awslegalpoc — Codex Implementation Spec (ECS + ALB + Cognito)

Goal
Build a portable, git-pushable project that lets any developer deploy a Streamlit chatbot (AgentCore + Strands + RAG) into THEIR OWN AWS account using IaC. Local Dev happens on EC2; production deploy is containerized on ECS Fargate behind an ALB with Cognito authentication. Observability via Langfuse with UI thumbs up/down feedback.

- Public internet-facing (≈10 users).
- Keep costs low
- No notebooks in the final app: convert notebook logic into Python modules.
- Secrets never committed: use `.env` and/or AWS Secrets Manager for deployed secrets.

------------------------------------------------------------
0) Repo structure (create)
- app/                    # Streamlit UI
- core/                   # agent logic, RAG, bedrock/agentcore wrappers, langfuse wrapper
- infra/                  # AWS CDK (Python) to deploy ECR, ECS Fargate, ALB, Cognito
- scripts/                # build/push/deploy/destroy helpers
- resources/              # gitignored external references (already cloned locally)
- .env.example            # template only (no secrets)
- pyproject.toml, poetry.lock

------------------------------------------------------------
1) Local Python environment (Poetry)
- Use Poetry for dependency management; commit `pyproject.toml` and `poetry.lock`.
- Provide optional Jupyter kernel setup:
  - `poetry run python -m ipykernel install --user --name awslegalpoc`
this environment is needed for local dev only
------------------------------------------------------------
2) Config & secrets
- Use `.env` for local secrets. Commit `.env.example` only.
- Add `.gitignore` entries for:
  - `.env`, `*.pem`, `resources/`, `.venv/`, `__pycache__/`, `.streamlit/`
- For deployed stack:
  - store Langfuse keys and any API secrets in AWS Secrets Manager (preferred)
  - do not hardcode secrets in CDK or source code

------------------------------------------------------------
3) Streamlit app requirements
Implement Streamlit UI in `app/main.py`:
- Chat input + chat history
- Display assistant responses
- Thumbs 👍/👎 on the latest assistant message


------------------------------------------------------------
4) Agent implementation (AgentCore + Strands + RAG)
Implement agent logic based on the notebooks in #1, but as Python modules (no notebooks):

References (#1):
/home/ec2-user/awslegalpoc/resources/amazon-bedrock-agentcore-samples/01-tutorials/09-AgentCore-E2E/lab-01-create-an-agent.ipynb
/home/ec2-user/awslegalpoc/resources/amazon-bedrock-agentcore-samples/01-tutorials/09-AgentCore-E2E/lab-02-agentcore-memory.ipynb
/home/ec2-user/awslegalpoc/resources/amazon-bedrock-agentcore-samples/01-tutorials/09-AgentCore-E2E/lab-03-agentcore-gateway.ipynb
/home/ec2-user/awslegalpoc/resources/amazon-bedrock-agentcore-samples/01-tutorials/09-AgentCore-E2E/lab-04-agentcore-runtime.ipynb
/home/ec2-user/awslegalpoc/resources/amazon-bedrock-agentcore-samples/01-tutorials/09-AgentCore-E2E/lab-06-frontend.ipynb

------------------------------------------------------------
5) Langfuse integration + thumbs feedback

References (#2):
/home/ec2-user/awslegalpoc/resources/amazon-bedrock-agentcore-samples/01-tutorials/06-AgentCore-observability/04-Agentcore-runtime-partner-observability/Langfuse/requirements.txt
/home/ec2-user/awslegalpoc/resources/amazon-bedrock-agentcore-samples/01-tutorials/06-AgentCore-observability/04-Agentcore-runtime-partner-observability/Langfuse/runtime_with_strands_and_langfuse.ipynb

Reference (#3):
resources/langfuse (gitignored)

------------------------------------------------------------
6) Containerization
Provide Dockerfile for Streamlit:
- Expose port 8501
- Runs `streamlit run app/main.py --server.port=8501 --server.address=0.0.0.0`
Provide scripts:
- `scripts/build.sh` build image
- `scripts/push.sh` push to ECR
- `scripts/run_local.sh` run locally (optional)

------------------------------------------------------------
7) AWS deployment (CDK in Python)
Implement `infra/` CDK app that deploys:

A) ECR repository
- `awslegalpoc-streamlit` repo

B) ECS Fargate service (public)
- 1 task (min 1, max 2 for now)
- Task role with least privileges to call Bedrock/AgentCore and read Secrets Manager
- Place tasks in PUBLIC subnets to avoid NAT Gateway costs
- Security group allows inbound from ALB only

C) Application Load Balancer (ALB)
- Public ALB
- Listener 443 (HTTPS) with ACM certificate
- Optional HTTP 80 redirect to HTTPS

D) Cognito authentication at ALB
- Cognito User Pool + App Client + Domain
- ALB listener rule: authenticate via Cognito then forward to target group

E) Outputs
- ALB HTTPS URL
- Cognito user pool info (for admin)
- ECS service name
- ECR repo URI

No API Gateway and no Lambda for v1.

------------------------------------------------------------
8) Developer workflow (README + scripts)
Provide:
- `./scripts/deploy.sh`:
  1) `cd infra && cdk bootstrap` if needed
  2) build docker image
  3) push to ECR
  4) `cd infra && cdk deploy`
- `./scripts/destroy.sh`: `cd infra && cdk destroy`

------------------------------------------------------------
9) Required env vars (.env.example)
Local:
- AWS_REGION=
- BEDROCK_REGION=
- LANGFUSE_PUBLIC_KEY=
- LANGFUSE_SECRET_KEY=
- LANGFUSE_HOST= (default https://cloud.langfuse.com)

Deployed:
- Use Secrets Manager or ECS env vars populated by CDK.

Done criteria
- Local run works: `poetry run streamlit run app/main.py`
- Deployment works: `deploy.sh` outputs an HTTPS URL
- Visiting URL requires Cognito login
- Chat works and invokes AgentCore
- Langfuse shows traces for each message
- Thumbs 👍/👎 create Langfuse scores and show in langfuse
