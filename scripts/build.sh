#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${REPO_NAME:-awslegalpoc-streamlit}"

DOCKER_CMD="${DOCKER_CMD:-docker}"
if ! ${DOCKER_CMD} info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    DOCKER_CMD="sudo docker"
  fi
fi

${DOCKER_CMD} build -t "${IMAGE_NAME}:latest" .
