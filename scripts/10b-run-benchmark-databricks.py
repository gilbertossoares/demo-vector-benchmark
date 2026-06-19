"""
Benchmark de Busca Vetorial — Databricks Nativo
Usa Spark + Databricks SDK (sem dependências externas).

Abordagens testadas:
  1. Databricks Vector Search (SDK nativo)
  2. Spark SQL com cálculo de distância cosseno
"""

import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from tabulate import tabulate
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import (
    EndpointType, VectorIndexType, DirectAccessVectorIndexSpec, EmbeddingVectorColumn
)
from pyspark.sql.types import (
    StructType, StructField, StringType, ArrayType, FloatType
)

# --- Configuração Nativa ---
DATABRICKS_HOST = f"https://{spark.conf.get('spark.databricks.workspaceUrl')}"
CATALOG = "gssdtvshybrid"
SCHEMA = "vector_benchmark"
TABLE_NAME = f"{CATALOG}.{SCHEMA}.documents"
VS_ENDPOINT_NAME = "benchmark_vs_endpoint"
VS_INDEX_NAME = f"{CATALOG}.{SCHEMA}.documents_vs_index"

DATA_DIR = Path("/Workspace/Users/admin@mngenv019932.onmicrosoft.com/data")
RESULTS_DIR = Path("/Workspace/Users/admin@mngenv019932.onmicrosoft.com/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_K = 10
NUM_ITERATIONS = 5
WARMUP_QUERIES = 3

w = WorkspaceClient()

print("=" * 70)
print(" BENCHMARK DATABRICKS — VECTOR SEARCH (Nativo)")
print(f" Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f" Host: {DATABRICKS_HOST}")
print(f" Catálogo: {CATALOG}.{SCHEMA}")
print(f" Top-K: {TOP_K} | Iterações por query: {NUM_ITERATIONS}")
print("=" * 70)

# =============================================
# 1. CARREGAR DADOS
# =============================================
print("\n📂 Carregando dados...")

with open(DATA_DIR / "documents.json", "r", encoding="utf-8") as f:
    documents = json.load(f)
print(f"   ✓ {len(documents)} documentos carregados")

with open(DATA_DIR / "queries.json", "r", encoding="utf-8") as f:
    queries = json.load(f)
print(f"   ✓ {len(queries)} queries carregadas ({len(queries) - WARMUP_QUERIES} efetivas + {WARMUP_QUERIES} warmup)")

# =============================================
# 2. SETUP: Criar schema e tabela via Spark
# =============================================
print(f"\n🔧 SETUP: Criando tabela via Spark...")
print("─" * 50)

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

# Preparar dados para DataFrame
rows = []
for doc in documents:
    rows.append((
        doc["id"],
        doc.get("title", ""),
        doc.get("category", "general"),
        doc.get("content", "")[:500],
        [float(x) for x in doc["embedding"]],
    ))

schema = StructType([
    StructField("id", StringType(), False),
    StructField("title", StringType(), True),
    StructField("category", StringType(), True),
    StructField("content", StringType(), True),
    StructField("embedding", ArrayType(FloatType()), False),
])

df = spark.createDataFrame(rows, schema=schema)
df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TABLE_NAME)

count = spark.table(TABLE_NAME).count()
print(f"  ✓ Tabela {TABLE_NAME} criada com {count} registros")
print("─" * 50)

# =============================================
# 3. SETUP: Vector Search Endpoint e Index
# =============================================
print("\n🔍 SETUP: Configurando Vector Search...")
print("─" * 50)

# Verificar/criar endpoint
try:
    ep = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT_NAME)
    print(f"  ✓ Endpoint '{VS_ENDPOINT_NAME}' já existe (status: {ep.endpoint_status})")
except Exception:
    print(f"  ⏳ Criando endpoint '{VS_ENDPOINT_NAME}'...")
    print("     (Isso pode levar alguns minutos na primeira vez)")
    try:
        w.vector_search_endpoints.create_endpoint_and_wait(
            name=VS_ENDPOINT_NAME,
            endpoint_type=EndpointType.STANDARD,
        )
        print(f"  ✓ Endpoint criado com sucesso")
    except Exception as e:
        print(f"  ⚠️  Erro ao criar endpoint: {e}")
        print("     O benchmark de Vector Search será pulado.")
        VS_ENDPOINT_NAME = None

