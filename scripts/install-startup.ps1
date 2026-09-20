param([string]$Config = 'config.local.json')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$configPath = if ([IO.Path]::IsPathRooted($Config)) { $Config } else { Join-Path $projectRoot $Config }
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Create config.local.json first' }
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Feishu Label Printer.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = '-m feishu_label_printer --config "' + $configPath + '" run'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.WindowStyle = 7
$shortcut.Description = 'Feishu Base label queue worker'
$shortcut.Save()
Write-Output "Installed user-login startup: $shortcutPath"
