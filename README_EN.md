# Vector Search Benchmark

A comprehensive benchmark suite for evaluating vector search performance across Azure, Databricks, and Microsoft Fabric platforms. This project measures latency, throughput, and consistency of different vector search implementations with standardized datasets and metrics.

**Latest Results:** See [docs/RESULTS.md](docs/RESULTS.md) for the most recent benchmark runs.

## Features

- 🔬 **Multi-Platform Testing**: Azure (Core), Databricks (Native), Microsoft Fabric (Native)
- 📊 **Standardized Metrics**: Mean, Median, P95, P99, Min, Max, StdDev latencies
- 🔄 **Reproducible**: Fixed test datasets and query sets for consistent comparisons
- 📈 **Detailed Reports**: Markdown and CSV exports with visual rankings
- 🚀 **Production-Ready**: Handles large-scale vector datasets and concurrent operations
- 🛡️ **Enterprise Auth**: Entra ID integration for Azure services

## Platforms & Services Tested

### Azure (Core)
- **Azure AI Search** – Managed vector search with semantic ranking
- **Cosmos DB NoSQL** – Multi-model database with vector support
- **PostgreSQL pgvector** – Open-source vector extension
- **Azure SQL** – Relational database with VECTOR_DISTANCE function

### Databricks (Native)
- **Vector Search SDK** – Endpoint-based managed vector index
- **Spark SQL** – Cosine similarity via SQL

### Microsoft Fabric (Native)
- **SQL Endpoint** – T-SQL with VECTOR_DISTANCE('cosine')
- **Spark SQL** – Distributed cosine similarity calculation

## Quick Start

### Prerequisites

```bash
# Python 3.10+
python --version

# Required packages
pip install -r requirements.txt

# Azure CLI (for resource lookup)
az --version
```

### Environment Setup

```bash
# Copy template
cp .env.example .env

# Configure credentials (Entra ID will be auto-detected via DefaultAzureCredential)
# For Databricks:
export DATABRICKS_TOKEN=<your-token>
export DATABRICKS_HOST=<workspace-url>
export DATABRICKS_WAREHOUSE_ID=<warehouse-id>

# For Fabric (optional):
export FABRIC_SQL_ENDPOINT=<endpoint-hostname>
export FABRIC_CAPACITY=F64  # optional, for info only
```

### Run Benchmarks

#### 1. Generate Test Data

```bash
python scripts/02-generate-data.py
# Output: data/documents.json, data/queries.json
```

#### 2. Setup Infrastructure (First Time Only)

```bash
# Azure services
python scripts/01-create-resources.ps1  # PowerShell
python scripts/03-load-ai-search.py
python scripts/04-load-cosmosdb.py
python scripts/05-load-postgresql.py
python scripts/07-load-azuresql.py
```

#### 3. Run Benchmarks

**Option A: Local Execution**
```bash
# Azure services
python scripts/08-run-benchmark.py
```

**Option B: Native Notebook Execution (Recommended)**

For **Databricks**, run in a notebook cell:
```python
%run /path/to/10b-run-benchmark-databricks.py
```

For **Microsoft Fabric**, run in a notebook cell:
```python
%run /path/to/11-run-benchmark-fabric.py
```

#### 4. Consolidate & Analyze

```bash
python scripts/12-compare-all-platforms.py
# Output: Markdown report + CSV export in results/
```

## Project Structure

