# Contributing to Vector Search Benchmark

Thank you for your interest in contributing! This document explains how to propose changes, report bugs, and improve the project.

## Code of Conduct

Be respectful, inclusive, and professional in all interactions. We follow the [Contributor Covenant](https://www.contributor-covenant.org/).

## Getting Started

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/demo-vector-benchmark.git
cd demo-vector-benchmark

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Optional: Install dev tools
pip install black pylint pytest
```

### Setting Up Test Environment

1. Configure `.env` with your credentials (see README.md)
2. For Azure: Run `scripts/01-create-resources.ps1`
3. For Databricks: Set environment variables
4. For Fabric: Set environment variables

## Contributing Workflow

### 1. Report a Bug

Open a GitHub Issue with:
- Clear title describing the problem
- Steps to reproduce
- Expected vs. actual behavior
- Environment info (OS, Python version, platform)
- Error messages/logs (sanitize credentials)

**Example:**
```
Title: Azure AI Search benchmark fails with connection timeout

Steps:
1. Run `python scripts/08-run-benchmark.py`
2. Observe timeout after 30 seconds

Expected: Query completes in <100ms
Actual: ConnectionTimeout exception

Environment:
- Windows 11
- Python 3.11
- Azure SDK 1.13
```

### 2. Propose a Feature

Open a GitHub Discussion or Issue with:
- Clear description of the feature
- Why it's useful
- Example use case
- Proposed implementation (if applicable)

**Example:**
```
Title: Add support for Elasticsearch vector search

Why: Popular open-source option, widely used in enterprise

Example use case:
"Compare managed services (Azure, Databricks) vs self-hosted (Elasticsearch)"

Proposed approach:
1. Create scripts/13-load-elasticsearch.py
2. Create scripts/13-run-benchmark-elasticsearch.py
3. Update consolidation script to include ES results
```

### 3. Submit a Pull Request

#### Step 1: Create a feature branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-number-description
```

#### Step 2: Make changes
- Keep commits atomic and focused
- Follow code style (see below)
- Update docstrings
- Add comments for complex logic

#### Step 3: Test locally
```bash
# Run your benchmark script
python scripts/XX-your-script.py

# Check for syntax errors
pylint scripts/XX-your-script.py

# Format code
black scripts/XX-your-script.py
```

#### Step 4: Commit with clear message
```bash
git add scripts/XX-your-script.py
git commit -m "feat: add Elasticsearch vector search benchmark"
```

Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`

#### Step 5: Push and create PR
```bash
git push origin feature/your-feature-name
```

Then open a PR on GitHub with:
- Clear title summarizing the change
- Description of what was changed and why
- Reference to related issues (#123)
- Any testing notes

## Code Style Guide

### Python Style

We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) with these conventions:

#### Naming
```python
# Variables and functions: snake_case
query_vector = load_embedding()
def calculate_cosine_similarity():
    pass

# Classes: PascalCase
class VectorSearchClient:
    pass

# Constants: UPPER_CASE
TOP_K = 10
EMBEDDING_DIM = 1536
```

#### Documentation
```python
def benchmark_service(service_name: str, queries: list) -> dict:
    """
    Run benchmark against a specific service.
    
    Args:
        service_name: Name of the service (e.g., 'Azure AI Search')
        queries: List of query embeddings as lists
    
    Returns:
        Dictionary with latency statistics:
        {
            'mean_ms': float,
            'median_ms': float,
            'p95_ms': float,
            ...
        }
    
    Raises:
        ConnectionError: If service is unreachable
        ValueError: If queries list is empty
    """
```

#### Comments
```python
# Use meaningful comments for non-obvious logic
# Bad:
x = y + 1  # Add one to y

# Good:
# Exclude first warmup query from latency calculation
measured_latencies = latencies[WARMUP_QUERIES:]
```

#### Line Length
- Maximum 100 characters per line
- Break long lines before operators

```python
# Good
result = (
    service.query(embedding, top_k=TOP_K)
    .filter(active=True)
    .limit(10)
)

# Avoid
result = service.query(embedding, top_k=TOP_K).filter(active=True).limit(10)
```

### Markdown Style

- Use ATX-style headers (`#`, `##`, not underlines)
- Provide code examples for complex concepts
- Include tables for comparisons
- Keep paragraphs concise (≤80 characters)

## Testing & Validation

### Before Submitting a PR

1. **Syntax check**: Code should import without errors
2. **Type hints**: Use type annotations for function arguments/returns
3. **Docstrings**: All functions must have docstrings
4. **Error handling**: Wrap external calls in try-except
5. **Logging**: Use print() for user messages, logging module for debug

### Testing New Benchmarks

```python
# Test with small dataset first
TEST_CONFIG = {
    "NUM_DOCUMENTS": 10,
    "TOP_K": 5,
    "NUM_ITERATIONS": 1,
    "WARMUP_QUERIES": 1
}
```

### Testing New Platforms

1. Create separate load script (e.g., `03-load-newservice.py`)
2. Create benchmark script (e.g., `13-run-benchmark-newservice.py`)
3. Follow existing pattern:
   - Load data from `data/documents.json` and `data/queries.json`
   - Implement `setup_phase()` function
   - Implement benchmark function returning latencies list
   - Calculate and output statistics as JSON
4. Test consolidation script includes new service

## Documentation

### When to Update Docs

- New platforms or services → Update README.md, ARCHITECTURE.md
- New configuration options → Update SETUP.md, config.json example
- New scripts or features → Add brief description to README.md
- Bug fixes → Update TROUBLESHOOTING.md if relevant
- New metrics or methodology → Update ARCHITECTURE.md

### Documentation Template

```markdown
### New Feature Name

**What it does:** Clear, one-line description

**When to use:** Specific scenarios or benefits

**Example:**
\`\`\`python
result = your_feature()
\`\`\`

**Related:**
- Link to relevant docs
- Link to issue/PR
```

## Adding New Platforms

Step-by-step guide for contributing a new platform:

1. **Create load script** (`scripts/XX-load-newplatform.py`)
   - Load `data/documents.json` and `data/queries.json`
   - Create indexes/tables/indexes as needed
   - Handle authentication
   - Print success message

2. **Create benchmark script** (`scripts/XX-run-benchmark-newplatform.py`)
   - Import necessary libraries
   - Implement `load_input_data()` to read JSON files
   - Implement `setup_phase()` to prepare service
   - Implement `benchmark_service()` function(s)
   - Calculate statistics using `compute_stats()`
   - Output JSON with platform field

3. **Update consolidation** (`scripts/12-compare-all-platforms.py`)
   - Add platform to results loading
   - Ensure JSON schema compatibility
   - Test with new results files

4. **Document your work**
   - Add entry to ARCHITECTURE.md platform list
   - Add setup instructions to SETUP.md
   - Update README.md Quick Start section

5. **Test thoroughly**
   - Run with test data (10 docs, 1 iteration)
   - Verify JSON output format
   - Check consolidation script includes results
   - Run with full dataset if possible

## Performance Considerations

When adding new code:
- Avoid O(n²) operations on large datasets
- Reuse connections/clients instead of creating per-query
- Benchmark critical sections
- Document performance implications

Example:
```python
# Good: Reuse connection
client = create_connection()
for query in queries:
    result = client.search(query)  # Reuses connection

# Avoid: Create new connection per query
for query in queries:
    client = create_connection()  # Expensive operation
    result = client.search(query)
```

## Security & Privacy

- Never commit `.env` files or credentials
- Sanitize error messages (remove URLs, account names)
- Use environment variables for sensitive data
- Follow Azure SDK security best practices

## Review Process

After you submit a PR:

1. **Automated checks** run (syntax, imports)
2. **Maintainer review** (usually within 1-2 weeks)
3. **Feedback & discussion** on any issues
4. **Approval & merge** once all comments addressed

## Getting Help

- **Questions?** Open a GitHub Discussion
- **Need guidance?** Comment on the issue
- **Stuck?** Ask in the PR - maintainers are happy to help

## Recognition

All contributors are recognized in:
- PR comments
- CONTRIBUTORS.md file
- Release notes

Thank you for contributing! 🎉

---

**Questions?** Open a GitHub Issue or Discussion.
