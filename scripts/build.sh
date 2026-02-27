#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${REPO_NAME:-awslegalpoc-streamlit}"

DOCKER_CMD="${DOCKER_CMD:-docker}"
if ! ${DOCKER_CMD} info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    DOCKER_CMD="sudo docker"
  fi
fi

SHORT_SHA="${GIT_SHA:0:7}"

${DOCKER_CMD} build -t "${IMAGE_NAME}:latest" .
if [[ -n "${SHORT_SHA}" && "${SHORT_SHA}" != "unknown" ]]; then
    ${DOCKER_CMD} tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:${SHORT_SHA}"
fi
