# ============================================================
# 01b-configure-entra-auth.ps1
# Configura autenticação Entra ID pós-provisionamento.
# Executar APÓS 01-create-resources.ps1 e ANTES de 02-generate-data.py.
#
# O que este script faz:
#   1. Detecta o usuário logado no Azure CLI
#   2. Define Entra admin no PostgreSQL Flexible Server
#   3. Define Entra admin no Azure SQL Server + cria usuário no banco via sqlcmd
#   4. Atribui roles de dados no Azure AI Search (RBAC ARM)
#   5. Atribui role de dados no Cosmos DB (RBAC data-plane)
#   6. Gera grants no PostgreSQL via Python + psycopg2 (token Entra)
#   7. Atualiza o arquivo .env com os valores detectados
# ============================================================

$ErrorActionPreference = "Stop"

# --- Carregar configuração ---
$ConfigFile = "$PSScriptRoot\..\config.json"
if (-not (Test-Path $ConfigFile)) {
    Write-Host "ERRO: config.json não encontrado. Execute 01-create-resources.ps1 primeiro." -ForegroundColor Red
    exit 1
}
$config = Get-Content $ConfigFile | ConvertFrom-Json

$RG              = $config.resource_group
$AI_SEARCH_NAME  = $config.ai_search_name
$COSMOS_NAME     = $config.cosmos_name
$PG_NAME         = $config.pg_name
$SQL_SERVER_NAME = $config.sql_server_name
$SQL_DB_NAME     = $config.sql_db_name

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Configurando Entra ID — Pós-Provisionamento" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# ============================================================
# PASSO 0 — Identidade do usuário logado
# ============================================================
Write-Host "`n[0/6] Obtendo identidade do usuário logado..." -ForegroundColor Yellow

$currentUser = az ad signed-in-user show --query "{upn:userPrincipalName, oid:id}" -o json | ConvertFrom-Json
$USER_UPN   = $currentUser.upn
$USER_OID   = $currentUser.oid

Write-Host "  UPN:       $USER_UPN"
Write-Host "  Object ID: $USER_OID"

# ============================================================
# PASSO 1 — PostgreSQL: Entra admin
# ============================================================
Write-Host "`n[1/6] Configurando Entra admin no PostgreSQL ($PG_NAME)..." -ForegroundColor Yellow

az postgres flexible-server microsoft-entra-admin create `
    --resource-group $RG `
    --server-name    $PG_NAME `
    --display-name   $USER_UPN `
    --object-id      $USER_OID `
    --type           User `
    --output none

Write-Host "  ✓ Entra admin definido: $USER_UPN" -ForegroundColor Green

# ============================================================
# PASSO 2 — Azure SQL: Entra admin
# ============================================================
Write-Host "`n[2/6] Configurando Entra admin no Azure SQL Server ($SQL_SERVER_NAME)..." -ForegroundColor Yellow

az sql server ad-admin create `
    --resource-group  $RG `
    --server-name     $SQL_SERVER_NAME `
    --display-name    $USER_UPN `
    --object-id       $USER_OID `
    --output none

Write-Host "  ✓ Entra admin definido: $USER_UPN" -ForegroundColor Green

# ============================================================
# PASSO 3 — Azure SQL: criar usuário no banco + grants
# ============================================================
Write-Host "`n[3/6] Criando usuário Entra no banco $SQL_DB_NAME via sqlcmd..." -ForegroundColor Yellow

$sqlServer = "$SQL_SERVER_NAME.database.windows.net"

# sqlcmd -G usa o token do az login automaticamente
$sqlCmds = @"
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '$USER_UPN')
BEGIN
    CREATE USER [$USER_UPN] FROM EXTERNAL PROVIDER;
END
ALTER ROLE db_datareader ADD MEMBER [$USER_UPN];
ALTER ROLE db_datawriter ADD MEMBER [$USER_UPN];
ALTER ROLE db_ddladmin  ADD MEMBER [$USER_UPN];
PRINT 'Grants aplicados com sucesso.';
"@

$tmpSql = [System.IO.Path]::GetTempFileName() -replace '\.tmp$', '.sql'
$sqlCmds | Out-File -FilePath $tmpSql -Encoding utf8

$sqlcmdPath = "sqlcmd"
if (Test-Path "C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\SQLCMD.EXE") {
    $sqlcmdPath = "C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\SQLCMD.EXE"
}

& $sqlcmdPath `
    -S $sqlServer `
    -d $SQL_DB_NAME `
    -G `
    -N `
    -i $tmpSql `
    -b

Remove-Item $tmpSql -ErrorAction SilentlyContinue

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Usuário e grants aplicados no Azure SQL" -ForegroundColor Green
} else {
    Write-Host "  ⚠ sqlcmd retornou código $LASTEXITCODE. Verifique conectividade e firewall." -ForegroundColor Yellow
}

# ============================================================
# PASSO 4 — AI Search: RBAC data-plane
# ============================================================
Write-Host "`n[4/6] Atribuindo roles de dados no AI Search ($AI_SEARCH_NAME)..." -ForegroundColor Yellow

