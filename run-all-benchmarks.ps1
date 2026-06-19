#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Executa todos os benchmarks (Azure, Databricks, Fabric) em sequência e consolida resultados.

.DESCRIPTION
    Script helper que automatiza a execução de todos os testes de benchmark:
    1. Verifica pré-requisitos
    2. Executa benchmark Azure (08-run-benchmark.py)
    3. Executa benchmark Databricks (10-run-benchmark-databricks.py)
    4. Executa benchmark Fabric (11-run-benchmark-fabric.py)
    5. Consolida resultados (12-compare-all-platforms.py)
    6. Abre relatório final

.PARAMETER OnlyAzure
    Executar apenas benchmark Azure (padrão: $false)

.PARAMETER OnlyDatabricks
    Executar apenas benchmark Databricks (padrão: $false)

.PARAMETER OnlyFabric
    Executar apenas benchmark Fabric (padrão: $false)

.PARAMETER SkipConsolidate
    Pular consolidação final (padrão: $false)

.PARAMETER ShowReport
    Abrir relatório após conclusão (padrão: $true)

.EXAMPLE
    .\run-all-benchmarks.ps1
    # Executa todos os benchmarks e consolida

.EXAMPLE
    .\run-all-benchmarks.ps1 -OnlyAzure
    # Executa apenas Azure

.EXAMPLE
    .\run-all-benchmarks.ps1 -OnlyDatabricks -ShowReport:$false
    # Executa apenas Databricks, sem abrir relatório
#>

param(
    [switch]$OnlyAzure,
    [switch]$OnlyDatabricks,
    [switch]$OnlyFabric,
    [switch]$SkipConsolidate,
    [switch]$ShowReport = $true
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Write-Header {
    param([string]$Text)
    Write-Host "`n$('=' * 80)" -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host "$('=' * 80)`n" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Text)
    Write-Host "✓ $Text" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Text)
    Write-Host "⚠ $Text" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Text)
    Write-Host "✗ $Text" -ForegroundColor Red
}

function Check-Prerequisites {
    Write-Host "`n📋 Verificando pré-requisitos..." -ForegroundColor Magenta
    
    # Verificar Python
    try {
        $pythonVersion = python --version 2>$1 | Out-String
        Write-Success "Python encontrado: $pythonVersion"
    }
    catch {
        Write-Error "Python não encontrado! Execute: pip install -r requirements.txt"
        exit 1
    }
    
    # Verificar .env
    if (-not (Test-Path ".env")) {
        Write-Warning ".env não encontrado"
        Write-Host "  1. Copie .env.example para .env"
        Write-Host "  2. Preencha as variáveis de ambiente"
        Write-Host "  3. Execute novamente este script`n"
        
        if (-not $OnlyAzure) {
            exit 1
        }
    }
    else {
        Write-Success ".env encontrado"
    }
    
    # Verificar dados
    if (-not (Test-Path "data/queries.json")) {
        Write-Warning "Arquivo de queries não encontrado"
        Write-Host "  Gerando dados com: python scripts/02-generate-data.py`n"
        python scripts/02-generate-data.py
    }
    else {
        Write-Success "Dados de teste encontrados"
    }
    
    Write-Success "Pré-requisitos OK`n"
}

function Run-AzureBenchmark {
    Write-Header "BENCHMARK AZURE (08-run-benchmark.py)"
    
    try {
        python scripts/08-run-benchmark.py
        Write-Success "Azure benchmark concluído"
        return $true
    }
    catch {
        Write-Error "Erro ao executar Azure benchmark: $_"
        return $false
    }
}

function Run-DatabricksBenchmark {
    Write-Header "BENCHMARK DATABRICKS (10-run-benchmark-databricks.py)"
    
    # Verificar configuração
    if (-not ($env:DATABRICKS_TOKEN -and $env:DATABRICKS_HOST)) {
        Write-Warning "DATABRICKS_TOKEN ou DATABRICKS_HOST não configurados"
        Write-Host "  Configure em .env e tente novamente`n"
        return $false
    }
    
    try {
        python scripts/10-run-benchmark-databricks.py
        Write-Success "Databricks benchmark concluído"
        return $true
    }
    catch {
        Write-Error "Erro ao executar Databricks benchmark: $_"
        return $false
    }
}

function Run-FabricBenchmark {
    Write-Header "BENCHMARK MICROSOFT FABRIC (11-run-benchmark-fabric.py)"
    
    # Verificar configuração
    if (-not ($env:FABRIC_WORKSPACE_ID -and $env:FABRIC_SQL_ENDPOINT)) {
        Write-Warning "FABRIC_WORKSPACE_ID ou FABRIC_SQL_ENDPOINT não configurados"
        Write-Host "  Configure em .env e tente novamente`n"
        return $false
    }
    
    try {
        python scripts/11-run-benchmark-fabric.py
        Write-Success "Fabric benchmark concluído"
        return $true
    }
    catch {
        Write-Error "Erro ao executar Fabric benchmark: $_"
        return $false
    }
}

