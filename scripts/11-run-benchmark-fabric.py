"""
Benchmark de Busca Vetorial — Microsoft Fabric (Nativo)
Usa Spark no Lakehouse e, opcionalmente, SQL Endpoint.

Abordagens testadas:
  1. Fabric SQL Endpoint com VECTOR_DISTANCE('cosine') (quando configurado)
  2. Spark SQL com calculo de similaridade cosseno
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from tabulate import tabulate
from dotenv import load_dotenv

load_dotenv()

TOP_K = 10
NUM_ITERATIONS = 5
WARMUP_QUERIES = 3
EMBEDDING_DIM = 1536
FABRIC_TABLE = "documents"
IS_FABRIC = "spark" in dir()

FABRIC_SQL_ENDPOINT = os.getenv("FABRIC_SQL_ENDPOINT")
FABRIC_CAPACITY = os.getenv("FABRIC_CAPACITY", "Unknown")

if IS_FABRIC:
    DATA_DIR = Path("/lakehouse/default/Files/data")
    if not DATA_DIR.exists():
        DATA_DIR = Path("data")

    RESULTS_DIR = Path("/lakehouse/default/Files/results")
    if not RESULTS_DIR.exists():
        RESULTS_DIR = Path("results")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
else:
    DATA_DIR = Path(__file__).parent.parent / "data"
    RESULTS_DIR = Path(__file__).parent.parent / "results"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================
# 1. CARREGAR DADOS
# =============================================
def load_input_data() -> tuple[list[dict], list[dict]]:
    documents_path = DATA_DIR / "documents.json"
    queries_path = DATA_DIR / "queries.json"

    if not documents_path.exists():
        raise FileNotFoundError(f"Arquivo de documentos nao encontrado: {documents_path}")
    if not queries_path.exists():
        raise FileNotFoundError(f"Arquivo de queries nao encontrado: {queries_path}")

    with open(documents_path, "r", encoding="utf-8") as f:
        documents = json.load(f)

    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)

    return documents, queries


# =============================================
# 2. SETUP: Criar tabela no Lakehouse via Spark
# =============================================
def setup_fabric_table_spark(documents: list[dict]) -> bool:
    if not IS_FABRIC:
        print("  ! Spark nao disponivel neste ambiente; setup via Spark sera pulado.")
        return False

    try:
        rows = []
        for doc in documents:
            emb = doc.get("embedding", [])
            if not isinstance(emb, list):
                emb = emb.tolist() if hasattr(emb, "tolist") else list(emb)

            rows.append(
                (
                    str(doc.get("id", "")),
                    doc.get("title", ""),
                    doc.get("category", "general"),
                    doc.get("content", "")[:500],
                    [float(x) for x in emb],
                )
            )

        from pyspark.sql.types import StructType, StructField, StringType, ArrayType, FloatType

        schema = StructType(
            [
                StructField("id", StringType(), False),
                StructField("title", StringType(), True),
                StructField("category", StringType(), True),
                StructField("content", StringType(), True),
                StructField("embedding", ArrayType(FloatType()), False),
            ]
        )

        df = spark.createDataFrame(rows, schema=schema)
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(FABRIC_TABLE)
        count = spark.table(FABRIC_TABLE).count()
        print(f"  + Tabela {FABRIC_TABLE} criada com {count} registros")
        return True
    except Exception as e:
        print(f"  x Erro no setup Spark: {e}")
        return False


# =============================================
# 3. BENCHMARK: Fabric SQL Endpoint (cosine)
# =============================================
def benchmark_fabric_sql_endpoint(queries: list[dict]) -> list[float]:
    try:
        import pyodbc
        from azure.identity import DefaultAzureCredential
        import struct
    except ImportError as e:
        print(f"    ! Dependencia ausente para SQL Endpoint: {e}")
        return []

    if not FABRIC_SQL_ENDPOINT:
        print("    ! FABRIC_SQL_ENDPOINT nao definido; benchmark SQL Endpoint sera pulado.")
        return []

    try:
        token = DefaultAzureCredential().get_token("https://database.windows.net/.default").token
    except Exception as e:
        print(f"    ! Erro ao obter token Entra ID: {e}")
        return []

    token_bytes = token.encode("utf-16-le")
    token_struct = struct.pack("<I", len(token_bytes)) + token_bytes
    sql_copt_ss_access_token = 1256

    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={FABRIC_SQL_ENDPOINT};"
        "DATABASE=default;"
        "Encrypt=yes;TrustServerCertificate=no;"
    )

    try:
        conn = pyodbc.connect(conn_str, attrs_before={sql_copt_ss_access_token: token_struct})
    except pyodbc.DatabaseError as e:
        print(f"    ! Erro ao conectar no SQL Endpoint: {e}")
        return []

    latencies: list[float] = []
    try:
        for i, query in enumerate(queries):
            embedding_json = json.dumps(query["embedding"])
            sql = f"""
                SELECT TOP {TOP_K}
                       id, title, category,
                       VECTOR_DISTANCE('cosine', embedding, CAST(CONVERT(VARCHAR(MAX), ?) AS VECTOR({EMBEDDING_DIM}))) AS distance
                FROM [{FABRIC_TABLE}]
                ORDER BY distance
            """

            if i < WARMUP_QUERIES:
                with conn.cursor() as cursor:
                    cursor.execute(sql, embedding_json)
                    cursor.fetchall()
                continue

            for _ in range(NUM_ITERATIONS):
                try:
                    start = time.perf_counter()
                    with conn.cursor() as cursor:
                        cursor.execute(sql, embedding_json)
                        cursor.fetchall()
                    elapsed = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed)
                except pyodbc.DatabaseError as e:
                    print(f"    Aviso: erro SQL Endpoint na query {i}: {e}")
    finally:
        conn.close()

    return latencies


# =============================================
# 4. BENCHMARK: Spark SQL (cosine)
# =============================================
def benchmark_spark_sql_cosine(queries: list[dict]) -> list[float]:
    if not IS_FABRIC:
        print("    ! Spark nao disponivel; benchmark Spark SQL sera pulado.")
        return []

    try:
        spark.sql(
            f"""
            CREATE OR REPLACE TEMP VIEW docs_with_norm AS
            SELECT *,
                   SQRT(AGGREGATE(embedding, DOUBLE(0), (acc, x) -> acc + x * x)) AS norm
            FROM {FABRIC_TABLE}
            """
        )
    except Exception as e:
        print(f"    ! Erro preparando view docs_with_norm: {e}")
        return []

    latencies: list[float] = []
    for i, query in enumerate(queries):
        query_vector = query["embedding"]
        vec_literal = ",".join(str(x) for x in query_vector)
        query_norm = float(np.linalg.norm(query_vector))
        if query_norm == 0:
            continue

        sql = f"""
            SELECT id, title, category,
                   AGGREGATE(
                       TRANSFORM(SEQUENCE(0, SIZE(embedding) - 1),
                                 idx -> embedding[idx] * ARRAY({vec_literal})[idx]),
                       DOUBLE(0), (acc, x) -> acc + x
                   ) / (norm * {query_norm}) AS cosine_similarity
            FROM docs_with_norm
            ORDER BY cosine_similarity DESC
            LIMIT {TOP_K}
        """

        if i < WARMUP_QUERIES:
            spark.sql(sql).collect()
            continue

        for _ in range(NUM_ITERATIONS):
            start = time.perf_counter()
            spark.sql(sql).collect()
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

    return latencies


# =============================================
# 5. UTIL
# =============================================
def compute_stats(latencies: list[float]) -> dict:
    if not latencies:
        return {"error": "Nenhuma latencia coletada"}

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


# =============================================
# 6. MAIN
# =============================================
def main():
    print("=" * 70)
    print(" BENCHMARK MICROSOFT FABRIC — VECTOR SEARCH (Nativo)")
    print(f" Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Modo: {'Notebook Fabric' if IS_FABRIC else 'Local'}")
    print(f" Capacity: {FABRIC_CAPACITY}")
    print(f" Top-K: {TOP_K} | Iteracoes por query: {NUM_ITERATIONS}")
    print("=" * 70)

    print("\n1) Carregando dados...")
    try:
        documents, queries = load_input_data()
    except Exception as e:
        print(f"\nERRO: {e}")
        print("Execute primeiro: python scripts/02-generate-data.py")
        return

    print(f"   + {len(documents)} documentos carregados")
    print(f"   + {len(queries)} queries carregadas ({len(queries) - WARMUP_QUERIES} efetivas + {WARMUP_QUERIES} warmup)")

    print("\n2) Setup da tabela...")
    print("-" * 50)
    setup_ok = setup_fabric_table_spark(documents)
    if not setup_ok and IS_FABRIC:
        print("Falha no setup Spark. Abortando benchmark.")
        return
    print("-" * 50)

    services: dict[str, callable] = {}
    services["Spark SQL (Distancia Cosseno)"] = benchmark_spark_sql_cosine
    services["Fabric SQL Endpoint (VECTOR_DISTANCE cosine)"] = benchmark_fabric_sql_endpoint

    all_results: dict[str, dict] = {}

    for name, benchmark_fn in services.items():
        print(f"\n{'-' * 50}")
        print(f"  Executando: {name}...")
        try:
            latencies = benchmark_fn(queries)
            if latencies:
                stats = compute_stats(latencies)
                all_results[name] = stats
                print(
                    f"  + Media: {stats['mean_ms']:.1f}ms | "
                    f"P95: {stats['p95_ms']:.1f}ms | P99: {stats['p99_ms']:.1f}ms"
                )
            else:
                all_results[name] = {"error": "Nenhuma latencia coletada"}
                print("  ! Nao foi possivel executar o teste")
        except Exception as e:
            print(f"  x ERRO: {e}")
            all_results[name] = {"error": str(e)}

    print("\n")
    print("=" * 70)
    print(" RESULTADOS DO BENCHMARK — MICROSOFT FABRIC")
    print("=" * 70)

    table_data = []
    for name, stats in all_results.items():
        if "error" in stats:
            table_data.append([name, "ERRO", "-", "-", "-", "-"])
        else:
            table_data.append(
                [
                    name,
                    f"{stats['mean_ms']:.1f}",
                    f"{stats['median_ms']:.1f}",
                    f"{stats['p95_ms']:.1f}",
                    f"{stats['p99_ms']:.1f}",
                    f"{stats['min_ms']:.1f} - {stats['max_ms']:.1f}",
                ]
            )

    headers = ["Servico", "Media (ms)", "Mediana (ms)", "P95 (ms)", "P99 (ms)", "Min-Max (ms)"]
    print("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))

    print("\nRANKING (por latencia media):")
    ranked = sorted(
        [(k, v) for k, v in all_results.items() if "error" not in v],
        key=lambda x: x[1]["mean_ms"],
    )
    if ranked:
        for i, (name, stats) in enumerate(ranked, 1):
            bar = "#" * max(1, int(stats["mean_ms"] / 10))
            print(f"  {i}o {name:<45} {stats['mean_ms']:>8.1f}ms  {bar}")
    else:
        print("  ! Nenhum resultado obtido")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"benchmark_fabric_nativo_{timestamp}.json"

    output = {
        "timestamp": datetime.now().isoformat(),
        "platform": "Microsoft Fabric (Nativo)",
        "config": {
            "execution_mode": "notebook" if IS_FABRIC else "local",
            "sql_endpoint": FABRIC_SQL_ENDPOINT,
            "capacity": FABRIC_CAPACITY,
            "table": FABRIC_TABLE,
            "top_k": TOP_K,
            "num_iterations": NUM_ITERATIONS,
            "warmup_queries": WARMUP_QUERIES,
            "total_queries": len(queries),
            "embedding_dim": EMBEDDING_DIM,
            "num_documents": len(documents),
        },
        "results": all_results,
    }

    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nResultados salvos: {results_file}")
    print("\nBenchmark Fabric concluido!")


if __name__ == "__main__":
    main()
