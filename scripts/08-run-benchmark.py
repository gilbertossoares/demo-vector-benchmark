"""
Vector Search Benchmark — Azure (Core)
Executes vector search benchmarks across Azure services.

Services tested:
    1. Azure AI Search
    2. Cosmos DB NoSQL
    3. PostgreSQL pgvector
    4. Azure SQL (VECTOR_DISTANCE cosine)
"""

import json
import os
import struct
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from tabulate import tabulate
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential

load_dotenv()

# --- Configuration ---
config_path = Path(__file__).parent.parent / "config.json"
with open(config_path) as f:
    config = json.load(f)

DATA_DIR = Path(__file__).parent.parent / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

TOP_K = 10  # Number of results per query
NUM_ITERATIONS = 5  # Repetitions per query to stabilize metrics
WARMUP_QUERIES = 3  # Warmup queries (discarded)
EMBEDDING_DIM = 1536

SQL_COPT_SS_ACCESS_TOKEN = 1256


def get_credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


def get_pg_access_token(credential: DefaultAzureCredential) -> str:
    return credential.get_token("https://ossrdbms-aad.database.windows.net/.default").token


def get_sql_access_token_struct(credential: DefaultAzureCredential) -> bytes:
    token = credential.get_token("https://database.windows.net/.default").token
    token_bytes = token.encode("utf-16-le")
    return struct.pack("<I", len(token_bytes)) + token_bytes


# =============================================
# AZURE AI SEARCH
# =============================================
def benchmark_ai_search(queries: list[dict]) -> list[float]:
    """Execute benchmark on Azure AI Search."""
    from azure.search.documents import SearchClient
    from azure.search.documents.models import VectorizedQuery
    credential = get_credential()

    search_name = config["ai_search_name"]
    endpoint = f"https://{search_name}.search.windows.net"

    client = SearchClient(
        endpoint=endpoint,
        index_name="vector-benchmark",
        credential=credential,
    )

    latencies = []
    for i, query in enumerate(queries):
        vector_query = VectorizedQuery(
            vector=query["embedding"],
            k_nearest_neighbors=TOP_K,
            fields="embedding",
        )
        # Warmup phase
        if i < WARMUP_QUERIES:
            client.search(search_text=None, vector_queries=[vector_query], top=TOP_K)
            continue

        # Measure phase
        iter_latencies = []
        for _ in range(NUM_ITERATIONS):
            start = time.perf_counter()
            results = list(client.search(
                search_text=None,
                vector_queries=[vector_query],
                top=TOP_K,
            ))
            elapsed = (time.perf_counter() - start) * 1000  # milliseconds
            iter_latencies.append(elapsed)

        latencies.extend(iter_latencies)

    return latencies


# =============================================
# AZURE COSMOS DB (NoSQL)
# =============================================
def benchmark_cosmosdb(queries: list[dict]) -> list[float]:
    """Execute benchmark on Cosmos DB for NoSQL."""
    from azure.cosmos import CosmosClient
    credential = get_credential()

    cosmos_name = config["cosmos_name"]
    endpoint = f"https://{cosmos_name}.documents.azure.com:443/"

    client = CosmosClient(endpoint, credential=credential)
    container = client.get_database_client("vectordb").get_container_client("documents")

    latencies = []
    for i, query in enumerate(queries):
        # Cosmos DB vector search query
        query_text = """
            SELECT TOP @top c.id, c.title, c.category,
                   VectorDistance(c.embedding, @embedding) AS score
            FROM c
            ORDER BY VectorDistance(c.embedding, @embedding)
        """
        parameters = [
            {"name": "@top", "value": TOP_K},
            {"name": "@embedding", "value": query["embedding"]},
        ]

        # Warmup phase
        if i < WARMUP_QUERIES:
            list(container.query_items(query_text, parameters=parameters, enable_cross_partition_query=True))
            continue

        # Measure phase
        iter_latencies = []
        for _ in range(NUM_ITERATIONS):
            start = time.perf_counter()
            results = list(container.query_items(
                query_text,
                parameters=parameters,
                enable_cross_partition_query=True,
            ))
            elapsed = (time.perf_counter() - start) * 1000
            iter_latencies.append(elapsed)

        latencies.extend(iter_latencies)

    return latencies


# =============================================
# POSTGRESQL (pgvector)
# =============================================
def benchmark_postgresql(queries: list[dict]) -> list[float]:
    """Execute benchmark on PostgreSQL with pgvector."""
    import psycopg2

    credential = get_credential()
    pg_user = os.getenv("AZURE_PG_ENTRA_USER", "")
    if not pg_user:
        raise ValueError("Set AZURE_PG_ENTRA_USER in .env for PostgreSQL Entra ID authentication.")

    pg_token = get_pg_access_token(credential)

    pg_host = f"{config['pg_name']}.postgres.database.azure.com"
    conn = psycopg2.connect(
        host=pg_host,
        database="postgres",
        user=pg_user,
        password=pg_token,
        sslmode="require",
    )

    # Configure ef_search for HNSW
    with conn.cursor() as cur:
        cur.execute("SET hnsw.ef_search = 100;")

    latencies = []
    for i, query in enumerate(queries):
        embedding_str = str(query["embedding"])

        # Warmup phase
        if i < WARMUP_QUERIES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, category, embedding <=> %s::vector AS distance "
                    "FROM documents ORDER BY embedding <=> %s::vector LIMIT %s",
                    (embedding_str, embedding_str, TOP_K),
                )
                cur.fetchall()
            continue

        # Measure phase
        iter_latencies = []
        for _ in range(NUM_ITERATIONS):
            start = time.perf_counter()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, category, embedding <=> %s::vector AS distance "
                    "FROM documents ORDER BY embedding <=> %s::vector LIMIT %s",
                    (embedding_str, embedding_str, TOP_K),
                )
                results = cur.fetchall()
            elapsed = (time.perf_counter() - start) * 1000
            iter_latencies.append(elapsed)

        latencies.extend(iter_latencies)

    conn.close()
    return latencies