# Verificar/criar index
vs_index_ready = False
if VS_ENDPOINT_NAME:
    try:
        idx = w.vector_search_indexes.get_index(VS_INDEX_NAME)
        print(f"  ✓ Index '{VS_INDEX_NAME}' já existe (status: ready={idx.status.ready})")
        vs_index_ready = idx.status.ready
    except Exception:
        print(f"  ⏳ Criando index '{VS_INDEX_NAME}'...")
        try:
            w.vector_search_indexes.create_index(
                name=VS_INDEX_NAME,
                endpoint_name=VS_ENDPOINT_NAME,
                primary_key="id",
                index_type=VectorIndexType.DIRECT_ACCESS,
                direct_access_index_spec=DirectAccessVectorIndexSpec(
                    embedding_vector_columns=[
                        EmbeddingVectorColumn(name="embedding", embedding_dimension=1536)
                    ],
                    schema_json=json.dumps({
                        "id": "string",
                        "title": "string",
                        "category": "string",
                        "content": "string",
                        "embedding": "array<float>",
                    }),
                ),
            )
            # Esperar index ficar pronto
            import time as _time
            print("     Aguardando provisionamento...")
            for _attempt in range(120):
                _idx = w.vector_search_indexes.get_index(VS_INDEX_NAME)
                if _idx.status.ready:
                    break
                _time.sleep(5)

            # Upsert data em batches (formato: lista de dicts)
            print(f"  ✓ Index pronto. Inserindo dados...")
            batch_size = 20
            for i in range(0, len(rows), batch_size):
                batch_dicts = [
                    {"id": r[0], "title": r[1], "category": r[2], "content": r[3][:200], "embedding": r[4]}
                    for r in rows[i:i + batch_size]
                ]
                w.vector_search_indexes.upsert_data_vector_index(
                    index_name=VS_INDEX_NAME,
                    inputs_json=json.dumps(batch_dicts),
                )
            print(f"  ✓ {len(rows)} documentos inseridos no index")
            vs_index_ready = True
        except Exception as e:
            print(f"  ⚠️  Erro ao criar index: {e}")
            vs_index_ready = False

print("─" * 50)

# =============================================
# 4. BENCHMARK: Vector Search (SDK)
# =============================================
def benchmark_vector_search_sdk(queries_list):
    """Benchmark via Databricks SDK Vector Search."""
    latencies = []
    for i, query in enumerate(queries_list):
        query_vector = query["embedding"]

        if i < WARMUP_QUERIES:
            w.vector_search_indexes.query_index(
                index_name=VS_INDEX_NAME,
                columns=["id", "title", "category"],
                query_vector=query_vector,
                num_results=TOP_K,
            )
            continue

        iter_latencies = []
        for _ in range(NUM_ITERATIONS):
            try:
                start = time.perf_counter()
                w.vector_search_indexes.query_index(
                    index_name=VS_INDEX_NAME,
                    columns=["id", "title", "category"],
                    query_vector=query_vector,
                    num_results=TOP_K,
                )
                elapsed = (time.perf_counter() - start) * 1000
                iter_latencies.append(elapsed)
            except Exception as e:
                print(f"    Aviso: Erro na query {i}: {e}")
                continue

        latencies.extend(iter_latencies)
    return latencies


# =============================================
# 5. BENCHMARK: Spark SQL (distância cosseno)
# =============================================
def benchmark_spark_sql(queries_list):
    """Benchmark via Spark SQL com cálculo de distância cosseno."""
    # Pré-computar norma dos embeddings na tabela
    spark.sql(f"""
        CREATE OR REPLACE TEMP VIEW docs_with_norm AS
        SELECT *,
               SQRT(AGGREGATE(embedding, DOUBLE(0), (acc, x) -> acc + x * x)) AS norm
        FROM {TABLE_NAME}
    """)

    latencies = []
    for i, query in enumerate(queries_list):
        query_vector = query["embedding"]
        vec_literal = ",".join(str(x) for x in query_vector)
        query_norm = float(np.linalg.norm(query_vector))

        sql = f"""
            SELECT id, title, category,
                   AGGREGATE(
                       TRANSFORM(SEQUENCE(0, SIZE(embedding) - 1),
                                 i -> embedding[i] * ARRAY({vec_literal})[i]),
                       DOUBLE(0), (acc, x) -> acc + x
                   ) / (norm * {query_norm}) AS cosine_similarity
            FROM docs_with_norm
            ORDER BY cosine_similarity DESC
            LIMIT {TOP_K}
        """

        if i < WARMUP_QUERIES:
            spark.sql(sql).collect()
            continue

        iter_latencies = []
        for _ in range(NUM_ITERATIONS):
            start = time.perf_counter()
            spark.sql(sql).collect()
            elapsed = (time.perf_counter() - start) * 1000
            iter_latencies.append(elapsed)

        latencies.extend(iter_latencies)
    return latencies


