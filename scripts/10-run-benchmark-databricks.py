"""
10-run-benchmark-databricks.py
Executes vector search benchmark on Databricks Vector Search.

Requirements:
- Databricks workspace provisioned with Unity Catalog
- Documents table with embeddings loaded
- Databricks access token (DATABRICKS_TOKEN)
- Databricks host (DATABRICKS_HOST)

Required environment variables (.env):
  DATABRICKS_TOKEN=<your-token>
  DATABRICKS_HOST=<your-host> (e.g., https://adb-xxxxx.azuredatabricks.net)
  DATABRICKS_WAREHOUSE_ID=<warehouse-id> (for SQL queries)
  DATABRICKS_CATALOG=<catalog-name> (default: 'main')
  DATABRICKS_SCHEMA=<schema-name> (default: 'vector_benchmark')
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from tabulate import tabulate
from dotenv import load_dotenv

load_dotenv()

# Detect if running INSIDE Databricks (notebook) or locally
IS_DATABRICKS = 'spark' in dir()  # Check if spark session exists

if IS_DATABRICKS:
    # Running inside Databricks notebook - use native context
    print("✓ Detected Databricks notebook - using native authentication")
    DATA_DIR = Path("/Workspace/data")
    RESULTS_DIR = Path("/Workspace/results")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    DATABRICKS_TOKEN = None
    DATABRICKS_HOST = None
    DATABRICKS_WAREHOUSE_ID = None
    DATABRICKS_CATALOG = "main"
    DATABRICKS_SCHEMA = "vector_benchmark"
else:
    # Running locally - use environment variables
    config_path = Path(__file__).parent.parent / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    
    DATA_DIR = Path(__file__).parent.parent / "data"
    RESULTS_DIR = Path(__file__).parent.parent / "results"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
    DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
    DATABRICKS_WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")
    DATABRICKS_CATALOG = os.getenv("DATABRICKS_CATALOG", "main")
    DATABRICKS_SCHEMA = os.getenv("DATABRICKS_SCHEMA", "vector_benchmark")
    
    if not DATABRICKS_TOKEN or not DATABRICKS_HOST:
        raise ValueError(
            "LOCAL mode: Set DATABRICKS_TOKEN and DATABRICKS_HOST in .env\n"
            "Or run this script directly in a Databricks notebook."
        )

# --- Configuration ---
TOP_K = 10  # Number of results per query
NUM_ITERATIONS = 5  # Repetitions per query to stabilize metrics
WARMUP_QUERIES = 3  # Warmup queries (discarded)


# =============================================
# DATABRICKS VECTOR SEARCH
# =============================================
# =============================================
# SETUP: CREATE TABLES AND LOAD DATA
# =============================================
def setup_databricks_table(documents: list[dict]) -> bool:
    """
    Create documents table in Databricks with embeddings.
    """
    try:
        import requests
    except ImportError:
        print("    ✗ requests not installed")
        return False

    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}",
        "Content-Type": "application/json",
    }

    # 1. Create table using SQL endpoint
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}.documents (
        id STRING NOT NULL,
        title STRING,
        category STRING,
        content STRING,
        embedding ARRAY<FLOAT> NOT NULL,
        PRIMARY KEY(id)
    )
    USING DELTA
    PARTITIONED BY (category)
    """

    # 2. Load data
    print("  ⏳ Loading data to Databricks...")
    try:
        # Prepare data for insertion
        rows = []
        for doc in documents:
            # Ensure embedding is a list
            emb = doc.get("embedding", [])
            if not isinstance(emb, list):
                emb = emb.tolist() if hasattr(emb, 'tolist') else list(emb)
            
            rows.append({
                "id": doc["id"],
                "title": doc.get("title", ""),
                "category": doc.get("category", "general"),
                "content": doc.get("content", ""),
                "embedding": emb,
            })

        # Using SQL for batch insertion
        for batch_idx in range(0, len(rows), 100):
            batch = rows[batch_idx:batch_idx + 100]
            
            # Build VALUES clause
            values_list = []
            for row in batch:
                emb_str = str(row["embedding"]).replace("'", "\\'")
                values_list.append(
                    f"('{row['id']}', '{row['title'].replace(chr(39), '')}', "
                    f"'{row['category']}', '{row['content'][:200].replace(chr(39), '')}', "
                    f"array({', '.join(str(x) for x in row['embedding'])})"
                    f")"
                )
            
            if values_list:
                insert_sql = f"""
                INSERT INTO {DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}.documents 
                VALUES {','.join(values_list)}
                """
                
                # Execute INSERT via SQL Warehouse
                try:
                    from databricks.sql import connect
                    conn = connect(
                        server_hostname=DATABRICKS_HOST.replace("https://", "").replace("http://", ""),
                        http_path=f"/sql/1.0/warehouses/{DATABRICKS_WAREHOUSE_ID}",
                        auth_type="pat",
                        token=DATABRICKS_TOKEN,
                    )
                    cursor = conn.cursor()
                    cursor.execute(insert_sql)
                    conn.close()
                except Exception as e:
                    print(f"    Warning: Error inserting batch {batch_idx}: {e}")

        print(f"  ✓ {len(rows)} documents loaded")
        return True

    except Exception as e:
        print(f"  ✗ Error loading data: {e}")
        return False


