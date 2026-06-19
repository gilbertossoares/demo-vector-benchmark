# Architecture & Design

## Overview

This document describes the design decisions, methodology, and technical architecture of the Vector Search Benchmark suite.

## Core Design Principles

1. **Reproducibility**: All tests use the same dataset, embeddings, and query set across all platforms
2. **Fairness**: Each platform is tested using its native, most-optimized API (not generic drivers)
3. **Comprehensiveness**: Test both simple queries and multi-step operations (setup, indexing, etc.)
4. **Extensibility**: Easy to add new platforms or services without restructuring core logic

## Test Methodology

### Dataset Characteristics

- **Documents**: 1,000 items with:
  - `id`: Unique identifier
  - `title`: Short text field
  - `category`: Classification (e.g., "technology", "finance")
  - `content`: Full text (200-500 words)
  - `embedding`: 1536-dimensional float vector

- **Queries**: 100 test queries with:
  - Same 1536-dimensional embedding space
  - Sampled from content of documents (ensuring relevant results exist)

- **Embedding Model**: OpenAI `text-embedding-3-small`
  - Dimension: 1536
  - Format: Normalized float arrays

### Performance Metrics

Each benchmark records:
- **Mean (µ)**: Average latency across all queries
- **Median (p50)**: Middle value (50th percentile)
- **P95**: 95th percentile latency (tail performance)
- **P99**: 99th percentile latency (extreme tail)
- **Min**: Best-case latency
- **Max**: Worst-case latency
- **StdDev (σ)**: Standard deviation (consistency indicator)

### Execution Pattern

```
Initialize Connection
  ↓
Load Data (from data/documents.json and data/queries.json)
  ↓
Setup Phase (create tables, indexes, collections)
  ↓
Warmup Phase (3 queries to prime caches, JIT compilation)
  ↓
Measure Phase (5 iterations × 100 queries = 500 total measurements)
  ↓
Calculate Statistics (mean, p95, p99, etc.)
  ↓
Output JSON Result
```

### Configuration Parameters

Defined in `config.json`:
```json
{
  "TOP_K": 10,              // Return top 10 most similar documents
  "NUM_ITERATIONS": 5,      // Run each query 5 times
  "WARMUP_QUERIES": 3,      // Discard first 3 queries for warm start
  "EMBEDDING_DIM": 1536,    // OpenAI embedding dimension
  "NUM_DOCUMENTS": 1000,    // Document count
  "REGION": "brazilsouth"   // Azure region for all services
}
```

## Platform-Specific Implementations

### Azure (Core) - `08-run-benchmark.py`

**Benchmarked Services:**
1. Azure AI Search
2. Cosmos DB NoSQL
3. PostgreSQL with pgvector
4. Azure SQL Database

**Authentication:** Azure SDK DefaultAzureCredential (supports MSI, Azure CLI, MSAL)

**Key Implementation Details:**

#### Azure AI Search
- Uses native SDK (`azure-search-documents`)
- Query type: Vector search with `search_type="similarityHybrid"`
- Vector field: Normalized cosine similarity
- Setup: Create index with vector field configuration

#### Cosmos DB NoSQL
- Native MongoDB API via SDK
- Vector search via aggregation pipeline with `$cosmosSearch`
- Returns ranking and similarity score
- Indexes: Automatic vector indexing policy

#### PostgreSQL pgvector
- Extension `pgvector` installed on database
- Query: `SELECT ... ORDER BY embedding <-> query_embedding LIMIT 10`
- Index: HNSW (`hnsw` method) for fast retrieval
- Connection: pyodbc with Entra ID authentication

#### Azure SQL Database
- Native `VECTOR_DISTANCE()` function (Preview feature)
- Distance metric: Cosine (`'cosine'`)
- Query: `SELECT TOP 10 ... ORDER BY VECTOR_DISTANCE('cosine', embedding, @query) DESC`
- Index: Heap or B-tree with optional full-text index

