# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
DuckDB Query Performance Analysis Utilities.

This module provides utilities for analyzing and optimizing DuckDB queries
using EXPLAIN ANALYZE and performance profiling capabilities.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import duckdb

logger = logging.getLogger(__name__)


@dataclass
class QueryPerformanceMetrics:
    """Performance metrics extracted from EXPLAIN ANALYZE output."""
    
    query: str
    total_time_ms: float
    rows_processed: int
    has_seq_scan: bool
    has_index_usage: bool
    bottleneck_operations: List[str]
    recommendations: List[str]


@dataclass
class IndexRecommendation:
    """Recommendation for creating a database index."""
    
    table_name: str
    columns: List[str]
    reason: str
    estimated_improvement: str


class DuckDBQueryAnalyzer:
    """
    Performance analysis tool for DuckDB queries.
    
    This class provides utilities to analyze query performance, identify
    bottlenecks, and recommend optimizations using DuckDB's EXPLAIN ANALYZE
    functionality.
    
    Example:
        ```python
        analyzer = DuckDBQueryAnalyzer(connection)
        metrics = analyzer.analyze_query("SELECT * FROM transactions WHERE date > '2024-01-01'")
        print(f"Query took {metrics.total_time_ms}ms")
        for rec in metrics.recommendations:
            print(f"Recommendation: {rec}")
        ```
    """
    
    def __init__(self, connection: duckdb.DuckDBPyConnection):
        """
        Initialize the query analyzer.
        
        Args:
            connection: Active DuckDB connection to analyze
        """
        self.con = connection
        
    def analyze_query(self, query: str) -> QueryPerformanceMetrics:
        """
        Analyze a query using EXPLAIN ANALYZE and extract performance metrics.
        
        Args:
            query: SQL query to analyze
            
        Returns:
            Performance metrics and optimization recommendations
        """
        try:
            # Execute EXPLAIN ANALYZE
            explain_query = f"EXPLAIN ANALYZE {query}"
            result = self.con.execute(explain_query).fetchall()
            
            # Parse the execution plan
            execution_plan = [row[0] for row in result]
            
            return self._parse_execution_plan(query, execution_plan)
            
        except Exception as e:
            logger.error(f"Failed to analyze query: {e}")
            return QueryPerformanceMetrics(
                query=query,
                total_time_ms=0.0,
                rows_processed=0,
                has_seq_scan=True,
                has_index_usage=False,
                bottleneck_operations=[],
                recommendations=[f"Query analysis failed: {e}"]
            )
    
    def _parse_execution_plan(self, query: str, plan_lines: List[str]) -> QueryPerformanceMetrics:
        """
        Parse EXPLAIN ANALYZE output to extract performance metrics.
        
        Args:
            query: Original SQL query
            plan_lines: Lines from EXPLAIN ANALYZE output
            
        Returns:
            Parsed performance metrics
        """
        total_time_ms = 0.0
        rows_processed = 0
        has_seq_scan = False
        has_index_usage = False
        bottleneck_operations = []
        recommendations = []
        
        for line in plan_lines:
            line_upper = line.upper()
            
            # Extract timing information
            time_match = re.search(r'(\d+\.?\d*)\s*MS', line_upper)
            if time_match:
                time_val = float(time_match.group(1))
                total_time_ms = max(total_time_ms, time_val)
            
            # Extract row counts
            rows_match = re.search(r'(\d+)\s*ROWS', line_upper)
            if rows_match:
                rows_processed = max(rows_processed, int(rows_match.group(1)))
            
            # Detect sequential scans (performance concern)
            if 'SEQ_SCAN' in line_upper or 'SEQUENTIAL_SCAN' in line_upper:
                has_seq_scan = True
                if 'transactions' in line.lower():
                    recommendations.append("Consider adding indexes on frequently filtered columns")
            
            # Detect index usage (good for performance)
            if 'INDEX_SCAN' in line_upper or 'INDEX' in line_upper:
                has_index_usage = True
            
            # Identify potentially slow operations
            if any(op in line_upper for op in ['HASH_GROUP_BY', 'SORT', 'FILTER', 'JOIN']):
                if time_match and float(time_match.group(1)) > 10.0:  # >10ms operations
                    operation = self._extract_operation_name(line)
                    if operation:
                        bottleneck_operations.append(operation)
        
        # Generate specific recommendations based on analysis
        if has_seq_scan and not has_index_usage:
            recommendations.append("Query is using sequential scans - consider adding strategic indexes")
        
        if total_time_ms > 100.0:  # Slow query threshold
            recommendations.append("Query is slow - consider query optimization or additional indexes")
        
        if 'GROUP BY' in query.upper() and has_seq_scan:
            recommendations.append("GROUP BY queries benefit from indexes on grouping columns")
        
        if 'WHERE' in query.upper() and has_seq_scan:
            recommendations.append("WHERE clause filtering would benefit from indexes on filtered columns")
        
        return QueryPerformanceMetrics(
            query=query,
            total_time_ms=total_time_ms,
            rows_processed=rows_processed,
            has_seq_scan=has_seq_scan,
            has_index_usage=has_index_usage,
            bottleneck_operations=bottleneck_operations,
            recommendations=recommendations if recommendations else ["Query appears to be well-optimized"]
        )
    
    def _extract_operation_name(self, plan_line: str) -> Optional[str]:
        """Extract operation name from an execution plan line."""
        # Simple extraction - could be enhanced with more sophisticated parsing
        operations = ['HASH_GROUP_BY', 'SORT', 'FILTER', 'JOIN', 'SEQ_SCAN', 'INDEX_SCAN']
        for op in operations:
            if op in plan_line.upper():
                return op
        return None
    
    def recommend_indexes(self, table_name: str, common_queries: List[str]) -> List[IndexRecommendation]:
        """
        Analyze common queries and recommend indexes for optimization.
        
        Args:
            table_name: Name of the table to analyze
            common_queries: List of frequently executed queries
            
        Returns:
            List of index recommendations
        """
        recommendations = []
        
        for query in common_queries:
            query_upper = query.upper()
            
            # Analyze WHERE clauses for index opportunities
            if 'WHERE' in query_upper:
                # Simple pattern matching - could be enhanced with proper SQL parsing
                if 'DATE' in query_upper and ('>' in query or '<' in query or 'BETWEEN' in query_upper):
                    recommendations.append(IndexRecommendation(
                        table_name=table_name,
                        columns=['date'],
                        reason="Range queries on date column detected",
                        estimated_improvement="2-10x faster for date filtering"
                    ))
                
                if 'CATEGORY' in query_upper and '=' in query:
                    recommendations.append(IndexRecommendation(
                        table_name=table_name,
                        columns=['category'],
                        reason="Equality filtering on category detected",
                        estimated_improvement="5-20x faster for category filtering"
                    ))
            
            # Analyze GROUP BY clauses
            if 'GROUP BY' in query_upper:
                if 'DATE' in query_upper and 'CATEGORY' in query_upper:
                    recommendations.append(IndexRecommendation(
                        table_name=table_name,
                        columns=['date', 'category'],
                        reason="GROUP BY on date and category detected",
                        estimated_improvement="3-15x faster for grouped aggregations"
                    ))
        
        # Remove duplicates based on columns
        unique_recommendations = []
        seen_columns = set()
        for rec in recommendations:
            col_key = tuple(sorted(rec.columns))
            if col_key not in seen_columns:
                unique_recommendations.append(rec)
                seen_columns.add(col_key)
        
        return unique_recommendations
    
    def profile_query_performance(self, query: str, iterations: int = 5) -> Dict[str, Any]:
        """
        Profile a query's performance over multiple iterations.
        
        Args:
            query: SQL query to profile
            iterations: Number of times to execute the query
            
        Returns:
            Dictionary containing performance statistics
        """
        import time
        
        execution_times = []
        
        for i in range(iterations):
            start_time = time.perf_counter()
            try:
                result = self.con.execute(query).fetchall()
                end_time = time.perf_counter()
                execution_times.append((end_time - start_time) * 1000)  # Convert to milliseconds
            except Exception as e:
                logger.error(f"Query execution {i + 1} failed: {e}")
                continue
        
        if not execution_times:
            return {"error": "All query executions failed"}
        
        avg_time = sum(execution_times) / len(execution_times)
        min_time = min(execution_times)
        max_time = max(execution_times)
        
        return {
            "query": query,
            "iterations": len(execution_times),
            "avg_time_ms": avg_time,
            "min_time_ms": min_time,
            "max_time_ms": max_time,
            "execution_times_ms": execution_times,
            "performance_variance": (max_time - min_time) / avg_time if avg_time > 0 else 0
        }
    
    def enable_profiling(self) -> None:
        """Enable DuckDB query profiling for detailed performance analysis."""
        try:
            self.con.execute("SET enable_profiling = true")
            self.con.execute("SET profiling_output = 'query_profile.json'")
            logger.info("DuckDB profiling enabled")
        except Exception as e:
            logger.warning(f"Could not enable profiling: {e}")
    
    def disable_profiling(self) -> None:
        """Disable DuckDB query profiling."""
        try:
            self.con.execute("SET enable_profiling = false")
            logger.info("DuckDB profiling disabled")
        except Exception as e:
            logger.warning(f"Could not disable profiling: {e}")
