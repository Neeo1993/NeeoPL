#!/bin/bash
set -e

PORT=8000
SERVICE_NAME="neeopl"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "Папка проекта: $PROJECT_DIR"

if ! command -v uv &>/dev/null; then
    echo "Устанавливаю uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "$HOME/.local/bin/env"
else
    source "$HOME/.local/bin/env" 2>/dev/null || true
fi

UV_PATH="$(command -v uv)"
echo "uv: $UV_PATH"

echo "Устанавливаю зависимости..."
uv sync

mkdir -p "$PROJECT_DIR/data"

SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

if systemctl --user is-active "$SERVICE_NAME" &>/dev/null; then
    echo "Останавливаю старую службу..."
    systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
fi

echo "Создаём службу systemd..."
cat > "$SYSTEMD_DIR/$SERVICE_NAME.service" << EOF
[Unit]
Description=NeeoP&L server
After=network.target

[Service]
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$(dirname "$UV_PATH"):/usr/local/bin:/usr/bin:/bin
Environment=HOME=$HOME
ExecStart=$UV_PATH run uvicorn neeopl.app:create_app --factory --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user start "$SERVICE_NAME"
sleep 2

if command -v loginctl &>/dev/null; then
    loginctl enable-linger "$(whoami)" 2>/dev/null || true
fi

if systemctl --user is-active "$SERVICE_NAME" &>/dev/null; then
    echo ""
    echo "Готово. Служба запущена и добавлена в автозапуск."
    echo "Адрес: http://127.0.0.1:$PORT"
    echo ""
    echo "Управление:"
    echo "  остановить:  systemctl --user stop $SERVICE_NAME"
    echo "  запустить:   systemctl --user start $SERVICE_NAME"
    echo "  статус:       systemctl --user status $SERVICE_NAME"
    echo "  логи:         journalctl --user -u $SERVICE_NAME -f"
else
    echo "Ошибка: служба не запустилась. Смотрите лог:"
    echo "  journalctl --user -u $SERVICE_NAME"
    exit 1
fi