### Databricks - `10-run-benchmark-databricks.py`

**Two Implementation Approaches:**

#### 1. Vector Search SDK
- Managed index-as-a-service
- Query via REST API endpoint
- Highest-level abstraction
- Native Databricks solution

#### 2. Spark SQL
- Direct SQL queries on Delta tables
- Calculates cosine similarity in SQL
- More control, lower latency than SDK
- Standard SQL operations

**Dual Testing Rationale:**
- SDK: Represents managed vector database experience
- SQL: Represents custom search implementation
- Together: Show trade-off between convenience and performance

### Microsoft Fabric - `11-run-benchmark-fabric.py`

**Two Execution Modes:**

#### Mode 1: Notebook (Native Spark)
- Triggered when: `'spark' in dir()` (running in Fabric notebook)
- Uses PySpark native operations
- `spark.createDataFrame()` for table creation
- Spark SQL with TRANSFORM and AGGREGATE for cosine similarity
- Fastest execution within Fabric

#### Mode 2: SQL Endpoint (T-SQL)
- Triggered when: Running from local machine via ODBC
- Uses Microsoft.Data.SqlClient connection
- T-SQL syntax: `SELECT ... VECTOR_DISTANCE('cosine', embedding, @query) DESC`
- Compatible with Fabric SQL Endpoint or standalone Azure SQL

**Dual Mode Rationale:**
- Native: True Fabric performance (Spark-based computation)
- SQL: Compatibility mode (can run from external tools)

## Data Flow Architecture

```
┌─────────────────────────────────────┐
│   Generate Data (02-generate-data)  │
│   - Create 1000 documents           │
│   - Tokenize & embed with OpenAI    │
│   - Output: data/*.json             │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────────────────────────────────────────┐
        │                                                  │
        ▼                                                  ▼
┌───────────────────────────┐                ┌──────────────────────────┐
│ Load to Azure Services    │                │ Load to External Services│
│ (03-07: Parallel scripts) │                │ (Databricks/Fabric)     │
│ - AI Search               │                │ - Auto-loaded in script │
│ - Cosmos DB               │                │ - No separate load      │
│ - PostgreSQL              │                │ - Part of setup phase   │
│ - Azure SQL               │                │                         │
└───────────┬───────────────┘                └──────────┬──────────────┘
            │                                           │
            │                  ┌────────────────────────┘
            │                  │
            ▼                  ▼
    ┌──────────────────────────────────────┐
    │     Run Benchmarks (08, 10-11)      │
    │  - Load data from data/*.json        │
    │  - Execute setup phase               │
    │  - Run benchmark queries             │
    │  - Measure latencies                 │
    │  - Output: results/benchmark_*.json  │
    └──────────┬───────────────────────────┘
               │
               ▼
    ┌──────────────────────────────────────┐
    │   Consolidate Results (12)           │
    │  - Read all benchmark_*.json files   │
    │  - Compute rankings                  │
    │  - Generate markdown report          │
    │  - Export CSV for analysis           │
    └──────────────────────────────────────┘
```

## JSON Output Schema

All benchmark scripts output JSON with this structure:

```json
{
  "timestamp": "2026-06-19T15:30:45.123456",
  "platform": "Azure (Core)|Databricks (Nativo)|Microsoft Fabric (Nativo)",
  "execution_mode": "notebook|local|api",
  "config": {
    "region": "string",
    "top_k": 10,
    "num_iterations": 5,
    "warmup_queries": 3,
    "total_queries": 100,
    "embedding_dim": 1536,
    "num_documents": 1000
  },
  "results": {
    "ServiceName": {
      "count": integer,
      "mean_ms": float,
      "median_ms": float,
      "p95_ms": float,
      "p99_ms": float,
      "min_ms": float,
      "max_ms": float,
      "std_ms": float
    }
  }
}
```

## Error Handling Strategy