def benchmark_databricks_rest(queries: list[dict]) -> list[float]:
    """
    Execute benchmark on Databricks Vector Search via REST API.
    
    This method does not require additional SDK installation and works with
    any Databricks version that supports Vector Search.
    """
    import requests

    vector_search_endpoint = f"{DATABRICKS_HOST}/api/2.0/vector-search/indexes"
    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}",
        "Content-Type": "application/json",
    }

    index_name = f"{DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}.documents"

    latencies = []
    for i, query in enumerate(queries):
        query_vector = query["embedding"]

        payload = {
            "index_name": index_name,
            "query_vector": query_vector,
            "k": TOP_K,
            "num_candidates": min(TOP_K * 10, 500),  # Candidates for HNSW search
        }

        if i < WARMUP_QUERIES:
            # Warmup query
            try:
                response = requests.post(
                    f"{vector_search_endpoint}/query",
                    json=payload,
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
            except requests.RequestException as e:
                raise Exception(f"Error in Databricks warmup: {e}")
            continue

        # Measure phase
        iter_latencies = []
        for _ in range(NUM_ITERATIONS):
            try:
                start = time.perf_counter()
                response = requests.post(
                    f"{vector_search_endpoint}/query",
                    json=payload,
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
                elapsed = (time.perf_counter() - start) * 1000  # milliseconds
                
                # Check if there were results
                result_data = response.json()
                if "results" in result_data:
                    iter_latencies.append(elapsed)
            except requests.RequestException as e:
                print(f"    Warning: Error in query {i}: {e}")
                continue

        latencies.extend(iter_latencies)

    return latencies


def benchmark_databricks_sql(queries: list[dict]) -> list[float]:
    """
    Execute benchmark on Databricks via SQL Warehouse with vector search.
    
    Requires active SQL Warehouse and table with vector support.
    """
    try:
        from databricks.sql import connect
    except ImportError:
        print("    ⚠️  databricks-sql-connector not installed, skipping...")
        return []

    try:
        conn = connect(
            server_hostname=DATABRICKS_HOST.replace("https://", "").replace("http://", ""),
            http_path=f"/sql/1.0/warehouses/{DATABRICKS_WAREHOUSE_ID}",
            auth_type="pat",
            token=DATABRICKS_TOKEN,
        )
    except Exception as e:
        print(f"    ⚠️  Could not connect to SQL Warehouse: {e}")
        return []

    latencies = []
    try:
        for i, query in enumerate(queries):
            query_vector = query["embedding"]
            
            # Convert vector to Databricks string format
            vector_str = str(query_vector)
            
            # SQL query with vector search (syntax may vary)
            sql = f"""
                SELECT id, title, category,
                       cosine_distance(embedding, parse_json('{vector_str}')) AS distance
                FROM {DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}.documents
                ORDER BY distance
                LIMIT {TOP_K}
            """

            # Warmup phase
            if i < WARMUP_QUERIES:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    cursor.fetchall()
                continue

            # Measure phase
            iter_latencies = []
            for _ in range(NUM_ITERATIONS):
                start = time.perf_counter()
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    results = cursor.fetchall()
                elapsed = (time.perf_counter() - start) * 1000
                iter_latencies.append(elapsed)

            latencies.extend(iter_latencies)
    finally:
        conn.close()

    return latencies


# =============================================
# MAIN
# =============================================
def compute_stats(latencies: list[float]) -> dict:
    """Calculate latency statistics."""
    if not latencies:
        return {"error": "Nenhuma latência coletada"}
    
    arr = np.array(latencies)
    return {
        "count": len(arr),
        "mean_ms": round(np.mean(arr), 2),
        "median_ms": round(np.median(arr), 2),
        "p95_ms": round(np.percentile(arr, 95), 2),
        "p99_ms": round(np.percentile(arr, 99), 2),
        "min_ms": round(np.min(arr), 2),
        "max_ms": round(np.max(arr), 2),
        "std_ms": round(np.std(arr), 2),
    }


def main():
    print("=" * 70)
    print(" BENCHMARK DATABRICKS — VECTOR SEARCH")
    print(f" Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Host: {DATABRICKS_HOST}")
    print(f" Catálogo: {DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}")
    print(f" Top-K: {TOP_K} | Iterações por query: {NUM_ITERATIONS}")
    print("=" * 70)

    # Carregar documentos
    documents_path = DATA_DIR / "documents.json"
    if not documents_path.exists():
        print(f"\n❌ ERRO: Arquivo de documentos não encontrado: {documents_path}")
        print("   Execute primeiro: python scripts/02-generate-data.py")
        return

    print(f"\n📂 Carregando documentos...")
    with open(documents_path, "r", encoding="utf-8") as f:
        documents = json.load(f)
    print(f"   ✓ {len(documents)} documentos carregados")

    # Carregar queries
    queries_path = DATA_DIR / "queries.json"
    if not queries_path.exists():
        print(f"\n❌ ERRO: Arquivo de queries não encontrado: {queries_path}")
        print("   Execute primeiro: python scripts/02-generate-data.py")
        return

    print(f"\n📋 Carregando queries...")
    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)
    print(f"   ✓ {len(queries)} queries carregadas ({len(queries) - WARMUP_QUERIES} efetivas + {WARMUP_QUERIES} warmup)")

    # Setup: criar tabelas e carregar dados
    print(f"\n🔧 SETUP: Criando tabelas e carregando dados...")
    print(f"{'─' * 50}")
    if not setup_databricks_table(documents):
        print("❌ Falha no setup. Abortando benchmark.")
        return
    print(f"{'─' * 50}")

    services = {
        "Databricks Vector Search (REST API)": benchmark_databricks_rest,
        "Databricks SQL Warehouse": benchmark_databricks_sql,
    }

    all_results = {}

    for name, benchmark_fn in services.items():
        print(f"\n{'─' * 50}")
        print(f"  Executando: {name}...")
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
    print(" RESULTADOS DO BENCHMARK — DATABRICKS")
    print("=" * 70)

    # Tabela comparativa
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

    headers = ["Serviço", "Média (ms)", "Mediana (ms)", "P95 (ms)", "P99 (ms)", "Min-Max (ms)"]
    print("\n" + tabulate(table_data, headers=headers, tablefmt="grid"))

    # Ranking
    print("\n📊 RANKING (por latência média):")
    ranked = sorted(
        [(k, v) for k, v in all_results.items() if "error" not in v],
        key=lambda x: x[1]["mean_ms"],
    )
    if ranked:
        for i, (name, stats) in enumerate(ranked, 1):
            bar = "█" * max(1, int(stats["mean_ms"] / 5))
            print(f"  {i}º {name:<35} {stats['mean_ms']:>8.1f}ms  {bar}")
    else:
        print("  ⚠️  Nenhum resultado foi obtido")

    # Salvar resultados
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"benchmark_databricks_{timestamp}.json"
    output = {
        "timestamp": datetime.now().isoformat(),
        "platform": "Databricks",
        "config": {
            "databricks_host": DATABRICKS_HOST,
            "catalog": DATABRICKS_CATALOG,
            "schema": DATABRICKS_SCHEMA,
            "top_k": TOP_K,
            "num_iterations": NUM_ITERATIONS,
            "warmup_queries": WARMUP_QUERIES,
            "total_queries": len(queries),
        },
        "results": all_results,
    }
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n📁 Resultados salvos: {results_file}")
    print("\n✅ Benchmark Databricks concluído!")


if __name__ == "__main__":
    main()
