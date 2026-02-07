#!/usr/bin/env bash
set -euo pipefail

/home/ec2-user/.local/bin/poetry run streamlit run app/main.py --server.port=8501 --server.address=0.0.0.0