Each benchmark script implements:
1. **Service-level try-catch**: One failing service doesn't crash the entire benchmark
2. **Graceful degradation**: If a service is unavailable, it's skipped with a warning
3. **Detailed logging**: Error messages indicate what failed and why
4. **Partial results**: Return successful measurements even if some services fail

## Environment Detection

### Azure Services
- Uses `DefaultAzureCredential` (auto-detects: CLI, MSI, MSAL)
- Loads configuration from `config.json`
- Region derived from Azure resource names

### Databricks
- Detects via environment variables: `DATABRICKS_TOKEN`, `DATABRICKS_HOST`
- Local execution: Uses REST API to external workspace
- Notebook execution: Native Spark access via `spark` object

### Microsoft Fabric
- Detects via: `'spark' in dir()` (indicates running in Fabric notebook)
- Notebook mode: Direct Spark DataFrame operations
- Local mode: Uses pyodbc connection to SQL Endpoint

## Performance Optimization

### For Azure Services
- Warm connections before benchmark
- Reuse HTTP clients
- Batch operations where possible
- Pre-allocate embedding arrays

### For Databricks
- SQL Warehouse with warm compute enabled
- Vector Search endpoint pre-warmed
- Spark query caching enabled
- Minimize data serialization

### For Microsoft Fabric
- Spark pool pre-warmed (if available)
- SQL Endpoint connection pooled
- Query result caching disabled (to measure true latency)
- No unnecessary data movement between compute pools

## Scalability Considerations

### Current Configuration
- 1,000 documents: Representative of small-to-medium workloads
- 100 queries: Sufficient for statistical analysis (p95, p99)
- 5 iterations: Balance between confidence and runtime

### Scaling Up
To test larger datasets:
1. Modify `NUM_DOCUMENTS` in `config.json`
2. Re-run `02-generate-data.py` (will create larger files)
3. May require re-indexing in some services
4. Some services have tier/SKU limits (e.g., AI Search Basic)

### Scaling Down
For quick testing:
1. Reduce `NUM_ITERATIONS` to 1-2
2. Reduce `NUM_DOCUMENTS` to 100
3. Create separate `test-config.json` and load conditionally

## Consolidation & Analysis (`12-compare-all-platforms.py`)

### Features
1. **Load all results**: Scans `results/` directory for `benchmark_*.json` files
2. **Compute rankings**: Compares mean latency across platforms/methods
3. **Latest run summary**: Shows newest benchmark execution details
4. **Best method per platform**: Identifies fastest approach for each service
5. **Markdown report**: Human-readable comparison with formatting
6. **CSV export**: Machine-readable format for downstream analysis

### Output Files
- `REPORT_YYYYMMDD_HHMMSS.md` - Markdown with tables and rankings
- `consolidated_results_YYYYMMDD_HHMMSS.csv` - Flat CSV for Excel/Power BI

## Future Extensions

### Potential Additions
- [ ] Additional platforms: Pinecone, Weaviate, Milvus, Elasticsearch
- [ ] Batch operations: Measure throughput for bulk uploads
- [ ] Index building: Benchmark time to create indexes
- [ ] Filtering + vector: Combine metadata filters with vector search
- [ ] Concurrent clients: Load test with multiple simultaneous connections
- [ ] Cost analysis: Track $/query based on service pricing

### New Metrics
- Throughput (queries/second)
- Memory usage
- CPU utilization
- Index size
- Update latency (if documents change)

## References

- [Azure AI Search Vector Search](https://learn.microsoft.com/en-us/azure/search/vector-search-overview)
- [Cosmos DB Vector Search](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/vector-search)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [Azure SQL VECTOR_DISTANCE](https://learn.microsoft.com/en-us/sql/t-sql/functions/vector-distance-transact-sql)
- [Databricks Vector Search](https://docs.databricks.com/en/generative-ai/vector-search.html)
- [Microsoft Fabric Documentation](https://learn.microsoft.com/en-us/fabric/)

---

**Version**: 1.0  
**Last Updated**: June 19, 2026
