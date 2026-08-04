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

echo "AWS account: $AWS_ACCOUNT_ID"
echo "AWS region:  $AWS_REGION"

# Create ECR repository.
if ! aws ecr describe-repositories \
  --repository-names "$ECR_REPOSITORY" >/dev/null 2>&1
then
  aws ecr create-repository \
    --repository-name "$ECR_REPOSITORY" \
    --image-scanning-configuration scanOnPush=true
fi

# Create private S3 bucket.
if ! aws s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null
then
  aws s3api create-bucket \
    --bucket "$S3_BUCKET" \
    --region "$AWS_REGION" \
    --create-bucket-configuration "LocationConstraint=$AWS_REGION"
fi

aws s3api put-public-access-block \
  --bucket "$S3_BUCKET" \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'

aws s3api put-bucket-encryption \
  --bucket "$S3_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# Create dead-letter queue.
DLQ_URL="$(
  aws sqs get-queue-url \
    --queue-name "$DLQ_NAME" \
    --query QueueUrl \
    --output text 2>/dev/null ||
  aws sqs create-queue \
    --queue-name "$DLQ_NAME" \
    --attributes MessageRetentionPeriod=1209600 \
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

# Create main job queue.
MAIN_QUEUE_URL="$(
  aws sqs get-queue-url \
    --queue-name "$MAIN_QUEUE_NAME" \
    --query QueueUrl \
    --output text 2>/dev/null ||
  aws sqs create-queue \
    --queue-name "$MAIN_QUEUE_NAME" \
    --query QueueUrl \
    --output text
)"

REDRIVE_POLICY="$(
  python3 -c 'import json,sys; print(json.dumps({"deadLetterTargetArn":sys.argv[1],"maxReceiveCount":"3"}))' \
  "$DLQ_ARN"
)"

aws sqs set-queue-attributes \
  --queue-url "$MAIN_QUEUE_URL" \
  --attributes \
    VisibilityTimeout=900,ReceiveMessageWaitTimeSeconds=20,MessageRetentionPeriod=345600,RedrivePolicy="$REDRIVE_POLICY"

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
echo "AWS base resources created successfully:"
cat .aws-bootstrap.env
