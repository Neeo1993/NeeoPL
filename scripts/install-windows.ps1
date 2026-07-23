$ErrorActionPreference = "Stop"
$Port = 8000
$TaskName = "NeeoPL"

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectDir
Write-Host "Папка проекта: $ProjectDir"

$UvCmd = Get-Command uv -ErrorAction SilentlyContinue
if (-not $UvCmd) {
    Write-Host "Устанавливаю uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $UvCmd = Get-Command uv -ErrorAction SilentlyContinue
}

if (-not $UvCmd) {
    Write-Host "Ошибка: uv не установлен. Добавьте его в PATH и запустите скрипт снова."
    exit 1
}

$UvPath = $UvCmd.Source
Write-Host "uv: $UvPath"

Write-Host "Устанавливаю зависимости..."
& uv sync

$DataDir = Join-Path $ProjectDir "data"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir | Out-Null
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Останавливаю старую задачу..."
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Write-Host "Создаю задачу в планировщике..."

$Action = New-ScheduledTaskAction `
    -Execute $UvPath `
    -Argument "run uvicorn neeopl.app:create_app --factory --host 127.0.0.1 --port $Port" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

$task = Get-ScheduledTask -TaskName $TaskName
if ($task.State -eq "Running" -or $task.State -eq "Ready") {
    Write-Host ""
    Write-Host "Готово. Задача запущена и добавлена в автозапуск."
    Write-Host "Адрес: http://127.0.0.1:$Port"
    Write-Host ""
    Write-Host "Управление:"
    Write-Host "  остановить:  Stop-ScheduledTask -TaskName $TaskName"
    Write-Host "  запустить:   Start-ScheduledTask -TaskName $TaskName"
    Write-Host "  удалить:      Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
} else {
    Write-Host "Ошибка: задача не запустилась. Проверьте состояние:"
    Write-Host "  Get-ScheduledTask -TaskName $TaskName"
    exit 1
}