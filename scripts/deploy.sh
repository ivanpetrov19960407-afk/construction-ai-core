#!/bin/bash
set -e

cd /opt/construction-ai-core

echo "=== Pulling latest code ==="
git pull origin main

echo "=== Building containers ==="
docker compose build

echo "=== Restarting services ==="
docker compose down
docker compose up -d

echo "=== Waiting for startup ==="
sleep 15

if curl -sf http://localhost:8000/health > /dev/null; then
  echo "✅ Deploy successful"
else
  echo "❌ Health check failed!"
  docker compose logs --tail=30
  exit 1
fi
