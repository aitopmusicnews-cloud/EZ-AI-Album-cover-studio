#!/usr/bin/env bash
set -euo pipefail

export AWS_PROFILE="${AWS_PROFILE:-ez-ceo}"
export AWS_REGION="${AWS_REGION:-us-west-2}"

AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_REPOSITORY="ez-ai-album-cover"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"
S3_BUCKET="ez-ai-album-cover-prod-${AWS_ACCOUNT_ID}"

MAIN_QUEUE_NAME="ez-ai-cover-jobs"
DLQ_NAME="ez-ai-cover-jobs-dlq"

DLQ_URL="$(
  aws sqs get-queue-url \
    --queue-name "$DLQ_NAME" \
    --query QueueUrl \
    --output text
)"

MAIN_QUEUE_URL="$(
  aws sqs get-queue-url \
    --queue-name "$MAIN_QUEUE_NAME" \
    --query QueueUrl \
    --output text
)"

DLQ_ARN="$(
  aws sqs get-queue-attributes \
    --queue-url "$DLQ_URL" \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' \
    --output text
)"

export DLQ_ARN

python3 - <<'PY'
import json
import os

attributes = {
    "VisibilityTimeout": "900",
    "ReceiveMessageWaitTimeSeconds": "20",
    "MessageRetentionPeriod": "345600",
    "RedrivePolicy": json.dumps(
        {
            "deadLetterTargetArn": os.environ["DLQ_ARN"],
            "maxReceiveCount": "3",
        },
        separators=(",", ":"),
    ),
}

with open("/tmp/ez-ai-sqs-attributes.json", "w", encoding="utf-8") as file:
    json.dump(attributes, file)
PY

aws sqs set-queue-attributes \
  --queue-url "$MAIN_QUEUE_URL" \
  --attributes file:///tmp/ez-ai-sqs-attributes.json

cat > .aws-bootstrap.env <<EOF
AWS_PROFILE=$AWS_PROFILE
AWS_REGION=$AWS_REGION
AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID
ECR_URI=$ECR_URI
S3_BUCKET=$S3_BUCKET
SQS_QUEUE_URL=$MAIN_QUEUE_URL
SQS_DLQ_URL=$DLQ_URL
EOF

echo
echo "AWS resources configured successfully:"
cat .aws-bootstrap.env

echo
echo "Queue settings:"
aws sqs get-queue-attributes \
  --queue-url "$MAIN_QUEUE_URL" \
  --attribute-names \
    QueueArn \
    VisibilityTimeout \
    ReceiveMessageWaitTimeSeconds \
    MessageRetentionPeriod \
    RedrivePolicy
