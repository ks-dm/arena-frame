#!/bin/bash
PI_HOST="${1:-pi@frame.local}"

rsync -avz \
    --exclude='content/*' \
    --exclude='state.json' \
    --exclude='__pycache__' \
    $PI_HOST:~/arena-frame/ ./

echo "Pulled from Pi"
