param([string]$Config = 'config.local.json')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$configPath = if ([IO.Path]::IsPathRooted($Config)) { $Config } else { Join-Path $projectRoot $Config }
$python = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
Start-Process -FilePath $python -ArgumentList ('-m feishu_label_printer --config "' + $configPath + '" run') -WorkingDirectory $projectRoot -WindowStyle Hidden
