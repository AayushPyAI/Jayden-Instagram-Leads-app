#!/usr/bin/env bash
# Build linux/amd64 image, push to ECR, roll the production ECS service.
# Prereqs: Docker running, AWS CLI credentials (same account as ECR/ECS), region us-east-1 unless overridden.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${AWS_DEFAULT_REGION:=us-east-1}"
export AWS_DEFAULT_REGION

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/instagram-leads-api"
CLUSTER="${ECS_CLUSTER:-production}"
SERVICE="${ECS_SERVICE:-YOUR_ECS_SERVICE}"
TAG="${IMAGE_TAG:-latest}"

aws ecr get-login-password --region "${AWS_DEFAULT_REGION}" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com"

docker build --platform linux/amd64 -t "${ECR_URI}:${TAG}" .
docker push "${ECR_URI}:${TAG}"

TASK_FAMILY="${ECS_TASK_FAMILY:-instagram-leads-prod}"
if [ -f "${ROOT}/deploy/ecs-register-input.json" ]; then
  aws ecs register-task-definition --cli-input-json "file://${ROOT}/deploy/ecs-register-input.json" --region "${AWS_DEFAULT_REGION}" >/dev/null
fi
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${SERVICE}" \
  --task-definition "${TASK_FAMILY}" \
  --force-new-deployment \
  --region "${AWS_DEFAULT_REGION}" >/dev/null
echo "Rollout triggered for ${CLUSTER}/${SERVICE} (${ECR_URI}:${TAG}, task ${TASK_FAMILY})."
