#!/bin/bash
set -e

# Выкатка dev -> prod.
# Копирует код из этого репозитория в продуктивный каталог, пересобирает
# окружение и перезапускает launchd-службу. Данные (data/) не трогаются.

PROD_DIR="${NEEOPL_PROD_DIR:-$HOME/Apps/neeopl}"
PORT=24898
LABEL="ai.neeopl.server"

DEV_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$DEV_DIR" = "$PROD_DIR" ]; then
    echo "Ошибка: запущено из продуктивного каталога. Выкатывать нужно из dev-репозитория."
    exit 1
fi

echo "dev:  $DEV_DIR"
echo "prod: $PROD_DIR"
echo ""

mkdir -p "$PROD_DIR"

echo "Копирую код..."
# --delete убирает из prod файлы, удалённые в dev.
# Исключённые каталоги (data, .venv) при этом не затрагиваются.
rsync -a --delete \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude 'data/' \
    --exclude '.ruff_cache/' \
    --exclude '__pycache__/' \
    --exclude '.DS_Store' \
    "$DEV_DIR/" "$PROD_DIR/"

# macOS помечает файлы в ~/Documents флагом hidden; Python (3.13+) молча
# игнорирует скрытые .pth-файлы, из-за чего пакет перестаёт импортироваться.
chflags -R nohidden "$PROD_DIR" 2>/dev/null || true

echo "Переустанавливаю службу..."
"$PROD_DIR/scripts/install-macos.sh"

echo ""
echo "Проверяю доступность..."
for i in $(seq 1 15); do
    CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/login" || true)"
    if [ "$CODE" = "200" ]; then
        echo "Готово. Сервер отвечает: http://127.0.0.1:$PORT"
        exit 0
    fi
    sleep 1
done

echo "Ошибка: сервер не отвечает (последний код: ${CODE:-нет ответа})."
echo "Логи: tail -f $PROD_DIR/data/neeopl-server.log"
exit 1
