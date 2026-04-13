#!/bin/bash
set -e

BACKUP_DIR="/opt/backups/construction-ai"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Бэкап SQLite
cp /opt/construction-ai-core/data/construction_ai.db \
  "$BACKUP_DIR/db_$DATE.sqlite"

# Бэкап ChromaDB
tar -czf "$BACKUP_DIR/chroma_$DATE.tar.gz" \
  -C /opt/construction-ai-core/data chroma/

# Удалить бэкапы старше 14 дней
find "$BACKUP_DIR" -type f -mtime +14 -delete

echo "Backup completed: $DATE"
