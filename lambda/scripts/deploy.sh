#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAMBDA_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
FUNCTION_NAME="umd-dining-scraper"
ROLE_NAME="umd-dining-scraper-role"
SCHEDULER_ROLE_NAME="umd-dining-scheduler-role"
LAYER_NAME="umd-dining-scraper-layer"
REGION="us-east-1"
RUNTIME="python3.12"

# Read MONGO_URI from project .env file
MONGO_URI=$(grep '^MONGO_URI=' "$LAMBDA_DIR/../.env" | cut -d '=' -f2-)
if [ -z "$MONGO_URI" ]; then
    echo "ERROR: MONGO_URI not found in .env"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
SCHEDULER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${SCHEDULER_ROLE_NAME}"
FUNCTION_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}"

echo "=== UMD Dining Scraper — Lambda Deployment ==="
echo "Account: $ACCOUNT_ID | Region: $REGION"
echo ""

# --- Step 1: IAM Role for Lambda ---
echo "[1/7] Creating Lambda IAM role..."
if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
    echo "  Role exists"
else
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "file://$SCRIPT_DIR/policies/lambda-trust-policy.json" \
        --query 'Role.Arn' --output text
    echo "  Waiting for role propagation..."
    sleep 10
fi

aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name lambda-logs \
    --policy-document "file://$SCRIPT_DIR/policies/lambda-execution-policy.json"

# --- Step 2: Build Lambda Layer ---
echo "[2/7] Building dependency layer..."
"$SCRIPT_DIR/build_layer.sh"

# --- Step 3: Publish Layer ---
echo "[3/7] Publishing layer..."
LAYER_VERSION=$(aws lambda publish-layer-version \
    --layer-name "$LAYER_NAME" \
    --zip-file "fileb://$LAMBDA_DIR/lambda-layer.zip" \
    --compatible-runtimes "$RUNTIME" \
    --region "$REGION" \
    --query 'Version' --output text)
LAYER_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:layer:${LAYER_NAME}:${LAYER_VERSION}"
echo "  Layer v${LAYER_VERSION} published"

# --- Step 4: Package function code ---
echo "[4/7] Packaging function..."
cd "$LAMBDA_DIR"
zip -r function.zip handler.py scraper_core.py -q

# --- Step 5: Create or update Lambda function ---
echo "[5/7] Deploying function..."
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" >/dev/null 2>&1; then
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file "fileb://$LAMBDA_DIR/function.zip" \
        --region "$REGION" \
        --query 'FunctionArn' --output text

    # Wait for update to complete before changing config
    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --runtime "$RUNTIME" \
        --handler handler.lambda_handler \
        --timeout 180 \
        --memory-size 512 \
        --layers "$LAYER_ARN" \
        --environment "Variables={MONGO_URI=$MONGO_URI}" \
        --region "$REGION" \
        --query 'FunctionArn' --output text
else
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime "$RUNTIME" \
        --role "$ROLE_ARN" \
        --handler handler.lambda_handler \
        --zip-file "fileb://$LAMBDA_DIR/function.zip" \
        --timeout 180 \
        --memory-size 512 \
        --layers "$LAYER_ARN" \
        --environment "Variables={MONGO_URI=$MONGO_URI}" \
        --region "$REGION" \
        --query 'FunctionArn' --output text

    # Wait for function to be active
    aws lambda wait function-active --function-name "$FUNCTION_NAME" --region "$REGION"
fi
echo "  Function deployed"

# --- Step 6: EventBridge Scheduler role ---
echo "[6/7] Setting up EventBridge Scheduler..."
if aws iam get-role --role-name "$SCHEDULER_ROLE_NAME" >/dev/null 2>&1; then
    echo "  Scheduler role exists"
else
    aws iam create-role \
        --role-name "$SCHEDULER_ROLE_NAME" \
        --assume-role-policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [{
                \"Effect\": \"Allow\",
                \"Principal\": {\"Service\": \"scheduler.amazonaws.com\"},
                \"Action\": \"sts:AssumeRole\"
            }]
        }" \
        --query 'Role.Arn' --output text
    sleep 10
fi

aws iam put-role-policy \
    --role-name "$SCHEDULER_ROLE_NAME" \
    --policy-name invoke-lambda \
    --policy-document "{
        \"Version\": \"2012-10-17\",
        \"Statement\": [{
            \"Effect\": \"Allow\",
            \"Action\": \"lambda:InvokeFunction\",
            \"Resource\": \"$FUNCTION_ARN\"
        }]
    }"

# --- Step 7: Create schedules (6am and 12pm ET) ---
echo "[7/7] Creating schedules..."

create_schedule() {
    local name="$1"
    local cron="$2"
    local label="$3"

    if aws scheduler get-schedule --name "$name" --region "$REGION" >/dev/null 2>&1; then
        aws scheduler update-schedule \
            --name "$name" \
            --schedule-expression "$cron" \
            --schedule-expression-timezone "America/New_York" \
            --flexible-time-window Mode=OFF \
            --target "{
                \"Arn\": \"$FUNCTION_ARN\",
                \"RoleArn\": \"$SCHEDULER_ROLE_ARN\",
                \"Input\": \"{}\"
            }" \
            --region "$REGION" \
            --query 'ScheduleArn' --output text >/dev/null
        echo "  Updated: $label"
    else
        aws scheduler create-schedule \
            --name "$name" \
            --schedule-expression "$cron" \
            --schedule-expression-timezone "America/New_York" \
            --flexible-time-window Mode=OFF \
            --target "{
                \"Arn\": \"$FUNCTION_ARN\",
                \"RoleArn\": \"$SCHEDULER_ROLE_ARN\",
                \"Input\": \"{}\"
            }" \
            --region "$REGION" \
            --query 'ScheduleArn' --output text >/dev/null
        echo "  Created: $label"
    fi
}

create_schedule "umd-dining-scraper-morning" "cron(0 6 * * ? *)" "6:00 AM ET"
create_schedule "umd-dining-scraper-noon"    "cron(0 12 * * ? *)" "12:00 PM ET"

# --- Test invocation ---
echo ""
echo "Testing Lambda..."
aws lambda invoke \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --payload '{}' \
    --cli-read-timeout 200 \
    /tmp/lambda-response.json >/dev/null

echo "Response:"
cat /tmp/lambda-response.json
echo ""

# Cleanup build artifacts
rm -rf "$LAMBDA_DIR/layer" "$LAMBDA_DIR/lambda-layer.zip" "$LAMBDA_DIR/function.zip"

echo ""
echo "=== Deployment Complete ==="
echo "Function:  $FUNCTION_NAME"
echo "Schedules: 6:00 AM ET, 12:00 PM ET"
echo "Logs:      aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $REGION"