$searchResourceId = (az search service show `
    --name $AI_SEARCH_NAME `
    --resource-group $RG `
    --query id -o tsv)

foreach ($roleName in @("Search Index Data Contributor", "Search Index Data Reader", "Search Service Contributor")) {
    $existing = az role assignment list `
        --assignee  $USER_OID `
        --role      $roleName `
        --scope     $searchResourceId `
        --query     "[0].id" -o tsv 2>$null

    if (-not $existing) {
        az role assignment create `
            --assignee  $USER_OID `
            --role      $roleName `
            --scope     $searchResourceId `
            --output none
        Write-Host "  ✓ Role '$roleName' atribuída" -ForegroundColor Green
    } else {
        Write-Host "  · '$roleName' já existe, ignorado" -ForegroundColor Gray
    }
}

# ============================================================
# PASSO 5 — Cosmos DB: RBAC data-plane
# ============================================================
Write-Host "`n[5/6] Atribuindo role de dados no Cosmos DB ($COSMOS_NAME)..." -ForegroundColor Yellow

$existingCosmos = az cosmosdb sql role assignment list `
    --account-name   $COSMOS_NAME `
    --resource-group $RG `
    --query          "[?principalId=='$USER_OID'].id" -o tsv 2>$null

if (-not $existingCosmos) {
    az cosmosdb sql role assignment create `
        --account-name      $COSMOS_NAME `
        --resource-group    $RG `
        --role-definition-name "Cosmos DB Built-in Data Contributor" `
        --scope             "/" `
        --principal-id      $USER_OID `
        --output none
    Write-Host "  ✓ Cosmos DB Built-in Data Contributor atribuída" -ForegroundColor Green
} else {
    Write-Host "  · Role Cosmos já existe, ignorada" -ForegroundColor Gray
}

# ============================================================
# PASSO 6 — PostgreSQL: grants no banco via Python
# ============================================================
Write-Host "`n[6/6] Aplicando grants no PostgreSQL via Python..." -ForegroundColor Yellow

$pgGrantScript = @"
import psycopg2
from azure.identity import DefaultAzureCredential

PG_HOST = "$($PG_NAME).postgres.database.azure.com"
PG_USER = "$USER_UPN"

credential = DefaultAzureCredential()
token = credential.get_token("https://ossrdbms-aad.database.windows.net/.default").token

conn = psycopg2.connect(
    host=PG_HOST, database="postgres", user=PG_USER,
    password=token, sslmode="require"
)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cur.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER;")
    print(f"  Grants aplicados para {PG_USER}")
conn.close()
"@

$tmpPy = [System.IO.Path]::GetTempFileName() -replace '\.tmp$', '.py'
$pgGrantScript | Out-File -FilePath $tmpPy -Encoding utf8

try {
    python $tmpPy
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ Grants no PostgreSQL aplicados com sucesso" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Python retornou código $LASTEXITCODE. Verifique o .env e a conectividade." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠ Não foi possível executar grants no PostgreSQL: $_" -ForegroundColor Yellow
    Write-Host "    Execute manualmente após configurar .env:" -ForegroundColor Gray
    Write-Host "      GRANT ALL ON SCHEMA public TO `"$USER_UPN`";" -ForegroundColor Gray
} finally {
    Remove-Item $tmpPy -ErrorAction SilentlyContinue
}

# ============================================================
# ATUALIZAR .env
# ============================================================
Write-Host "`n[+] Atualizando .env com valores detectados..." -ForegroundColor Yellow

$DotEnvFile = "$PSScriptRoot\..\.env"

if (Test-Path $DotEnvFile) {
    $envContent = Get-Content $DotEnvFile -Raw
    $envContent = $envContent -replace 'AZURE_PG_ENTRA_USER=.*', "AZURE_PG_ENTRA_USER=$USER_UPN"
    $envContent | Out-File -FilePath $DotEnvFile -Encoding utf8 -NoNewline
    Write-Host "  ✓ AZURE_PG_ENTRA_USER=$USER_UPN" -ForegroundColor Green
} else {
    Write-Host "  · .env não encontrado — crie a partir de .env.example e ajuste os valores acima" -ForegroundColor Gray
}

# ============================================================
# RESUMO
# ============================================================
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " CONFIGURAÇÃO ENTRA ID CONCLUÍDA" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Identidade configurada:" -ForegroundColor White
Write-Host "  UPN:       $USER_UPN"
Write-Host "  Object ID: $USER_OID"
Write-Host ""
Write-Host "Serviços configurados:" -ForegroundColor White
Write-Host "  ✓ PostgreSQL  — Entra admin + grants"
Write-Host "  ✓ Azure SQL   — Entra admin + user + grants"
Write-Host "  ✓ AI Search   — RBAC data-plane (3 roles)"
Write-Host "  ✓ Cosmos DB   — Built-in Data Contributor"
Write-Host ""
Write-Host "Verifique/complete o arquivo .env antes de prosseguir:" -ForegroundColor Yellow
Write-Host "  AZURE_OPENAI_ENDPOINT             = https://<recurso>.openai.azure.com/"
Write-Host "  AZURE_OPENAI_EMBEDDING_DEPLOYMENT = text-embedding-3-small"
Write-Host "  AZURE_PG_ENTRA_USER               = $USER_UPN"
Write-Host ""
Write-Host "Próximo passo: python scripts/02-generate-data.py" -ForegroundColor Yellow