# =============================================
# 6. EXECUÇÃO E RESULTADOS
# =============================================
def compute_stats(latencies):
    if not latencies:
        return {"error": "Nenhuma latência coletada"}
    arr = np.array(latencies)
    return {
        "count": len(arr),
        "mean_ms": round(float(np.mean(arr)), 2),
        "median_ms": round(float(np.median(arr)), 2),
        "p95_ms": round(float(np.percentile(arr, 95)), 2),
        "p99_ms": round(float(np.percentile(arr, 99)), 2),
        "min_ms": round(float(np.min(arr)), 2),
        "max_ms": round(float(np.max(arr)), 2),
        "std_ms": round(float(np.std(arr)), 2),
    }


# Montar lista de benchmarks
services = {}
if vs_index_ready:
    services["Vector Search (SDK)"] = benchmark_vector_search_sdk
else:
    print("\n⚠️  Vector Search não disponível — pulando benchmark SDK")

services["Spark SQL (Distância Cosseno)"] = benchmark_spark_sql

all_results = {}

for name, benchmark_fn in services.items():
    print(f"\n{'─' * 50}")
    print(f"  ▶ Executando: {name}...")
    try:
        latencies = benchmark_fn(queries)
        if latencies:
            stats = compute_stats(latencies)
            all_results[name] = stats
            print(f"  ✓ Média: {stats['mean_ms']:.1f}ms | P95: {stats['p95_ms']:.1f}ms | P99: {stats['p99_ms']:.1f}ms")
        else:
            all_results[name] = {"error": "Nenhuma latência coletada"}
            print(f"  ⚠️  Não foi possível executar o teste")
    except Exception as e:
        print(f"  ✗ ERRO: {e}")
        all_results[name] = {"error": str(e)}

# --- Relatório ---
print("\n")
print("=" * 70)
print(" RESULTADOS DO BENCHMARK")
print("=" * 70)

table_data = []
for name, stats in all_results.items():
    if "error" in stats:
        table_data.append([name, "ERRO", "-", "-", "-", "-"])
    else:
        table_data.append([
            name,
            f"{stats['mean_ms']:.1f}",
            f"{stats['median_ms']:.1f}",
            f"{stats['p95_ms']:.1f}",
            f"{stats['p99_ms']:.1f}",
            f"{stats['min_ms']:.1f} - {stats['max_ms']:.1f}",
        ])

headers_tbl = ["Serviço", "Média (ms)", "Mediana (ms)", "P95 (ms)", "P99 (ms)", "Min-Max (ms)"]
print("\n" + tabulate(table_data, headers=headers_tbl, tablefmt="grid"))

# Ranking
print("\n📊 RANKING (por latência média):")
ranked = sorted(
    [(k, v) for k, v in all_results.items() if "error" not in v],
    key=lambda x: x[1]["mean_ms"],
)
if ranked:
    for i, (name, stats) in enumerate(ranked, 1):
        bar = "█" * max(1, int(stats["mean_ms"] / 10))
        print(f"  {i}º {name:<35} {stats['mean_ms']:>8.1f}ms  {bar}")
else:
    print("  ⚠️  Nenhum resultado obtido")

# Salvar resultados
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
results_file = RESULTS_DIR / f"benchmark_nativo_{timestamp}.json"
output = {
    "timestamp": datetime.now().isoformat(),
    "platform": "Databricks (Nativo)",
    "config": {
        "host": DATABRICKS_HOST,
        "catalog": CATALOG,
        "schema": SCHEMA,
        "top_k": TOP_K,
        "num_iterations": NUM_ITERATIONS,
        "warmup_queries": WARMUP_QUERIES,
        "total_queries": len(queries),
        "embedding_dim": 1536,
        "num_documents": len(documents),
    },
    "results": all_results,
}
with open(results_file, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n📁 Resultados salvos: {results_file}")
print("\n✅ Benchmark concluído!")