function Run-Consolidate {
    Write-Header "CONSOLIDAÇÃO DE RESULTADOS (12-compare-all-platforms.py)"
    
    try {
        python scripts/12-compare-all-platforms.py
        Write-Success "Resultados consolidados"
        return $true
    }
    catch {
        Write-Error "Erro ao consolidar resultados: $_"
        return $false
    }
}

function Open-Report {
    # Encontrar relatório mais recente
    $latestReport = Get-ChildItem "results/REPORT_*.md" -ErrorAction SilentlyContinue | 
                    Sort-Object LastWriteTime -Descending | 
                    Select-Object -First 1
    
    if ($latestReport) {
        Write-Host "📖 Abrindo relatório: $($latestReport.Name)`n" -ForegroundColor Cyan
        
        # Tentar abrir com VS Code (melhor experiência)
        if (Get-Command code -ErrorAction SilentlyContinue) {
            code $latestReport.FullName
        }
        # Fallback para notepad
        elseif ($IsWindows) {
            notepad $latestReport.FullName
        }
        # Fallback para less/more
        else {
            Get-Content $latestReport.FullName | less
        }
    }
    else {
        Write-Warning "Nenhum relatório encontrado"
    }
}

# ============================================================================
# MAIN
# ============================================================================

Write-Header "BENCHMARK VECTOR SEARCH — EXECUTOR AUTOMÁTICO"
Write-Host "Inicialização: $timestamp`n"

# Resolver modo de execução
$modes = @()
if ($OnlyAzure -or (-not $OnlyDatabricks -and -not $OnlyFabric)) { $modes += "Azure" }
if ($OnlyDatabricks -or (-not $OnlyAzure -and -not $OnlyFabric)) { $modes += "Databricks" }
if ($OnlyFabric -or (-not $OnlyAzure -and -not $OnlyDatabricks)) { $modes += "Fabric" }

Write-Host "Plataformas a executar: $($modes -join ', ')`n"

# Verificar pré-requisitos
Check-Prerequisites

# Executar benchmarks
$results = @{}

if ($OnlyAzure -or (-not $OnlyDatabricks -and -not $OnlyFabric)) {
    $results["Azure"] = Run-AzureBenchmark
}

if ($OnlyDatabricks -or (-not $OnlyAzure -and -not $OnlyFabric)) {
    $results["Databricks"] = Run-DatabricksBenchmark
}

if ($OnlyFabric -or (-not $OnlyAzure -and -not $OnlyDatabricks)) {
    $results["Fabric"] = Run-FabricBenchmark
}

# Consolidar se houver múltiplas plataformas
$completedCount = $results.Values | Where-Object { $_ -eq $true } | Measure-Object | Select-Object -ExpandProperty Count

if ($completedCount -gt 1 -and -not $SkipConsolidate) {
    Run-Consolidate
}

# Resumo final
Write-Header "RESUMO FINAL"

$completedPlatforms = @()
$failedPlatforms = @()

foreach ($platform in $results.Keys) {
    if ($results[$platform]) {
        $completedPlatforms += $platform
        Write-Success "$platform benchmark completado"
    }
    else {
        $failedPlatforms += $platform
        Write-Error "$platform benchmark falhou"
    }
}

if ($failedPlatforms.Count -eq 0) {
    Write-Host "`n✅ Todos os benchmarks completados com sucesso!`n" -ForegroundColor Green
}
else {
    Write-Host "`n⚠ Alguns benchmarks falharam: $($failedPlatforms -join ', ')`n" -ForegroundColor Yellow
}

# Exibir estatísticas
Write-Host "📊 Resultados salvos em: $(Resolve-Path 'results')`n"

# Listar arquivos gerados
$jsonFiles = @(Get-ChildItem "results/benchmark_*.json" -ErrorAction SilentlyContinue)
$csvFiles = @(Get-ChildItem "results/consolidated_results_*.csv" -ErrorAction SilentlyContinue)
$reportFiles = @(Get-ChildItem "results/REPORT_*.md" -ErrorAction SilentlyContinue)

if ($jsonFiles.Count -gt 0) {
    Write-Host "  📄 Arquivos JSON: $($jsonFiles.Count)"
    $jsonFiles | ForEach-Object { Write-Host "     - $($_.Name)" }
}

if ($csvFiles.Count -gt 0) {
    Write-Host "  📊 Arquivos CSV: $($csvFiles.Count)"
    $csvFiles | ForEach-Object { Write-Host "     - $($_.Name)" }
}

if ($reportFiles.Count -gt 0) {
    Write-Host "  📖 Relatórios Markdown: $($reportFiles.Count)"
    $reportFiles | ForEach-Object { Write-Host "     - $($_.Name)" }
}

Write-Host ""

# Abrir relatório se solicitado
if ($ShowReport -and $reportFiles.Count -gt 0) {
    Open-Report
}

Write-Host "✅ Execução finalizada em $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n" -ForegroundColor Green
