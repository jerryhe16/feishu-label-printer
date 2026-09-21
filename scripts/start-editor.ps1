param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw '请先按README创建.venv并安装项目依赖。' }
$config = if (Test-Path -LiteralPath (Join-Path $projectRoot 'config.local.json')) { 'config.local.json' } else { 'config.example.json' }
$arguments = '-m feishu_label_printer --config "' + $config + '" editor --port ' + $Port
Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden
