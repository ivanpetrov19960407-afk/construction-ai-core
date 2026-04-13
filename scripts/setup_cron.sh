#!/bin/bash

# Добавляет cron-задачи на сервер
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/construction-ai-core/scripts/backup.sh") | crontab -
(crontab -l 2>/dev/null; echo "0 4 1,15 * * certbot renew --quiet") | crontab -

echo "Cron jobs installed"
