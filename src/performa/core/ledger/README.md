# DuckDB-Based Transactional Ledger

The ledger system is the heart of Performa's financial modeling engine, providing a unified, immutable, and auditable record-based system that serves as the single source of truth for all financial calculations.

## Architecture Overview

### High-Performance DuckDB Backend

The ledger system uses DuckDB as its storage engine, providing:

- **SQL-based queries** for complex financial analytics
- **In-memory processing** with optimized data types
- **Multi-threading support** utilizing all CPU cores
- **Transaction batching** for bulk operations
- **Strategic indexing** on common query patterns

### Key Components

- **`Ledger`**: Core DuckDB-based ledger with transaction batching
- **`LedgerQueries`**: Optimized SQL-based query interface for financial metrics
- **`TransactionRecord`**: Immutable transaction representation  
- **`SeriesMetadata`**: Type-safe metadata for Series conversion
- **`FlowPurposeMapper`**: Business logic for transaction classification

## Quick Start

### Basic Usage

```python
from performa.core.ledger import Ledger, LedgerQueries, SeriesMetadata
import pandas as pd

# Create ledger
ledger = Ledger()

# Add series with metadata
dates = pd.date_range('2024-01-01', periods=12, freq='M')
cash_flows = pd.Series([1000.0] * 12, index=dates)

metadata = SeriesMetadata(
    category=CashFlowCategoryEnum.REVENUE,
    subcategory=RevenueSubcategoryEnum.LEASE,
    item_name="Base Rent",
    source_id=uuid.uuid4(),
    asset_id=uuid.uuid4(),
    pass_num=1
)

ledger.add_series(cash_flows, metadata)

# Query the ledger
queries = LedgerQueries(ledger)
revenue = queries.pgr()  # Potential Gross Revenue
```

### Transaction Batching (Recommended)

For optimal performance with multiple series:

```python
# Use transaction context for batching
with ledger.transaction():
    for series, metadata in series_list:
        ledger.add_series(series, metadata)
    
    # Optional: flush mid-transaction for complex workflows
    ledger.flush()
    
    # More series...
    for series, metadata in more_series:
        ledger.add_series(series, metadata)

# All data committed automatically on context exit
```

## Performance Characteristics

### Optimized Data Storage

- **UUID types** for efficient identifier storage
- **DATE types** for temporal data (not TIMESTAMP when unnecessary)
- **DOUBLE precision** for financial calculations
- **TINYINT** for small integers (pass numbers, flags)
- **VARCHAR with appropriate lengths** for categorical data

### Query Performance

- **Strategic indexes** on date, category, and compound keys
- **Optimized joins** using proper foreign key relationships
- **Aggregation pushdown** to DuckDB's vectorized engine
- **Memory-efficient** result materialization

### Bulk Operations

- **Transaction batching** eliminates individual insert overhead
- **Bulk UUID generation** for efficient identifier creation
- **Pre-processed data structures** minimize Python/SQL marshaling
- **Automatic buffer management** with configurable limits

## Advanced Features

### Performance Analysis

```python
# Get query performance analyzer
analyzer = ledger.get_query_analyzer()

# Analyze common query patterns
metrics = analyzer.analyze_common_queries()
print(f"Average query time: {metrics.avg_execution_time_ms:.2f}ms")

# Profile specific queries
explain_result = analyzer.explain_query("SELECT * FROM transactions WHERE date >= '2024-01-01'")
```

### Memory Management

The ledger automatically configures DuckDB for optimal memory usage:

- **Dynamic thread allocation** based on available CPU cores
- **Configurable memory limits** via `DUCKDB_MEMORY_LIMIT` environment variable
- **Efficient cleanup** of temporary views and buffers
- **Memory monitoring** for large batch operations

### Data Export

```python
# Materialize full DataFrame for compatibility
df = ledger.to_dataframe()

# Export to various formats
ledger.con.execute("COPY transactions TO 'ledger.parquet' (FORMAT PARQUET)")
ledger.con.execute("COPY transactions TO 'ledger.csv' (HEADER)")
```

## Transaction Workflow

### Standard Workflow

1. **Create ledger** instance
2. **Add series** with proper metadata
3. **Query results** using LedgerQueries methods
4. **Materialize DataFrame** if needed for external tools

### Batched Workflow

1. **Start transaction** context
2. **Add multiple series** (buffered in memory)
3. **Optional flush** for complex dependency management
4. **Add more series** if needed
5. **Automatic commit** on context exit
6. **Query results** from committed data

## Financial Query Methods

The `LedgerQueries` class provides comprehensive financial analytics:

### Revenue Metrics
- `pgr()` - Potential Gross Revenue
- `gpr()` - Gross Potential Revenue  
- `tenant_revenue()` - Tenant-specific revenue
- `vacancy_loss()` - Vacancy and collection loss

### Expense Metrics
- `opex()` - Operating expenses
- `capex()` - Capital expenditures
- `ti()` - Tenant improvements
- `lc()` - Leasing commissions

### Net Operating Income
- `noi()` - Net Operating Income
- `egi()` - Effective Gross Income
- `operating_flows()` - All operating cash flows

### Financing & Returns
- `debt_service()` - Debt service payments
- `equity_contributions()` - Equity capital
- `ucf()` - Unlevered cash flow
- `distributions()` - Equity distributions

## Best Practices

### Metadata Management

Always provide all required metadata for accurate categorization:

```python
metadata = SeriesMetadata(
    category=CashFlowCategoryEnum.REVENUE,     # Required
    subcategory=RevenueSubcategoryEnum.LEASE,  # Required  
    item_name="Market Rate Rent - Unit 101",   # Descriptive
    source_id=lease_model.uid,                 # Source tracking
    asset_id=property.uid,                     # Asset linkage
    pass_num=1,                                # Calculation pass
    deal_id=deal.uid,                          # Optional: Deal context
    entity_id=entity.uid,                      # Optional: Entity context
    entity_type="Partnership"                  # Optional: Entity type
)
```

### Error Handling

```python
try:
    with ledger.transaction():
        for series, metadata in series_list:
            ledger.add_series(series, metadata)
except Exception as e:
    logger.error(f"Ledger transaction failed: {e}")
    # Transaction automatically rolled back
    raise
```

### Performance Tips

1. **Use transaction batching** for multiple series
2. **Filter zero values** before adding series (done automatically)
3. **Use appropriate data types** in metadata
4. **Monitor memory usage** for very large datasets
5. **Leverage indexes** by querying on date and category fields

## Integration

### With Performa Analysis

```python
from performa.analysis import run
from performa.core.ledger import Ledger

# The analysis engine automatically uses the ledger
ledger = Ledger()
result = run(deal_config, analysis_config, ledger_builder=ledger)

# Access the populated ledger
populated_ledger = result.ledger
queries = LedgerQueries(populated_ledger)
```

### With External Tools

```python
# Export for Argus/Excel compatibility
df = ledger.to_dataframe()
df.to_excel('financial_model.xlsx', index=False)

# Export for data science workflows  
parquet_data = ledger.con.execute("SELECT * FROM transactions").fetch_arrow_table()
```

This ledger system provides the foundation for comprehensive financial modeling while maintaining the performance and reliability required for professional real estate analysis.