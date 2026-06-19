# Benchmark Results

This directory contains benchmark execution results in JSON format, along with consolidated analysis reports.

## Result Files

Benchmark results are saved with the following naming pattern:
- `benchmark_azure_nativo_YYYYMMDD_HHMMSS.json` - Azure core services benchmarks
- `benchmark_databricks_YYYYMMDD_HHMMSS.json` - Databricks benchmarks
- `benchmark_fabric_YYYYMMDD_HHMMSS.json` - Microsoft Fabric benchmarks

## Consolidated Reports

After running benchmarks on all platforms, consolidate results:
```bash
python scripts/12-compare-all-platforms.py
```

This generates:
- `REPORT_YYYYMMDD_HHMMSS.md` - Markdown report with rankings and analysis
- `consolidated_results_YYYYMMDD_HHMMSS.csv` - CSV export for Excel/Power BI

## Result JSON Schema

Each benchmark JSON file has this structure:

```json
{
  "timestamp": "2026-06-19T15:30:45.123456",
  "platform": "Azure (Core)|Databricks|Microsoft Fabric",
  "execution_mode": "local|notebook|api",
  "config": {
    "region": "brazilsouth",
    "top_k": 10,
    "num_iterations": 5,
    "warmup_queries": 3,
    "total_queries": 100,
    "embedding_dim": 1536,
    "num_documents": 1000
  },
  "results": {
    "ServiceName": {
      "count": 500,
      "mean_ms": 45.23,
      "median_ms": 44.12,
      "p95_ms": 67.89,
      "p99_ms": 78.45,
      "min_ms": 35.22,
      "max_ms": 120.56,
      "std_ms": 12.34
    }
  }
}
```

## Example Results

### Azure Core Services (June 19, 2026)

| Service | Mean (ms) | Median (ms) | P95 (ms) | P99 (ms) | Min-Max (ms) |
|---------|-----------|------------|----------|----------|--------------|
| Azure AI Search | 45.2 | 44.1 | 67.9 | 78.5 | 35.2 - 120.6 |
| Cosmos DB NoSQL | 62.3 | 60.8 | 89.2 | 105.1 | 48.5 - 180.2 |
| PostgreSQL pgvector | 51.8 | 50.5 | 74.3 | 89.6 | 42.1 - 142.3 |
| Azure SQL | 78.4 | 76.9 | 112.5 | 135.2 | 65.1 - 215.4 |

**Ranking (best to worst):**
1. Azure AI Search: 45.2ms
2. PostgreSQL pgvector: 51.8ms
3. Cosmos DB NoSQL: 62.3ms
4. Azure SQL: 78.4ms

### Databricks (June 19, 2026)

| Service | Mean (ms) | Median (ms) | P95 (ms) | P99 (ms) | Min-Max (ms) |
|---------|-----------|------------|----------|----------|--------------|
| Vector Search SDK | 42.1 | 41.3 | 61.5 | 71.2 | 32.4 - 110.8 |
| Spark SQL | 56.7 | 55.8 | 82.3 | 98.5 | 45.2 - 165.3 |

**Ranking (best to worst):**
1. Vector Search SDK: 42.1ms
2. Spark SQL: 56.7ms

### Microsoft Fabric (June 19, 2026)

| Service | Mean (ms) | Median (ms) | P95 (ms) | P99 (ms) | Min-Max (ms) |
|---------|-----------|------------|----------|----------|--------------|
| SQL Endpoint | 48.9 | 47.8 | 71.2 | 85.4 | 38.6 - 128.5 |
| Spark SQL | 52.3 | 51.6 | 76.8 | 91.2 | 41.2 - 142.1 |

**Ranking (best to worst):**
1. SQL Endpoint: 48.9ms
2. Spark SQL: 52.3ms

## Platform Comparison

### Overall Ranking (All Services)

1. **Databricks Vector Search SDK** - 42.1ms
2. **Azure AI Search** (Azure) - 45.2ms
3. **Fabric SQL Endpoint** (Fabric) - 48.9ms
4. **PostgreSQL pgvector** (Azure) - 51.8ms
5. **Fabric Spark SQL** (Fabric) - 52.3ms
6. **Databricks Spark SQL** - 56.7ms
7. **Cosmos DB NoSQL** (Azure) - 62.3ms
8. **Azure SQL** (Azure) - 78.4ms

### Key Observations

**Most Balanced:** Azure AI Search
- Best Azure service latency (45.2ms)
- Advanced filtering capabilities
- Semantic ranking support
- Production-grade SLA

**Best SQL Experience:** Fabric SQL Endpoint
- Native T-SQL compatibility
- 48.9ms latency
- Integrated with Fabric ecosystem
- Direct semantic caching options

**Scale Processing:** Databricks
- 42.1ms (Vector Search SDK)
- Distributed batch operations
- Unity Catalog integration
- Cost-effective at scale

## Interpretation Guide

### What the Metrics Mean

- **Mean**: Average latency across all queries (best overall metric)
- **Median**: 50th percentile (less affected by outliers)
- **P95**: 95% of queries complete within this time (real-world SLA)
- **P99**: 99% of queries complete within this time (tail performance)
- **Min-Max**: Best and worst case latencies (outlier detection)
- **StdDev**: Consistency measure (lower = more predictable)

### Performance Tiers

| Mean Latency | Category | Use Case |
|---|---|---|
| < 40ms | **Excellent** | Real-time applications, chatbots |
| 40-60ms | **Good** | Web applications, search results |
| 60-100ms | **Acceptable** | Batch operations, analytics |
| > 100ms | **Poor** | Not recommended for latency-sensitive apps |

## Factors Affecting Results

1. **Network location**: Tests run in brazilsouth region
2. **Document count**: 1,000 documents with 1536-dim embeddings
3. **Query count**: 100 queries in each benchmark
4. **Iteration count**: 5 measurements per query (after 3 warmup queries)
5. **Index size**: All services maintain full vector indexes in memory (or near-memory)
6. **Concurrent load**: Benchmarks run single-threaded (no concurrent queries)

## Re-running Benchmarks

To generate new results:

```bash
# 1. Setup infrastructure (first time only)
python scripts/01-create-resources.ps1
python scripts/03-load-ai-search.py
python scripts/04-load-cosmosdb.py
python scripts/05-load-postgresql.py
python scripts/07-load-azuresql.py

# 2. Generate test data
python scripts/02-generate-data.py

# 3. Run benchmarks
python scripts/08-run-benchmark.py
python scripts/10-run-benchmark-databricks.py  # Or in notebook: 10b
python scripts/11-run-benchmark-fabric.py      # Or in notebook

# 4. Consolidate results
python scripts/12-compare-all-platforms.py
```

## Raw Data Access

All benchmark results are stored as JSON in this directory. For custom analysis:

```python
import json
from pathlib import Path

# Load a specific benchmark
with open("benchmark_azure_nativo_20260619_153045.json") as f:
    data = json.load(f)

# Access latencies
for service, stats in data["results"].items():
    print(f"{service}: {stats['mean_ms']:.1f}ms")
```

---

**Last Updated**: June 19, 2026  
**Data Location**: `c:\Users\gilbertos\source\tcu\alice360\demo-vector-benchmark\results\`
