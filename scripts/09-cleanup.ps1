# ============================================================
# 09-cleanup.ps1
# Remove todos os recursos do benchmark
# ============================================================

$ErrorActionPreference = "Stop"

$RG = "rg-vector-benchmark-brazilsouth"

Write-Host "============================================" -ForegroundColor Red
Write-Host " ATENÇÃO: Removendo todos os recursos!" -ForegroundColor Red
Write-Host " Resource Group: $RG" -ForegroundColor Red
Write-Host "============================================" -ForegroundColor Red
Write-Host ""

$confirm = Read-Host "Tem certeza que deseja remover TODOS os recursos? (sim/nao)"
if ($confirm -ne "sim") {
    Write-Host "Operação cancelada." -ForegroundColor Yellow
    exit 0
}

Write-Host "`nRemovendo Resource Group '$RG' e todos os recursos..." -ForegroundColor Yellow
az group delete --name $RG --yes --no-wait

Write-Host "`n✓ Exclusão iniciada (executa em background no Azure)." -ForegroundColor Green
Write-Host "  Use 'az group show --name $RG' para verificar status." -ForegroundColor Gray

# Limpar arquivos locais
$configFile = "$PSScriptRoot\..\config.json"
if (Test-Path $configFile) {
    Remove-Item $configFile
    Write-Host "  ✓ config.json removido" -ForegroundColor Gray
}

Write-Host "`n✅ Cleanup concluído!" -ForegroundColor Green