# =============================================
# AZURE SQL DATABASE (Vector Preview)
# =============================================
def benchmark_azuresql(queries: list[dict]) -> list[float]:
    """Execute benchmark on Azure SQL Database."""
    import pyodbc

    credential = get_credential()
    token_struct = get_sql_access_token_struct(credential)

    server = f"{config['sql_server_name']}.database.windows.net"
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};DATABASE={config['sql_db_name']};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    conn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})

    latencies = []
    for i, query in enumerate(queries):
        embedding_json = json.dumps(query["embedding"])

        sql = f"""
            SELECT TOP {TOP_K} id, title, category,
                   VECTOR_DISTANCE('cosine', embedding, CAST(CONVERT(VARCHAR(MAX), ?) AS VECTOR(1536))) AS distance
            FROM documents
            ORDER BY VECTOR_DISTANCE('cosine', embedding, CAST(CONVERT(VARCHAR(MAX), ?) AS VECTOR(1536)))
        """

        # Warmup phase
        if i < WARMUP_QUERIES:
            cursor = conn.cursor()
            cursor.execute(sql, embedding_json, embedding_json)
            cursor.fetchall()
            continue

        # Measure phase
        iter_latencies = []
        for _ in range(NUM_ITERATIONS):
            start = time.perf_counter()
            cursor = conn.cursor()
            cursor.execute(sql, embedding_json, embedding_json)
            results = cursor.fetchall()
            elapsed = (time.perf_counter() - start) * 1000
            iter_latencies.append(elapsed)

        latencies.extend(iter_latencies)

    conn.close()
    return latencies


# =============================================
# MAIN
# =============================================
def load_input_data() -> tuple[list[dict], list[dict]]:
    """Load documents and input queries."""
    documents_path = DATA_DIR / "documents.json"
    queries_path = DATA_DIR / "queries.json"

    if not documents_path.exists():
        raise FileNotFoundError(f"Documents file not found: {documents_path}")
    if not queries_path.exists():
        raise FileNotFoundError(f"Queries file not found: {queries_path}")

    with open(documents_path, "r", encoding="utf-8") as f:
        documents = json.load(f)
    with open(queries_path, "r", encoding="utf-8") as f:
        queries = json.load(f)

    return documents, queries


def setup_phase(documents: list[dict]) -> bool:
    """
    Setup phase to maintain standard with other benchmarks.
    In this runner, assumes services are already loaded via scripts 03-07.
    """
    _ = documents
    print("  ✓ Setup: data already provisioned in services (scripts 03-07)")
    return True


def compute_stats(latencies: list[float]) -> dict:
    """Calculate latency statistics."""
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


def main():
    print("=" * 70)
    print(" BENCHMARK AZURE — VECTOR SEARCH (Core)")
    print(f" Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Region: Brazil South")
    print(f" Top-K: {TOP_K} | Iterations per query: {NUM_ITERATIONS}")
    print("=" * 70)

    print("\n1) Loading data...")
    try:
        documents, queries = load_input_data()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("   Run first: python scripts/02-generate-data.py")
        return

    print(f"   ✓ {len(documents)} documents loaded")
    print(
        f"   ✓ {len(queries)} queries loaded "
        f"({len(queries) - WARMUP_QUERIES} effective + {WARMUP_QUERIES} warmup)"
    )

    print("\n2) Setup...")
    print("─" * 50)
    if not setup_phase(documents):
        print("❌ Setup failed. Aborting benchmark.")
        return
    print("─" * 50)

    services = {
        "Azure AI Search": benchmark_ai_search,
        "Cosmos DB NoSQL": benchmark_cosmosdb,
        "PostgreSQL pgvector": benchmark_postgresql,
        "Azure SQL (Preview)": benchmark_azuresql,
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
                print(
                    f"  ✓ Média: {stats['mean_ms']:.1f}ms | "
                    f"P95: {stats['p95_ms']:.1f}ms | P99: {stats['p99_ms']:.1f}ms"
                )
            else:
                all_results[name] = {"error": "Nenhuma latência coletada"}
                print("  ⚠️  Não foi possível executar o teste")
        except Exception as e:
            print(f"  ✗ ERRO: {e}")
            all_results[name] = {"error": str(e)}

    # --- Relatório ---
    print("\n")
    print("=" * 70)
    print(" RESULTADOS DO BENCHMARK")
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
    for i, (name, stats) in enumerate(ranked, 1):
        bar = "█" * max(1, int(stats["mean_ms"] / 5))
        print(f"  {i}º {name:<25} {stats['mean_ms']:>8.1f}ms  {bar}")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"benchmark_azure_nativo_{timestamp}.json"
    output = {
        "timestamp": datetime.now().isoformat(),
        "platform": "Azure (Core)",
        "config": {
            "execution_mode": "local",
            "region": "brazilsouth",
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

    print(f"\n📁 Results saved: {results_file}")
    print("\n✅ Benchmark completed!")


if __name__ == "__main__":
    main()
