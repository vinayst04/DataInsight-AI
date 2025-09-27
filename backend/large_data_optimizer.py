import pandas as pd
import sqlite3
from sqlalchemy import create_engine, text
import json
import time
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from datetime import datetime
import threading
import queue
import io
import base64
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

class LargeDatasetOptimizer:
    """Enterprise-grade optimizer for handling large datasets (1K-10K+ records)"""
    
    def __init__(self, engine):
        self.engine = engine
        self.cache = {}
        self.performance_metrics = {}
        
        # Configuration for different dataset sizes
        self.size_thresholds = {
            'small': 50,           # ≤50 records: Show all
            'medium': 1000,        # 51-1000 records: Smart sampling
            'large': 10000,        # 1001-10000 records: Advanced optimization
            'enterprise': 50000    # 10001+ records: Enterprise strategies
        }
        
    def classify_dataset_size(self, row_count: int) -> str:
        """Classify dataset size for optimal processing strategy"""
        if row_count <= self.size_thresholds['small']:
            return 'small'
        elif row_count <= self.size_thresholds['medium']:
            return 'medium'
        elif row_count <= self.size_thresholds['large']:
            return 'large'
        else:
            return 'enterprise'
    
    def get_dataset_info(self, table_name: str) -> Dict:
        """Get comprehensive dataset information for optimization"""
        with self.engine.connect() as conn:
            # Get row count
            count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            row_count = count_result.fetchone()[0]
            
            # Get column info
            columns_result = conn.execute(text(f"PRAGMA table_info({table_name})"))
            columns_info = columns_result.fetchall()
            
            # Identify numeric and text columns for smart processing
            numeric_columns = []
            text_columns = []
            date_columns = []
            
            for col_info in columns_info:
                col_name = col_info[1]
                col_type = col_info[2].upper()
                
                if any(t in col_type for t in ['INT', 'REAL', 'NUMERIC', 'DECIMAL', 'FLOAT']):
                    numeric_columns.append(col_name)
                elif any(t in col_type for t in ['TEXT', 'VARCHAR', 'CHAR']):
                    text_columns.append(col_name)
                elif any(t in col_type for t in ['DATE', 'TIME']):
                    date_columns.append(col_name)
                else:
                    text_columns.append(col_name)  # Default to text
            
            return {
                'row_count': row_count,
                'size_category': self.classify_dataset_size(row_count),
                'columns': [col[1] for col in columns_info],
                'numeric_columns': numeric_columns,
                'text_columns': text_columns,
                'date_columns': date_columns,
                'total_columns': len(columns_info)
            }
    
    def optimize_query_for_large_data(self, base_query: str, dataset_info: Dict, user_intent: str) -> Dict:
        """Generate optimized query strategy based on dataset size and user intent"""
        size_category = dataset_info['size_category']
        row_count = dataset_info['row_count']
        
        if size_category == 'small':
            # Small datasets: return all data
            return {
                'strategy': 'full_dataset',
                'query': base_query,
                'limit': None,
                'sampling': None,
                'pagination': False
            }
        
        elif size_category == 'medium':
            # Medium datasets: intelligent sampling
            return self._medium_dataset_strategy(base_query, dataset_info, user_intent)
            
        elif size_category == 'large':
            # Large datasets: advanced optimization
            return self._large_dataset_strategy(base_query, dataset_info, user_intent)
            
        else:  # enterprise
            # Enterprise datasets: maximum optimization
            return self._enterprise_dataset_strategy(base_query, dataset_info, user_intent)
    
    def _medium_dataset_strategy(self, base_query: str, dataset_info: Dict, user_intent: str) -> Dict:
        """Strategy for medium datasets (51-1000 records)"""
        intent_lower = user_intent.lower()
        
        # If user wants everything, provide paginated approach
        if any(word in intent_lower for word in ['all', 'complete', 'everything', 'full']):
            return {
                'strategy': 'smart_pagination',
                'query': base_query,
                'limit': 100,  # Show 100 at a time
                'sampling': None,
                'pagination': True,
                'page_size': 100
            }
        
        # For analysis requests, use representative sampling
        elif any(word in intent_lower for word in ['analyze', 'trend', 'pattern', 'insight']):
            return {
                'strategy': 'representative_sampling',
                'query': self._add_smart_sampling(base_query, dataset_info, sample_size=200),
                'limit': 200,
                'sampling': 'systematic',
                'pagination': False
            }
        
        # Default: intelligent top results
        else:
            return {
                'strategy': 'intelligent_top',
                'query': self._add_intelligent_ordering(base_query, dataset_info) + " LIMIT 50",
                'limit': 50,
                'sampling': None,
                'pagination': False
            }
    
    def _large_dataset_strategy(self, base_query: str, dataset_info: Dict, user_intent: str) -> Dict:
        """Strategy for large datasets (1001-10000 records)"""
        intent_lower = user_intent.lower()
        
        # For aggregation queries, use database-level aggregation
        if any(word in intent_lower for word in ['sum', 'count', 'average', 'total', 'statistics']):
            return {
                'strategy': 'database_aggregation',
                'query': self._convert_to_aggregation_query(base_query, dataset_info),
                'limit': None,
                'sampling': None,
                'pagination': False
            }
        
        # For trend analysis, use time-based sampling
        elif any(word in intent_lower for word in ['trend', 'growth', 'over time', 'monthly', 'yearly']):
            return {
                'strategy': 'temporal_sampling',
                'query': self._add_temporal_grouping(base_query, dataset_info),
                'limit': 50,
                'sampling': 'temporal',
                'pagination': False
            }
        
        # For complete data requests, use efficient pagination
        elif any(word in intent_lower for word in ['all', 'complete', 'everything']):
            return {
                'strategy': 'efficient_pagination',
                'query': base_query,
                'limit': 200,
                'sampling': None,
                'pagination': True,
                'page_size': 200,
                'background_processing': True
            }
        
        # Default: strategic sampling
        else:
            return {
                'strategy': 'strategic_sampling',
                'query': self._add_strategic_sampling(base_query, dataset_info, sample_size=100),
                'limit': 100,
                'sampling': 'strategic',
                'pagination': False
            }
    
    def _enterprise_dataset_strategy(self, base_query: str, dataset_info: Dict, user_intent: str) -> Dict:
        """Strategy for enterprise datasets (10000+ records)"""
        return {
            'strategy': 'enterprise_aggregation',
            'query': self._convert_to_enterprise_query(base_query, dataset_info),
            'limit': 100,
            'sampling': 'enterprise',
            'pagination': True,
            'page_size': 100,
            'background_processing': True,
            'caching': True,
            'streaming': True
        }
    
    def _add_smart_sampling(self, query: str, dataset_info: Dict, sample_size: int) -> str:
        """Add systematic sampling to query"""
        row_count = dataset_info['row_count']
        if row_count <= sample_size:
            return query
        
        # Calculate sampling interval
        interval = max(1, row_count // sample_size)
        
        # Add ROW_NUMBER() for systematic sampling
        if "FROM" in query.upper():
            table_part = query.split("FROM", 1)[1].strip().split()[0]
            return f"""
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (ORDER BY RANDOM()) as rn
                FROM {table_part}
            ) WHERE rn % {interval} = 0 LIMIT {sample_size}
            """
        return query
    
    def _add_intelligent_ordering(self, query: str, dataset_info: Dict) -> str:
        """Add intelligent ordering based on data characteristics"""
        numeric_cols = dataset_info['numeric_columns']
        
        if numeric_cols and "ORDER BY" not in query.upper():
            # Order by most likely important numeric column
            primary_col = numeric_cols[0]
            query += f" ORDER BY {primary_col} DESC"
        
        return query
    
    def _convert_to_aggregation_query(self, base_query: str, dataset_info: Dict) -> str:
        """Convert to efficient aggregation query"""
        numeric_cols = dataset_info['numeric_columns']
        text_cols = dataset_info['text_columns']
        
        if numeric_cols and text_cols:
            # Group by first text column, aggregate numeric columns
            group_col = text_cols[0]
            agg_col = numeric_cols[0]
            
            if "FROM" in base_query.upper():
                table_part = base_query.split("FROM", 1)[1].strip().split()[0]
                return f"""
                SELECT {group_col}, 
                       COUNT(*) as record_count,
                       AVG({agg_col}) as avg_{agg_col},
                       SUM({agg_col}) as total_{agg_col},
                       MIN({agg_col}) as min_{agg_col},
                       MAX({agg_col}) as max_{agg_col}
                FROM {table_part}
                WHERE {group_col} IS NOT NULL
                GROUP BY {group_col}
                ORDER BY total_{agg_col} DESC
                LIMIT 20
                """
        
        return base_query
    
    def _add_temporal_grouping(self, query: str, dataset_info: Dict) -> str:
        """Add temporal grouping for trend analysis"""
        date_cols = dataset_info['date_columns']
        numeric_cols = dataset_info['numeric_columns']
        
        if date_cols and numeric_cols and "FROM" in query.upper():
            table_part = query.split("FROM", 1)[1].strip().split()[0]
            date_col = date_cols[0]
            numeric_col = numeric_cols[0]
            
            return f"""
            SELECT strftime('%Y-%m', {date_col}) as period,
                   COUNT(*) as record_count,
                   AVG({numeric_col}) as avg_value,
                   SUM({numeric_col}) as total_value
            FROM {table_part}
            WHERE {date_col} IS NOT NULL
            GROUP BY strftime('%Y-%m', {date_col})
            ORDER BY period
            """
        
        return query
    
    def _add_strategic_sampling(self, query: str, dataset_info: Dict, sample_size: int) -> str:
        """Add strategic sampling that maintains data distribution"""
        if "FROM" in query.upper():
            table_part = query.split("FROM", 1)[1].strip().split()[0]
            
            # Use TABLESAMPLE for very efficient sampling (if supported)
            # Fallback to systematic sampling
            return f"""
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (ORDER BY RANDOM()) as rn
                FROM {table_part}
            ) WHERE rn <= {sample_size}
            """
        
        return query
    
    def _convert_to_enterprise_query(self, base_query: str, dataset_info: Dict) -> str:
        """Convert to enterprise-optimized query with heavy aggregation"""
        # For enterprise datasets, focus on high-level insights
        numeric_cols = dataset_info['numeric_columns'][:3]  # Top 3 numeric columns
        text_cols = dataset_info['text_columns'][:2]       # Top 2 text columns
        
        if "FROM" in base_query.upper():
            table_part = base_query.split("FROM", 1)[1].strip().split()[0]
            
            # Create executive summary query
            return f"""
            SELECT 'Dataset Overview' as insight_type,
                   COUNT(*) as total_records,
                   '{dataset_info["row_count"]}' as actual_count,
                   'Enterprise Scale Dataset' as category
            FROM {table_part}
            
            UNION ALL
            
            SELECT 'Top Categories' as insight_type,
                   COUNT(*) as count,
                   {text_cols[0] if text_cols else "'No Category'"} as category,
                   'Distribution Analysis' as type
            FROM {table_part}
            GROUP BY {text_cols[0] if text_cols else "1"}
            ORDER BY count DESC
            LIMIT 10
            """
        
        return base_query
    
    def execute_optimized_query(self, query_config: Dict, table_name: str) -> Dict:
        """Execute optimized query with performance monitoring"""
        start_time = time.time()
        strategy = query_config['strategy']
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query_config['query']))
                data = result.fetchall()
                columns = list(result.keys())
                
                # Convert to records
                if data:
                    if hasattr(data[0], '_mapping'):
                        records = [dict(row._mapping) for row in data]
                    else:
                        records = [dict(zip(columns, row)) for row in data]
                else:
                    records = []
                
                execution_time = time.time() - start_time
                
                # Store performance metrics
                self.performance_metrics[table_name] = {
                    'strategy': strategy,
                    'execution_time': execution_time,
                    'records_returned': len(records),
                    'query_length': len(query_config['query']),
                    'timestamp': datetime.now().isoformat()
                }
                
                # Generate appropriate summary based on strategy
                summary = self._generate_strategy_summary(strategy, records, execution_time)
                
                return {
                    'results': records,
                    'columns': columns,
                    'strategy_used': strategy,
                    'performance': {
                        'execution_time_seconds': round(execution_time, 3),
                        'records_returned': len(records),
                        'optimization_applied': True
                    },
                    'summary': summary,
                    'pagination': query_config.get('pagination', False)
                }
                
        except Exception as e:
            return {
                'error': f"Optimized query execution failed: {str(e)}",
                'strategy_attempted': strategy,
                'results': [],
                'columns': []
            }
    
    def _generate_strategy_summary(self, strategy: str, records: List[Dict], execution_time: float) -> str:
        """Generate appropriate summary based on optimization strategy"""
        record_count = len(records)
        
        strategy_messages = {
            'full_dataset': f"✅ **COMPLETE DATASET**: All {record_count} records analyzed in {execution_time:.2f}s",
            'smart_pagination': f"📊 **SMART PAGINATION**: Showing {record_count} records with efficient paging",
            'representative_sampling': f"🎯 **STRATEGIC SAMPLING**: {record_count} representative records selected from large dataset",
            'database_aggregation': f"⚡ **DATABASE AGGREGATION**: High-performance summary of large dataset in {execution_time:.2f}s",
            'temporal_sampling': f"📈 **TREND ANALYSIS**: Time-based insights from {record_count} data points",
            'efficient_pagination': f"🚀 **EFFICIENT PROCESSING**: {record_count} records with enterprise-grade optimization",
            'strategic_sampling': f"💡 **INTELLIGENT SAMPLING**: {record_count} strategically selected records for analysis",
            'enterprise_aggregation': f"🏢 **ENTERPRISE INSIGHTS**: Executive-level analysis optimized for massive datasets"
        }
        
        base_message = strategy_messages.get(strategy, f"📊 Analysis complete: {record_count} records processed")
        
        # Add performance note for large datasets
        if record_count > 1000 or execution_time > 2:
            base_message += f"\n\n🔧 **Performance Optimized**: Advanced algorithms applied for {record_count:,} records"
        
        return base_message
    
    def create_optimized_chart(self, records: List[Dict], query_intent: str, dataset_size: str) -> Optional[str]:
        """Create charts optimized for different dataset sizes"""
        if not records:
            return None
        
        # For large datasets, use aggregated/sampled visualization
        if dataset_size in ['large', 'enterprise'] and len(records) > 100:
            # Sample data for visualization
            sample_size = min(50, len(records))
            sampled_records = records[:sample_size]
        else:
            sampled_records = records
        
        try:
            # Create performance-optimized chart
            plt.figure(figsize=(12, 8))
            
            # Identify data for plotting
            numeric_data = []
            labels = []
            
            for record in sampled_records:
                for key, value in record.items():
                    try:
                        numeric_data.append(float(value))
                        labels.append(str(key)[:15])
                        break  # Use first numeric value found
                    except (ValueError, TypeError):
                        continue
            
            if numeric_data and len(numeric_data) > 1:
                plt.plot(range(len(numeric_data)), numeric_data, 'o-', linewidth=2, markersize=6)
                plt.title(f'Data Visualization ({dataset_size.title()} Dataset)', fontsize=14, fontweight='bold')
                plt.xlabel('Records', fontsize=12)
                plt.ylabel('Values', fontsize=12)
                plt.grid(True, alpha=0.3)
                
                # Add dataset size indicator
                plt.text(0.02, 0.98, f'Optimization: {dataset_size}', transform=plt.gca().transAxes,
                        bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7),
                        verticalalignment='top', fontsize=10)
                
                plt.tight_layout()
                
                # Convert to base64
                buffer = io.BytesIO()
                plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
                buffer.seek(0)
                chart_data = base64.b64encode(buffer.getvalue()).decode()
                plt.close()
                
                return f"data:image/png;base64,{chart_data}"
        
        except Exception as e:

            plt.close()
        
        return None
    
    def get_performance_report(self) -> Dict:
        """Get performance report for all processed datasets"""
        return {
            'total_datasets_processed': len(self.performance_metrics),
            'performance_metrics': self.performance_metrics,
            'optimization_strategies_used': list(set(
                metrics['strategy'] for metrics in self.performance_metrics.values()
            )),
            'average_execution_time': sum(
                metrics['execution_time'] for metrics in self.performance_metrics.values()
            ) / len(self.performance_metrics) if self.performance_metrics else 0
        } 