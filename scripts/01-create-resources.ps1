# ============================================================
# 01-create-resources.ps1
# Provisiona todos os recursos Azure para o benchmark vetorial
# Região: Brazil South
# ============================================================

$ErrorActionPreference = "Stop"

# --- VARIÁVEIS (edite conforme necessário) ---
$SUBSCRIPTION    = (az account show --query id -o tsv)
$LOCATION        = "brazilsouth"
$RG              = "rg-vector-benchmark-brazilsouth"
$AI_SEARCH_NAME  = "srch-vectorbench-brs"
$COSMOS_NAME     = "cosmos-vectorbench-brs"
$PG_NAME         = "pg-vectorbench-brs"
$SQL_SERVER_NAME = "sql-vectorbench-brs"
$SQL_DB_NAME     = "vectorbenchdb"
$ADMIN_USER      = "vecadmin"
$ADMIN_PASSWORD  = $env:SQL_ADMIN_PASSWORD  # Set via environment variable before running: $env:SQL_ADMIN_PASSWORD = "YourPassword"
# Nota: SQL Server com Entra-only auth será configurado via 01b-configure-entra-auth.ps1

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Azure Vector Storage Benchmark - Setup" -ForegroundColor Cyan
Write-Host " Região: $LOCATION" -ForegroundColor Cyan
Write-Host " Subscription: $SUBSCRIPTION" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# --- 1. Resource Group ---
Write-Host "`n[1/5] Criando Resource Group..." -ForegroundColor Yellow
az group create --name $RG --location $LOCATION --output none
Write-Host "  ✓ Resource Group: $RG" -ForegroundColor Green

# --- 2. Azure AI Search (Basic SKU) ---
Write-Host "`n[2/5] Criando Azure AI Search (Basic)..." -ForegroundColor Yellow
az search service create `
    --name $AI_SEARCH_NAME `
    --resource-group $RG `
    --location $LOCATION `
    --sku basic `
    --partition-count 1 `
    --replica-count 1 `
    --output none
Write-Host "  ✓ AI Search: $AI_SEARCH_NAME" -ForegroundColor Green

# --- 3. Azure Cosmos DB (NoSQL, Serverless) ---
Write-Host "`n[3/5] Criando Azure Cosmos DB (NoSQL, Serverless)..." -ForegroundColor Yellow
az cosmosdb create `
    --name $COSMOS_NAME `
    --resource-group $RG `
    --locations regionName=$LOCATION failoverPriority=0 `
    --capabilities EnableServerless EnableNoSQLVectorSearch `
    --default-consistency-level Session `
    --output none

az cosmosdb sql database create `
    --account-name $COSMOS_NAME `
    --resource-group $RG `
    --name "vectordb" `
    --output none

# Container com vector embedding policy
$vectorPolicy = @'
{
  "vectorEmbeddings": [
    {
      "path": "/embedding",
      "dataType": "float32",
      "distanceFunction": "cosine",
      "dimensions": 1536
    }
  ]
}
'@
$vectorPolicyFile = "$env:TEMP\cosmos-vector-policy.json"
$vectorPolicy | Out-File -FilePath $vectorPolicyFile -Encoding utf8

$indexingPolicy = @'
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [{ "path": "/*" }],
  "excludedPaths": [{ "path": "/embedding/*" }],
  "vectorIndexes": [{ "path": "/embedding", "type": "diskANN" }]
}
'@
$indexingPolicyFile = "$env:TEMP\cosmos-indexing-policy.json"
$indexingPolicy | Out-File -FilePath $indexingPolicyFile -Encoding utf8

az cosmosdb sql container create `
    --account-name $COSMOS_NAME `
    --resource-group $RG `
    --database-name "vectordb" `
    --name "documents" `
    --partition-key-path "/category" `
    --vector-embedding-policy "$vectorPolicyFile" `
    --idx "$indexingPolicyFile" `
    --output none

Write-Host "  ✓ Cosmos DB: $COSMOS_NAME (database: vectordb, container: documents)" -ForegroundColor Green

