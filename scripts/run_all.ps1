# Rawy: migration + test (onaysız sıra)
# Kullanım: rawy klasöründe  .\scripts\run_all.ps1
# Sadece test:  $env:SKIP_ALEMBIC='1'; .\scripts\run_all.ps1

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

if ($env:SKIP_ALEMBIC -eq '1') {
    Write-Host '[run_all] SKIP_ALEMBIC=1 -> migration atlandi'
} else {
    Write-Host '[run_all] alembic upgrade head ...'
    python -m alembic upgrade head
}

Write-Host '[run_all] pytest ...'
python -m pytest tests/ -v --tb=short
Write-Host '[run_all] tamam.'
