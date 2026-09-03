$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path (Split-Path -Parent $ProjectDirectory) ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "未找到项目 Python：$Python"
}

Set-Location -LiteralPath $ProjectDirectory
Write-Host "正在启动 HYSYS AI 对话界面…"
& $Python ".\chat_app.py" @args

