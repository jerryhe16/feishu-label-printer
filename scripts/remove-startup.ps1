$shortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Feishu Label Printer.lnk'
if (Test-Path -LiteralPath $shortcutPath) { Remove-Item -LiteralPath $shortcutPath }
Write-Output 'Startup shortcut removed; a running worker must be stopped separately.'
