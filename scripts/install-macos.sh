#!/bin/bash
set -e

PORT=8000
LABEL="ai.neeopl.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

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

if launchctl list &>/dev/null | grep -q "$LABEL"; then
    echo "Останавливаю старую службу..."
    launchctl unload "$PLIST" 2>/dev/null || true
fi

echo "Создаём службу launchd..."
cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$UV_PATH</string>
        <string>run</string>
        <string>uvicorn</string>
        <string>neeopl.app:create_app</string>
        <string>--factory</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>$PORT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$(dirname "$UV_PATH"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>$HOME</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/data/neeopl-server.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/data/neeopl-server.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST"
sleep 2

if launchctl list | grep -q "$LABEL"; then
    echo ""
    echo "Готово. Служба запущена и добавлена в автозапуск."
    echo "Адрес: http://127.0.0.1:$PORT"
    echo ""
    echo "Управление:"
    echo "  остановить:  launchctl unload $PLIST"
    echo "  запустить:   launchctl load $PLIST"
    echo "  логи:         tail -f $PROJECT_DIR/data/neeopl-server.log"
else
    echo "Ошибка: служба не запустилась. Смотрите лог:"
    echo "  tail -f $PROJECT_DIR/data/neeopl-server.log"
    exit 1
fi