$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path (Split-Path -Parent $ProjectDirectory) ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "未找到项目 Python：$Python"
}

Set-Location -LiteralPath $ProjectDirectory
& $Python ".\chat_app.py" @args
