> 🇧🇷 Versão em Português | 🇺🇸 [English version](README.md)

# Azure Vector Storage — Benchmark Comparativo

## Objetivo

Demonstração prática comparando o **tempo de resposta** de busca vetorial entre os principais serviços Azure:

| # | Serviço | Algoritmo | Região |
|---|---------|-----------|--------|
| 1 | Azure AI Search | HNSW | Brazil South |
| 2 | Azure Cosmos DB for NoSQL | DiskANN | Brazil South |
| 3 | Azure Database for PostgreSQL (pgvector) | HNSW | Brazil South |
| 4 | Azure SQL Database | DiskANN (Preview) | Brazil South |

## Pré-requisitos

- Azure CLI (`az`) instalado e autenticado
- Python 3.10+
- Subscription com permissão para criar recursos
- Azure OpenAI com modelo `text-embedding-3-small` deployado (para gerar embeddings)
- Permissões de dados via Entra ID nos serviços usados no benchmark

### Autenticação (Entra ID)

Este projeto usa `DefaultAzureCredential` em todos os scripts Python.

1. Faça login no Azure CLI:

```powershell
az login
az account set --subscription <subscription-id-ou-nome>
```

2. Crie o arquivo `.env` a partir de `.env.example` e preencha os valores:

```powershell
Copy-Item .env.example .env
```

Variáveis necessárias:
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `AZURE_PG_ENTRA_USER`

3. Garanta acesso de dados para a identidade usada no `az login`:
- Azure OpenAI: permissão para inferência no recurso
- Azure AI Search: permissão de leitura/escrita no índice
- Cosmos DB for NoSQL: acesso de dados ao banco/container
- PostgreSQL Flexible Server: usuário Entra ID criado no servidor e privilégios no banco
- Azure SQL Database: usuário Entra ID criado no banco e permissões de leitura

## Estrutura do Projeto

```
demo-vector-benchmark/
├── README.md                    # Versão em inglês (padrão)
├── README_pt.md                 # Este arquivo
├── scripts/
│   ├── 01-create-resources.ps1  # Provisiona todos os recursos Azure
│   ├── 01b-configure-entra-auth.ps1  # Configura autenticação Entra ID
│   ├── 02-generate-data.py      # Gera dataset padronizado + embeddings
│   ├── 03-load-ai-search.py     # Carrega dados no AI Search
│   ├── 04-load-cosmosdb.py      # Carrega dados no Cosmos DB
│   ├── 05-load-postgresql.py    # Carrega dados no PostgreSQL
│   ├── 07-load-azuresql.py      # Carrega dados no Azure SQL
│   ├── 08-run-benchmark.py      # Executa benchmark e coleta métricas
│   └── 09-cleanup.ps1           # Remove todos os recursos
├── data/                        # Gerado pelo script 02 (ignorado pelo git)
├── results/                     # Gerado pelo script 08 (ignorado pelo git)
└── requirements.txt
```

## Guia Passo a Passo

### 1. Instalar dependências Python

```powershell
cd demo-vector-benchmark
pip install -r requirements.txt
```

### 2. Provisionar recursos Azure

```powershell
# Defina a senha de admin antes de executar
$env:SQL_ADMIN_PASSWORD = "SuaSenhaAqui"

# Edite as variáveis no início do script se necessário
.\scripts\01-create-resources.ps1
```

Este script cria:
- Resource Group: `rg-vector-benchmark-brazilsouth`
- Azure AI Search (Basic): `srch-vectorbench-brs`
- Cosmos DB (NoSQL, Serverless): `cosmos-vectorbench-brs`
- PostgreSQL Flexible Server (Standard_B2s): `pg-vectorbench-brs`
- Azure SQL Database (GP): `sql-vectorbench-brs`

### 2b. Configurar autenticação Entra ID (pós-provisionamento)

```powershell
.\scripts\01b-configure-entra-auth.ps1
```

Este script detecta o usuário autenticado com `az login` e configura automaticamente:

| Serviço | O que é configurado |
|---|---|
| PostgreSQL | Entra admin + grants no schema |
| Azure SQL | Entra admin + usuário no banco + roles DDL/DML |
| AI Search | RBAC: Search Index Data Contributor / Reader / Service Contributor |
| Cosmos DB | RBAC data-plane: Cosmos DB Built-in Data Contributor |

> O script também atualiza `AZURE_PG_ENTRA_USER` no `.env` automaticamente.

### 3. Gerar dataset padronizado

```powershell
python scripts/02-generate-data.py
```

Gera 1.000 documentos com embeddings de 1.536 dimensões usando Azure OpenAI `text-embedding-3-small` com token Entra ID.

### 4. Carregar dados em cada serviço

```powershell
python scripts/03-load-ai-search.py
python scripts/04-load-cosmosdb.py
python scripts/05-load-postgresql.py
python scripts/07-load-azuresql.py
```

### 5. Executar benchmark

```powershell
python scripts/08-run-benchmark.py
```

Executa queries de similaridade em cada serviço e registra:
- Latência P50, P95, P99
- Tempo médio de resposta
- Recall (comparado com busca exaustiva)

### 6. Limpar recursos

```powershell
.\scripts\09-cleanup.ps1
```

## Notas Importantes

- **Recomendação**: Execute o benchmark e destrua os recursos no mesmo dia
- **Azure SQL**: Requer `azureADOnlyAuthentication = true` (Entra ID-only authentication). O script automaticamente configura isso via `01b-configure-entra-auth.ps1`.
- Todos os serviços usam o **mesmo dataset e embeddings** para comparação justa

## Problemas Conhecidos e Soluções

### Azure SQL: Erro `RequestDisallowedByPolicy`
**Causa**: Azure SQL exige Entra ID-only authentication.  
**Solução**: Já resolvida no script. Se falhar, execute `01b-configure-entra-auth.ps1` após o provisionamento.

## Licença

MIT License — veja o arquivo [LICENSE](LICENSE) para detalhes.

---

**Última atualização**: 19 de junho de 2026 | **Status**: Pronto para Produção ✅