```
demo-vector-benchmark/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── config.json                        # Azure resource configuration
├── .env.example                       # Environment template
├── .gitignore
│
├── docs/
│   ├── SETUP.md                       # Detailed setup guide
│   ├── ARCHITECTURE.md                # Design & implementation details
│   ├── RESULTS.md                     # Latest benchmark results
│   └── TROUBLESHOOTING.md             # Common issues & solutions
│
├── scripts/
│   ├── 01-create-resources.ps1        # Provision Azure infrastructure
│   ├── 01b-configure-entra-auth.ps1   # Setup Entra ID authentication
│   ├── 02-generate-data.py            # Create synthetic vector dataset
│   ├── 03-load-ai-search.py           # Load data to Azure AI Search
│   ├── 04-load-cosmosdb.py            # Load data to Cosmos DB
│   ├── 05-load-postgresql.py          # Load data to PostgreSQL
│   ├── 07-load-azuresql.py            # Load data to Azure SQL
│   ├── 08-run-benchmark.py            # Azure core benchmarks
│   ├── 09-cleanup.ps1                 # Remove Azure resources
│   ├── 10-run-benchmark-databricks.py # Databricks benchmark (local)
│   ├── 10b-run-benchmark-databricks.py# Databricks benchmark (native)
│   ├── 11-run-benchmark-fabric.py     # Fabric benchmark (native)
│   └── 12-compare-all-platforms.py    # Consolidate & compare results
│
├── data/
│   ├── documents.json                 # Synthetic documents with embeddings
│   └── queries.json                   # Test queries with embeddings
│
└── results/
    ├── benchmark_azure_nativo_YYYYMMDD_HHMMSS.json
    ├── benchmark_databricks_nativo_YYYYMMDD_HHMMSS.json
    ├── benchmark_fabric_nativo_YYYYMMDD_HHMMSS.json
    ├── consolidated_results_YYYYMMDD_HHMMSS.csv
    └── REPORT_YYYYMMDD_HHMMSS.md
```

## Benchmark Methodology

### Test Dataset
- **1000 documents** with 1536-dimensional embeddings (compatible with OpenAI models)
- **100 test queries** with same embedding dimension
- **Document fields**: id, title, category, content

### Metrics
- **Top-K**: 10 results per query (configurable)
- **Iterations**: 3 warmup queries + 5 measured iterations per test
- **Latency**: End-to-end query execution time (ms)
- **Statistics**: Mean, Median, P95, P99, Min, Max, StdDev

### Test Flow
```
For each service:
  1. Warmup phase (discard first 3 queries for JIT compilation, caching)
  2. Measure phase (5 iterations per query × 100 queries)
  3. Calculate latency statistics
  4. Report results
```

## Output & Analysis

### Console Output
Real-time progress with per-service summary and platform ranking.

### JSON Results
```json
{
  "timestamp": "2026-06-19T15:30:45.123456",
  "platform": "Azure (Core)",
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
    "Azure AI Search": {
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

### Consolidated Report
- **Markdown**: Summary, rankings, insights, platform comparisons
- **CSV**: Tabular data for further analysis (Excel, Power BI, etc.)

## Performance Tips

### Azure AI Search
- Use `waitForIndexing=true` only in setup, not benchmarks
- Enable query debugging with `@search.debug=true` for analysis

### Cosmos DB
- Set `enableThroughputControl=true` for RU/s limiting
- Use indexing policy optimization for vector fields

### PostgreSQL
- Configure `hnsw.ef_search` (100-200 typically optimal)
- Ensure `pgvector` extension is properly installed
- Use `EXPLAIN` to verify index usage

### Azure SQL
- Benchmark with appropriate column statistics
- Use `VECTOR_DISTANCE('cosine')` for consistency

### Databricks
- Use SQL Warehouse with warm compute for stable latencies
- Vector Search SDK adds minimal overhead vs raw SQL

### Microsoft Fabric
- Lakehouse Spark execution requires active capacity
- SQL Endpoint provides T-SQL compatibility layer

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for:
- Authentication errors
- Connection timeouts
- Data loading failures
- Missing dependencies

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improvement`)
3. Make changes and test locally
4. Submit a pull request with description

### Guidelines
- Follow existing code style
- Add docstrings for new functions
- Update README/docs if adding features
- Test on multiple platforms if possible

## License

MIT License - see LICENSE file for details.

## Citation

If you use this benchmark in your research or blog, please cite:

```bibtex
@misc{vectorbench2026,
  title={Vector Search Benchmark Suite},
  author={Your Organization},
  year={2026},
  url={https://github.com/yourusername/demo-vector-benchmark}
}
```

## Support

- 📧 **Issues**: Open a GitHub issue for bugs or feature requests
- 💬 **Discussions**: Use GitHub Discussions for questions
- 📖 **Documentation**: See `docs/` folder for detailed guides

## Related Projects

- [Azure AI Search Documentation](https://learn.microsoft.com/en-us/azure/search/)
- [Databricks Vector Search](https://docs.databricks.com/en/generative-ai/vector-search.html)
- [Microsoft Fabric](https://learn.microsoft.com/en-us/fabric/)
- [pgvector](https://github.com/pgvector/pgvector)

---

**Last Updated**: June 19, 2026  
**Status**: Production Ready ✅
