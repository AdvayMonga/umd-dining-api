#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAMBDA_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building Lambda layer..."

rm -rf "$LAMBDA_DIR/layer"
mkdir -p "$LAMBDA_DIR/layer/python"

pip install -r "$LAMBDA_DIR/requirements.txt" \
    -t "$LAMBDA_DIR/layer/python/" \
    --platform manylinux2014_x86_64 \
    --only-binary=:all: \
    --quiet

cd "$LAMBDA_DIR/layer"
zip -r "$LAMBDA_DIR/lambda-layer.zip" python/ -q

echo "Layer built: lambda-layer.zip ($(du -h "$LAMBDA_DIR/lambda-layer.zip" | cut -f1))"
