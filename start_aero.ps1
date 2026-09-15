$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = (Get-Command python).Source

Write-Host "AlleenAero starten..."
Write-Host "Repo: $root"
Write-Host "Health: http://127.0.0.1:8091/health"

& $python -m aero.server