# --- 4. Azure Database for PostgreSQL Flexible Server ---
Write-Host "`n[4/5] Criando PostgreSQL Flexible Server..." -ForegroundColor Yellow
az postgres flexible-server create `
    --name $PG_NAME `
    --resource-group $RG `
    --location $LOCATION `
    --admin-user $ADMIN_USER `
    --admin-password "$ADMIN_PASSWORD" `
    --sku-name Standard_B2s `
    --tier Burstable `
    --storage-size 32 `
    --version 16 `
    --public-access 0.0.0.0 `
    --output none

# Habilitar extensão pgvector
az postgres flexible-server parameter set `
    --resource-group $RG `
    --server-name $PG_NAME `
    --name azure.extensions `
    --value vector `
    --output none

Write-Host "  ✓ PostgreSQL: $PG_NAME (pgvector habilitado)" -ForegroundColor Green

# --- 5. Azure SQL Database ---
Write-Host "`n[5/5] Criando Azure SQL Database..." -ForegroundColor Yellow

# Obter informações do usuário Entra atual (necessário para cumprir política MCAPS Entra-only)
$entraUser = az ad signed-in-user show --query "userPrincipalName" -o tsv 2>$null
$entraUserId = az ad signed-in-user show --query "id" -o tsv 2>$null

if (-not $entraUser -or -not $entraUserId) {
    Write-Host "  ⚠ Não foi possível obter usuário Entra. SQL Server bloqueado por política MCAPS." -ForegroundColor Yellow
} else {
    # Criar SQL Server com Entra-only auth para cumprir política MCAPS
    az sql server create `
        --name $SQL_SERVER_NAME `
        --resource-group $RG `
        --location $LOCATION `
        --enable-ad-only-auth `
        --external-admin-name $entraUser `
        --external-admin-sid $entraUserId `
        --assign-identity `
        --output none
}

# Permitir acesso de IPs Azure
az sql server firewall-rule create `
    --resource-group $RG `
    --server $SQL_SERVER_NAME `
    --name AllowAzureServices `
    --start-ip-address 0.0.0.0 `
    --end-ip-address 0.0.0.0 `
    --output none

# Permitir acesso do IP atual
$myIp = (Invoke-RestMethod -Uri "https://api.ipify.org")
az sql server firewall-rule create `
    --resource-group $RG `
    --server $SQL_SERVER_NAME `
    --name AllowMyIP `
    --start-ip-address $myIp `
    --end-ip-address $myIp `
    --output none

az sql db create `
    --resource-group $RG `
    --server $SQL_SERVER_NAME `
    --name $SQL_DB_NAME `
    --edition GeneralPurpose `
    --compute-model Provisioned `
    --family Gen5 `
    --capacity 2 `
    --output none

Write-Host "  ✓ Azure SQL: $SQL_SERVER_NAME/$SQL_DB_NAME" -ForegroundColor Green

# --- RESUMO ---
Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host " PROVISIONAMENTO COMPLETO!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Recursos criados em $LOCATION :" -ForegroundColor White
Write-Host "  • Resource Group:  $RG"
Write-Host "  • AI Search:       $AI_SEARCH_NAME"
Write-Host "  • Cosmos DB:       $COSMOS_NAME"
Write-Host "  • PostgreSQL:      $PG_NAME"
Write-Host "  • Azure SQL:       $SQL_SERVER_NAME/$SQL_DB_NAME (Entra-only)"
Write-Host ""
Write-Host "`nProximo passo: execute .\01b-configure-entra-auth.ps1" -ForegroundColor Yellow

# --- Salvar configuração para os scripts Python ---
$config = @{
    resource_group   = $RG
    location         = $LOCATION
    ai_search_name   = $AI_SEARCH_NAME
    cosmos_name      = $COSMOS_NAME
    pg_name          = $PG_NAME
    sql_server_name  = $SQL_SERVER_NAME
    sql_db_name      = $SQL_DB_NAME
} | ConvertTo-Json

$config | Out-File -FilePath "$PSScriptRoot\..\config.json" -Encoding utf8
Write-Host "`nConfiguração salva em config.json" -ForegroundColor Gray
