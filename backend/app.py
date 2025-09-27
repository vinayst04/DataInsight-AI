from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pandas as pd
import sqlite3
import os
import json
from datetime import datetime
import google.generativeai as genai
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
import numpy as np
from sqlalchemy import create_engine, text
import re
from typing import Dict, List, Any
from dotenv import load_dotenv
import time
import threading
import schedule
import glob

# Load environment variables from .env.local
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
env_path = os.path.join(parent_dir, '.env.local')

load_dotenv(env_path)

app = Flask(__name__)
# Configure CORS for production - allow Vercel domains
CORS(app, origins=[
    "http://localhost:3000",  # Development
    "http://localhost:3001",  # Alternative dev port
], supports_credentials=True)

# For Vercel, we need to allow dynamic origins
@app.after_request
def after_request(response):
    origin = request.headers.get('Origin')
    if origin:
        if (origin.startswith('https://') and 
            ('.vercel.app' in origin or '.netlify.app' in origin or 'localhost' in origin)):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
            response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

# Configuration
UPLOAD_FOLDER = 'uploads'
CHARTS_FOLDER = 'charts'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
DATABASE_PATH = 'data_agent.db'

# Create directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CHARTS_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CHARTS_FOLDER'] = CHARTS_FOLDER

# Database setup
engine = create_engine(f'sqlite:///{DATABASE_PATH}')

# File cleanup configuration
FILE_RETENTION_HOURS = 4  # Delete files after 4 hours

class DataProcessor:
    def __init__(self):
        self.engine = engine
    
    def clean_column_name(self, col_name):
        """Clean column names for SQL compatibility"""
        if pd.isna(col_name) or col_name == '' or str(col_name).strip() == '':
            return f"unnamed_column_{datetime.now().microsecond}"
        
        cleaned = str(col_name).strip()
        cleaned = re.sub(r'[^\w\s]', '', cleaned)
        cleaned = re.sub(r'\s+', '_', cleaned)
        return cleaned.lower()
    
    def smart_column_processing(self, df):
        """Smart processing to detect and clean meaningful columns"""
        
        # Step 1: Remove completely empty columns
        df = df.dropna(axis=1, how='all')
        
        # Step 2: Remove columns that are mostly empty (>90% NaN)
        threshold = len(df) * 0.1  # Keep columns with at least 10% data
        df = df.dropna(axis=1, thresh=threshold)
        
        # Step 3: Improve column naming
        new_columns = []
        for i, col in enumerate(df.columns):
            cleaned_name = self.smart_clean_column_name(col, i, df[col])
            new_columns.append(cleaned_name)
        
        # Step 4: Handle duplicate column names
        seen_cols = {}
        final_cols = []
        for col in new_columns:
            if col in seen_cols:
                seen_cols[col] += 1
                final_cols.append(f"{col}_{seen_cols[col]}")
            else:
                seen_cols[col] = 0
                final_cols.append(col)
        
        df.columns = final_cols

        return df
    
    def smart_clean_column_name(self, col_name, position, col_data):
        """Smarter column name cleaning that preserves meaning"""
        
        # Handle empty/unnamed columns by analyzing their content
        if pd.isna(col_name) or col_name == '' or str(col_name).strip() == '':
            # Try to infer name from data content
            sample_data = col_data.dropna().head(5)
            if len(sample_data) > 0:
                first_val = str(sample_data.iloc[0]).lower()
                if '@' in first_val:
                    return 'email'
                elif any(word in first_val for word in ['price', 'cost', 'amount']):
                    return 'amount'
                elif any(word in first_val for word in ['date', 'time']):
                    return 'date'
                elif any(word in first_val for word in ['name', 'customer', 'client']):
                    return 'name'
            return f"column_{position + 1}"
        
        # Clean the column name but preserve important information
        cleaned = str(col_name).strip()
        
        # Handle special patterns
        if '@' in cleaned:
            cleaned = 'email_address'
        elif 'date' in cleaned.lower() or 'time' in cleaned.lower():
            cleaned = 'date_time'
        elif any(word in cleaned.lower() for word in ['price', 'cost', 'amount', 'revenue', 'sales']):
            cleaned = 'amount'
        elif any(word in cleaned.lower() for word in ['name', 'customer', 'client']):
            cleaned = 'customer_name'
        elif any(word in cleaned.lower() for word in ['product', 'item']):
            cleaned = 'product'
        elif any(word in cleaned.lower() for word in ['quantity', 'qty']):
            cleaned = 'quantity'
        else:
            # General cleaning while preserving meaning
            # Remove special characters but keep the essence
            cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
            cleaned = re.sub(r'\s+', '_', cleaned)
            # Don't force to lowercase if it loses meaning
            if cleaned.isupper():
                cleaned = cleaned.lower()
        
        return cleaned[:50]  # Limit length
    
    def identify_meaningful_columns(self, df):
        """Identify which columns contain meaningful data for analysis"""
        meaningful = {}
        
        for col in df.columns:
            col_info = {
                'name': col,
                'type': str(df[col].dtype),
                'non_null_count': df[col].notna().sum(),
                'null_percentage': (df[col].isna().sum() / len(df)) * 100,
                'is_meaningful': False
            }
            
            # Check if column has enough non-null data (at least 50%)
            if col_info['null_percentage'] < 50:
                col_info['is_meaningful'] = True
                
                # Add semantic information
                if df[col].dtype in ['int64', 'float64']:
                    col_info['category'] = 'numeric'
                    col_info['min'] = float(df[col].min()) if df[col].notna().any() else None
                    col_info['max'] = float(df[col].max()) if df[col].notna().any() else None
                elif 'date' in col.lower() or 'time' in col.lower():
                    col_info['category'] = 'datetime'
                elif '@' in str(df[col].iloc[0]) if df[col].notna().any() else False:
                    col_info['category'] = 'email'
                else:
                    col_info['category'] = 'text'
                    col_info['unique_values'] = df[col].nunique()
            
            meaningful[col] = col_info
        
        return meaningful
        """Handle queries about available datasets/Excel files"""
        
        dataset_count = len(available_tables)
        dataset_names = list(available_tables.keys())
        
        # Calculate total rows across all datasets
        total_rows = 0
        dataset_details = []
        
        for name, info in available_tables.items():
            table_name = info['table_name']
            columns = info.get('columns', [])
            
            # Get row count for this table
            try:
                with self.engine.connect() as conn:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    row_count = result.fetchone()[0]
                    total_rows += row_count
                    
                    dataset_details.append({
                        'name': name,
                        'rows': row_count,
                        'columns': len(columns)
                    })
            except Exception as e:

                dataset_details.append({
                    'name': name,
                    'rows': 0,
                    'columns': len(columns)
                })
        
        # Create summary
        if dataset_count == 0:
            summary = "No Excel files have been uploaded yet. Please upload an Excel file to get started."
        elif dataset_count == 1:
            details = dataset_details[0]
            summary = f"You have uploaded **1 Excel file**: **{details['name']}** containing **{details['rows']} rows** and **{details['columns']} columns** of data."
        else:
            summary = f"You have uploaded **{dataset_count} Excel files**:\n\n"
            for i, details in enumerate(dataset_details, 1):
                summary += f"{i}. **{details['name']}**: {details['rows']} rows, {details['columns']} columns\n"
            summary += f"\n**Total**: {total_rows} rows across all datasets."
        
        # Create results table
        results = []
        for details in dataset_details:
            results.append({
                'Dataset_Name': details['name'],
                'Rows': details['rows'],
                'Columns': details['columns']
            })
        
        return {
            'results': results,
            'columns': ['Dataset_Name', 'Rows', 'Columns'],
            'chart': None,  # No chart for dataset info
            'summary': summary
        }
    
    def process_excel_file(self, file_path: str, user_id: str):
        """Process Excel file and store in database"""
        excel_file = None
        try:
            # Read Excel file with all sheets
            excel_file = pd.ExcelFile(file_path)
            processed_data = {}
            
            for sheet_name in excel_file.sheet_names:
                try:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    
                    # Handle empty or problematic data
                    if df.empty:
                        continue

                    # Smart column detection and cleaning
                    df = self.smart_column_processing(df)
                    
                    # Skip if no meaningful columns remain
                    if df.empty or len(df.columns) == 0:

                        continue
                    
                    # Clean sheet name for table naming
                    clean_sheet_name = re.sub(r'[^\w]', '_', sheet_name.lower())
                    table_name = f"{user_id}_{clean_sheet_name}"
                    
                    # Store in database
                    df.to_sql(table_name, self.engine, if_exists='replace', index=False)
                    
                    # Convert data types to JSON-serializable format
                    data_types_json = {}
                    for col, dtype in df.dtypes.items():
                        data_types_json[str(col)] = str(dtype)
                    
                    # Identify meaningful columns for AI
                    meaningful_cols = self.identify_meaningful_columns(df)
                    
                    # Convert meaningful columns to JSON-serializable format
                    meaningful_cols_json = {}
                    for col, info in meaningful_cols.items():
                        col_info_json = {}
                        for key, value in info.items():
                            if isinstance(value, (int, float)) and pd.isna(value):
                                col_info_json[key] = None
                            elif hasattr(value, 'item'):  # numpy scalar
                                col_info_json[key] = value.item()
                            else:
                                col_info_json[key] = value
                        meaningful_cols_json[str(col)] = col_info_json
                    
                    processed_data[sheet_name] = {
                        'table_name': table_name,
                        'columns': [str(col) for col in df.columns],
                        'meaningful_columns': meaningful_cols_json,
                        'row_count': int(len(df)),
                        'data_types': data_types_json
                    }

                except Exception as e:

                    continue
            
            return processed_data
            
        except Exception as e:
            raise Exception(f"Error processing Excel file: {str(e)}")
        finally:
            # Ensure Excel file is properly closed
            if excel_file is not None:
                excel_file.close()

class AIAgent:
    def __init__(self):
        self.engine = engine
        # Configure Gemini API
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:

            api_key = None
        
        if api_key:
            # Configure for Google AI Studio API (not Vertex AI)
            genai.configure(api_key=api_key)
            
            # Use current supported model names with speed optimization
            model_names = ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-pro']
            
            self.model = None
            self.fast_model = None
            for model_name in model_names:
                try:
                    if not self.model:
                        self.model = genai.GenerativeModel(model_name)

                    if not self.fast_model and 'lite' in model_name:
                        self.fast_model = genai.GenerativeModel(model_name)

                    if self.model and self.fast_model:
                        break
                except Exception as e:

                    continue
            
            # Fallback: use same model for both if lite not available
            if self.model and not self.fast_model:
                self.fast_model = self.model

            if not self.model:
                pass
        else:
            self.model = None
            self.fast_model = None

    def is_simple_query(self, query: str) -> bool:
        """Determine if a query is simple enough for fast processing"""
        simple_patterns = [
            'count', 'how many', 'total', 'sum', 'average', 'max', 'min',
            'show me', 'list', 'display', 'first', 'last', 'describe',
            'what is', 'what are', 'overview'
        ]
        return any(pattern in query.lower() for pattern in simple_patterns)
    
    def is_data_analysis_query(self, query: str) -> bool:
        """Check if the query is actually about data analysis"""
        query_lower = query.lower().strip()
        
        # Data analysis indicators
        data_indicators = [
            'show', 'list', 'display', 'count', 'how many', 'total', 'sum',
            'average', 'mean', 'max', 'min', 'top', 'bottom', 'highest', 'lowest',
            'filter', 'search', 'find', 'analyze', 'trend', 'breakdown', 'group',
            'chart', 'graph', 'visualize', 'plot', 'report', 'customer', 'sales',
            'revenue', 'profit', 'data', 'records', 'rows', 'columns', 'value',
            'what is', 'what are', 'who are', 'which', 'when', 'where'
        ]
        
        # Non-data indicators (things that suggest this isn't about data analysis)
        non_data_indicators = [
            'modify this', 'change this', 'fix this', 'update this', 'improve this',
            'how does this work', 'what does this do', 'explain this system',
            'can you modify', 'can you change', 'can you fix', 'can you improve'
        ]
        
        # Check for explicit non-data queries
        if any(phrase in query_lower for phrase in non_data_indicators):
            return False
            
        # Check for data analysis indicators
        if any(indicator in query_lower for indicator in data_indicators):
            return True
            
        # If unclear, assume it's data analysis (safer default)
        return True

    def get_data_characteristics(self, df: pd.DataFrame) -> str:
        """Get key characteristics of the dataset for AI analysis"""
        characteristics = []
        
        # Data quality info
        total_cells = len(df) * len(df.columns)
        null_cells = df.isnull().sum().sum()
        if null_cells > 0:
            null_percentage = (null_cells / total_cells) * 100
            characteristics.append(f"Null values: {null_cells} ({null_percentage:.1f}%)")
        
        # Column types
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        text_cols = df.select_dtypes(include=[object]).columns.tolist()
        
        if numeric_cols:
            characteristics.append(f"Numeric columns: {', '.join(numeric_cols)}")
        if text_cols:
            characteristics.append(f"Text columns: {', '.join(text_cols)}")
            
        return ' | '.join(characteristics) if characteristics else "No specific patterns identified"
    
    def classify_request(self, query: str) -> str:
        """Classify the type of request to handle it appropriately"""
        query_lower = query.lower().strip()
        
        # System modification requests - explicit phrases only
        system_keywords = [
            'modify this', 'change this', 'fix this', 'update this', 'improve this',
            'can you modify', 'can you change', 'can you fix', 'can you improve',
            'customize', 'configure', 'setup', 'install', 'debug this', 'repair this'
        ]
        
        # Conversation/help requests - be very specific to avoid false positives
        conversation_keywords = [
            'hello', 'hi there', 'help me', 'what can you do', 'how does this work',
            'what does this do', 'explain this system', 'thank you', 'thanks', 'bye', 'goodbye'
        ]
        
        # Strong data analysis indicators
        data_keywords = [
            'what is the', 'what are the', 'show me', 'tell me about', 'analyze',
            'data', 'records', 'accounts', 'customers', 'sales', 'revenue',
            'combination', 'summary', 'breakdown', 'total', 'count', 'list',
            'display', 'find', 'search', 'filter', 'trend', 'pattern'
        ]
        
        # Check for explicit system modification requests
        if any(phrase in query_lower for phrase in system_keywords):
            return 'system'
        
        # Check for strong data analysis indicators first
        if any(keyword in query_lower for keyword in data_keywords):
            return 'data_analysis'
        
        # Check for conversation requests (only very specific ones)
        if any(phrase in query_lower for phrase in conversation_keywords):
            return 'conversation'
            
        # Default to data analysis (safer for a data analysis tool)
        return 'data_analysis'

    def handle_system_request(self, query: str) -> Dict:
        """Handle system modification and configuration requests"""
        if not self.model:
            return {
                'results': [],
                'columns': [],
                'chart': None,
                'summary': "I understand you want to modify something, but I need more specific details. What would you like me to change or improve in the system?"
            }
        
        try:
            prompt = f"""You are a helpful AI assistant for a data analysis application. The user is asking to modify, fix, or improve something about the system.

User request: "{query}"

This is NOT a data analysis query. The user wants to:
- Modify system behavior
- Fix an issue
- Improve functionality
- Change configuration
- Get help with the system

Respond as a helpful assistant who can:
1. Acknowledge their request
2. Ask clarifying questions if needed
3. Provide helpful guidance
4. Explain what can be modified or improved

Be conversational and helpful. Don't try to generate SQL or analyze data.

Response:"""

            response = self.model.generate_content(prompt)
            return {
                'results': [],
                'columns': [],
                'chart': None,
                'summary': response.text.strip()
            }
        except Exception as e:
            return {
                'results': [],
                'columns': [],
                'chart': None,
                'summary': f"I understand you want to modify something. Could you please be more specific about what you'd like me to change or improve? I can help with system configurations, data analysis improvements, or interface modifications."
            }

    def handle_conversation_request(self, query: str) -> Dict:
        """Handle general conversation and help requests"""
        query_lower = query.lower().strip()
        
        if any(word in query_lower for word in ['hello', 'hi']):
            return {
                'results': [],
                'columns': [],
                'chart': None,
                'summary': "Hello! 👋 I'm your AI data analysis assistant. I can help you analyze Excel data, create visualizations, and answer questions about your datasets. Upload an Excel file and ask me anything about your data!"
            }
        
        elif any(word in query_lower for word in ['help', 'what can you do']):
            return {
                'results': [],
                'columns': [],
                'chart': None,
                'summary': """I can help you with:

📊 **Data Analysis**: Ask questions about your data in natural language
📈 **Visualizations**: Create charts and graphs from your data  
🔍 **Insights**: Get business intelligence and trends
📋 **Reports**: Generate summaries and breakdowns
🎯 **Queries**: Find specific information in your datasets

Just upload an Excel file and start asking questions like:
- "Show me the top 10 customers"
- "What's the average sales amount?"
- "Create a chart of monthly trends"
- "Which products are most popular?"

What would you like to explore?"""
            }
        
        elif any(word in query_lower for word in ['thank', 'thanks']):
            return {
                'results': [],
                'columns': [],
                'chart': None,
                'summary': "You're welcome! 😊 Feel free to ask me anything else about your data or if you need help with analysis."
            }
        
        else:
            # Use AI for other conversation
            if self.model:
                try:
                    prompt = f"""You are a helpful AI assistant for a data analysis application. Respond to this user message in a friendly, helpful way:

User: "{query}"

Keep it brief and redirect them to data analysis capabilities if appropriate.

Response:"""
                    response = self.model.generate_content(prompt)
                    return {
                        'results': [],
                        'columns': [],
                        'chart': None,
                        'summary': response.text.strip()
                    }
                except:
            return {
                'results': [],
                'columns': [],
                'chart': None,
                'summary': "I'm here to help with data analysis! Upload an Excel file and ask me questions about your data."
            }

    def handle_dataset_info_query(self, query: str, available_tables: Dict) -> Dict:
        """Handle queries about available datasets/Excel files"""
        
        dataset_count = len(available_tables)
        dataset_names = list(available_tables.keys())
        
        # Calculate total rows across all datasets
        total_rows = 0
        dataset_details = []
        
        for name, info in available_tables.items():
            table_name = info['table_name']
            columns = info.get('columns', [])
            
            # Get row count for this table
            try:
                with self.engine.connect() as conn:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    row_count = result.fetchone()[0]
                    total_rows += row_count
                    
                    dataset_details.append({
                        'name': name,
                        'rows': row_count,
                        'columns': len(columns)
                    })
            except Exception as e:

                dataset_details.append({
                    'name': name,
                    'rows': 0,
                    'columns': len(columns)
                })
        
        # Create summary
        if dataset_count == 0:
            summary = "No Excel files have been uploaded yet. Please upload an Excel file to get started."
        elif dataset_count == 1:
            details = dataset_details[0]
            summary = f"You have uploaded **1 Excel file**: **{details['name']}** containing **{details['rows']} rows** and **{details['columns']} columns** of data."
        else:
            summary = f"You have uploaded **{dataset_count} Excel files**:\n\n"
            for i, details in enumerate(dataset_details, 1):
                summary += f"{i}. **{details['name']}**: {details['rows']} rows, {details['columns']} columns\n"
            summary += f"\n**Total**: {total_rows} rows across all datasets."
        
        # Create results table
        results = []
        for details in dataset_details:
            results.append({
                'Dataset_Name': details['name'],
                'Rows': details['rows'],
                'Columns': details['columns']
            })
        
        return {
            'results': results,
            'columns': ['Dataset_Name', 'Rows', 'Columns'],
            'chart': None,  # No chart for dataset info
            'summary': summary
        }

    def analyze_query(self, query: str, available_tables: Dict) -> Dict:
        """Analyze natural language query with proper request classification"""
        try:
            # First classify the type of request
            request_type = self.classify_request(query)
            
            # Handle different types of requests appropriately
            if request_type == 'system':
                return self.handle_system_request(query)
            elif request_type == 'conversation':
                return self.handle_conversation_request(query)
            else:
                # Handle as data analysis query
                return self.generate_sql_and_analysis(query, available_tables)
                
        except Exception as e:
            return {
                'error': f"Error analyzing query: {str(e)}",
                'sql_query': None,
                'results': None,
                'chart': None
            }
    
    def generate_sql_and_analysis(self, query: str, available_tables: Dict) -> Dict:
        """Generate SQL query and perform analysis based on natural language using Gemini AI"""
        
        if not available_tables:
            return {
                'error': 'No data tables available. Please upload an Excel file first.',
                'results': None, 
                'chart': None,
                'summary': 'Please upload an Excel file to start analyzing your data.'
            }
        
        # If multiple tables available, let AI choose or inform user
        if len(available_tables) > 1:

            # For now, use the most recently uploaded (last in the list)
            # Future enhancement: Let AI choose based on query context
            table_info = list(available_tables.values())[-1]
            table_name = table_info['table_name']
            
            # Add info about multiple datasets to response
            dataset_info = f"\n\n📊 **Available Datasets:** {', '.join(available_tables.keys())}\n*Currently analyzing: {list(available_tables.keys())[-1]}*\n\n"
        else:
            # Single table
            table_info = list(available_tables.values())[0]
            table_name = table_info['table_name']
            dataset_info = ""
        
        # Check if this is a dataset info query first
        fallback_sql = self.generate_sql_from_query(query.lower(), table_name, table_info['columns'])
        if fallback_sql == "DATASET_INFO_QUERY":
            # Handle dataset information query
            return self.handle_dataset_info_query(query, available_tables)
        
        # Since we're in data analysis mode, proceed with the query
        
        # Generate SQL using Gemini AI
        try:
            sql_query = self.generate_sql_with_gemini(query, table_name, table_info['columns'])
            
            # If Gemini fails, fallback to pattern matching
            if not sql_query:
                sql_query = fallback_sql
            
        except Exception:
            # Fallback to pattern matching if Gemini fails
            sql_query = fallback_sql
        
        # Execute query
        try:
            with self.engine.connect() as conn:
                # Execute the generated SQL query
                result = conn.execute(text(sql_query))
                data = result.fetchall()
                columns = list(result.keys())
                
                # Convert to DataFrame for analysis - handle the data properly
                if data:
                    try:
                        # Try different approaches for Row objects
                        if hasattr(data[0], '_mapping'):
                            # SQLAlchemy 2.0 Row objects
                            rows_as_dicts = [dict(row._mapping) for row in data]
                        else:
                            # Fallback for other types
                            rows_as_dicts = [dict(zip(columns, row)) for row in data]
                        
                        df = pd.DataFrame(rows_as_dicts)
                    except Exception as conv_error:

                        # Fallback: try direct conversion
                        df = pd.DataFrame(data, columns=columns)
                else:
                    df = pd.DataFrame(columns=columns)
                
                # Generate visualization only if user requests it
                chart_data = self.generate_chart_if_requested(df, query)
                
                # Generate intelligent summary using Gemini
                summary = self.generate_intelligent_summary(df, query, sql_query)
                
                # Convert DataFrame to records safely with JSON serialization
                try:
                    results = []
                    for _, row in df.iterrows():
                        row_dict = {}
                        for col, value in row.items():
                            # Convert numpy types to native Python types for JSON serialization
                            if pd.isna(value):
                                row_dict[str(col)] = None
                            elif hasattr(value, 'item'):  # numpy scalar
                                row_dict[str(col)] = value.item()
                            elif isinstance(value, (int, float, str, bool)):
                                row_dict[str(col)] = value
                            else:
                                row_dict[str(col)] = str(value)
                        results.append(row_dict)
                except Exception as dict_error:

                    # Ultimate fallback
                    results = [{"error": "Could not convert data to JSON format"}]
                
                return {
                    'results': results,
                    'columns': [str(col) for col in df.columns] if not df.empty else [str(col) for col in columns],
                    'chart': chart_data,
                    'summary': dataset_info + summary
                }
                
        except Exception as e:

            return {
                'error': f"Error executing query: {str(e)}",
                'results': None,
                'chart': None
            }
    
    def generate_sql_with_gemini(self, query: str, table_name: str, columns: List[str]) -> str:
        """Use Gemini AI to generate SQL from natural language with speed optimization"""
        if not self.model:
            return None  # Fallback to pattern matching
        
        try:
            # Determine if this is a simple query for fast processing
            use_fast_mode = self.is_simple_query(query)
            selected_model = self.fast_model if (use_fast_mode and self.fast_model) else self.model
            
            if use_fast_mode:
                # Check if user wants complete data
                complete_data_keywords = [
                    'all data', 'complete data', 'entire dataset', 'full data', 'everything',
                    'all records', 'complete records', 'show all', 'give me all', 'full dataset',
                    'without limit', 'unlimited', 'all rows'
                ]
                wants_complete_data = any(keyword in query.lower() for keyword in complete_data_keywords)
                limit_guidance = "- Show all data without LIMIT clauses" if wants_complete_data else "- Use appropriate LIMIT clauses (10-50 rows)"
                
                # Fast mode with simple prompt
                prompt = f"""Convert this question to SQL. Be concise and accurate.

Table: {table_name}
Columns: {', '.join(columns)}
Question: "{query}"

Rules:
- Use proper SQLite syntax
- Return ONLY the SQL query
- For aggregations use SUM, AVG, COUNT, MIN, MAX
{limit_guidance}
- Handle fuzzy column matching

SQL Query:"""
            else:
                # Advanced mode with detailed prompt
                prompt = f"""You are a Business Intelligence Expert. Generate advanced SQL for complex analysis.

Table: {table_name}
Columns: {', '.join(columns)}
Question: "{query}"

CAPABILITIES:
📊 Business Analytics: Revenue, profit, growth, KPIs
📈 Trends: Time series, comparisons, forecasting  
🎯 Segmentation: Customer analysis, cohorts
💰 Financial: ROI, margins, variance analysis
📊 Statistics: Percentiles, correlations, distributions

ADVANCED SQL PATTERNS:
- Window functions: ROW_NUMBER(), RANK(), LAG(), LEAD()
- CTEs for complex logic
- Date functions: strftime() for time grouping
- Statistical: NTILE() for quartiles
- Fuzzy column matching for business terms

EXAMPLES:
- "top customers" → SELECT customer, SUM(revenue) FROM table GROUP BY customer ORDER BY SUM(revenue) DESC LIMIT 10
- "monthly trends" → SELECT strftime('%Y-%m', date), SUM(amount) FROM table GROUP BY strftime('%Y-%m', date)
- "growth rate" → SELECT *, LAG(value) OVER (ORDER BY date) as prev_value FROM table

Return ONLY the optimized SQL query:"""

            response = selected_model.generate_content(prompt)
            sql_query = response.text.strip()
            
            # Clean up the response
            if sql_query.startswith('```sql'):
                sql_query = sql_query.replace('```sql', '').replace('```', '').strip()
            elif sql_query.startswith('```'):
                sql_query = sql_query.replace('```', '').strip()
            
            # Basic validation
            if sql_query.upper().startswith('SELECT') and table_name in sql_query:
                if use_fast_mode:

                else:

                return sql_query
            else:
                return None
                
        except Exception as e:
            if "quota" in str(e).lower() or "429" in str(e):

                import time
                time.sleep(1)
                try:
                    response = selected_model.generate_content(prompt)
                    sql_query = response.text.strip()
                    if sql_query.startswith('```sql'):
                        sql_query = sql_query.replace('```sql', '').replace('```', '').strip()
                    elif sql_query.startswith('```'):
                        sql_query = sql_query.replace('```', '').strip()
                    if sql_query.upper().startswith('SELECT') and table_name in sql_query:

                        return sql_query
                except:
            return None
    
    def generate_intelligent_summary(self, df: pd.DataFrame, query: str, sql_query: str) -> str:
        """Generate intelligent business intelligence summary using AI analysis of actual data"""
        if not self.model:
            # Simple fallback only when AI is completely unavailable
            if df.empty:
                return "No data found for your query."
            return f"Found {len(df)} records with {len(df.columns)} columns. AI analysis unavailable."
        
        try:
            if df.empty:
                return "No data found matching your criteria. Consider broadening your search parameters or verifying data availability."
            
            # Always use the full model for better analysis
            selected_model = self.model
            
            # Create comprehensive data summary for AI analysis
            if len(df) == 1 and len(df.columns) == 1:
                # Single value result
                value = df.iloc[0, 0]
                data_summary = f"Single result: {value}"
                if pd.notna(value) and isinstance(value, (int, float)):
                    data_summary += f" (formatted: {value:,})"
            elif len(df) <= 10:
                # Small dataset - show all data
                data_summary = f"Complete dataset ({len(df)} records):\n{df.to_string(index=False)}"
            else:
                # Large dataset - show sample + stats
                data_summary = f"""Dataset Overview:
- Total records: {len(df)}
- Columns: {', '.join(df.columns)}

Sample data (first 5 rows):
{df.head(5).to_string(index=False)}

Data characteristics:
{self.get_data_characteristics(df)}"""

            # Comprehensive prompt for detailed analysis
            prompt = f"""You are an expert data analyst. Analyze this data and provide insights based on the user's question.

USER QUESTION: "{query}"
SQL QUERY USED: {sql_query}

ACTUAL DATA RESULTS:
{data_summary}

ANALYSIS REQUIREMENTS:
1. Analyze the ACTUAL data shown above
2. Answer the user's specific question
3. Point out data quality issues if any (null values, inconsistencies)
4. Provide business insights based on what you see
5. Use specific numbers from the data
6. Be analytical but conversational

RESPONSE FORMAT:
🎯 **Key Finding:** [Direct answer to the question]
📊 **Data Insights:** [What the actual data reveals]
💡 **Business Impact:** [Strategic implications]

Analyze the real data and respond:"""

            response = selected_model.generate_content(prompt)
            summary = response.text.strip()

            return summary
            
        except Exception as e:

            # Minimal fallback - just describe what we found
            if df.empty:
                return "No data found for your query."
            elif len(df) == 1 and len(df.columns) == 1:
                value = df.iloc[0, 0]
                return f"Found result: {value:,}" if pd.notna(value) else "Found result: No data"
            else:
                return f"Found {len(df)} records. AI analysis temporarily unavailable."
    
    def generate_sql_from_query(self, query: str, table_name: str, columns: List[str]) -> str:
        """Generate advanced SQL query based on natural language input with business intelligence focus"""
        
        query_lower = query.lower()
        
        # Check if user is asking about available datasets/files
        dataset_question_keywords = [
            'how many excel', 'how many files', 'what files', 'what excel', 'available datasets',
            'list files', 'show files', 'what data do i have', 'available data'
        ]
        
        if any(keyword in query_lower for keyword in dataset_question_keywords):
            # This is a question about available datasets, not data content
            # We'll handle this differently in the calling function
            return "DATASET_INFO_QUERY"
        
        # Check if user wants complete data (no limits)
        complete_data_keywords = [
            'all data', 'complete data', 'entire dataset', 'full data', 'everything',
            'all records', 'complete records', 'show all', 'give me all', 'full dataset',
            'without limit', 'unlimited', 'all rows'
        ]
        
        use_limits = not any(keyword in query_lower for keyword in complete_data_keywords)
        
        # Advanced business analytics patterns
        if any(word in query_lower for word in ['sum', 'total', 'add up', 'sum of', 'revenue', 'sales']):
            numeric_cols = [col for col in columns if any(term in col.lower() for term in ['amount', 'price', 'value', 'cost', 'revenue', 'sales', 'income', 'profit', 'fee', 'charge'])]
            if numeric_cols:
                return f"SELECT SUM({numeric_cols[0]}) as total_{numeric_cols[0].lower()} FROM {table_name}"
        
        elif any(word in query_lower for word in ['average', 'avg', 'mean']):
            numeric_cols = [col for col in columns if any(term in col.lower() for term in ['amount', 'price', 'value', 'cost', 'revenue', 'sales', 'income', 'rating', 'score'])]
            if numeric_cols:
                return f"SELECT AVG({numeric_cols[0]}) as average_{numeric_cols[0].lower()}, COUNT(*) as total_records FROM {table_name}"
        
        elif any(phrase in query_lower for phrase in ['how many', 'count', 'number of', 'total records', 'total rows']):
            return f"SELECT COUNT(*) as total_records FROM {table_name}"
        
        elif any(word in query_lower for word in ['top', 'best', 'highest', 'leading']):
            # Extract number if mentioned (top 5, top 10, etc.)
            import re
            num_match = re.search(r'top\s+(\d+)', query_lower)
            limit = int(num_match.group(1)) if num_match else 10
            
            numeric_cols = [col for col in columns if any(term in col.lower() for term in ['amount', 'price', 'value', 'cost', 'revenue', 'sales', 'income', 'profit', 'score', 'rating'])]
            text_cols = [col for col in columns if any(term in col.lower() for term in ['name', 'customer', 'client', 'product', 'category', 'region', 'account'])]
            
            limit_clause = f" LIMIT {limit}" if use_limits else ""
            
            if numeric_cols and text_cols:
                return f"SELECT {text_cols[0]}, {numeric_cols[0]} FROM {table_name} ORDER BY {numeric_cols[0]} DESC{limit_clause}"
            elif numeric_cols:
                return f"SELECT * FROM {table_name} ORDER BY {numeric_cols[0]} DESC{limit_clause}"
        
        elif any(phrase in query_lower for phrase in ['show me', 'list', 'display', 'view all', 'see all']):
            if 'email' in query_lower:
                email_cols = [col for col in columns if 'email' in col.lower() or 'mail' in col.lower()]
                if email_cols:
                    limit_clause = " LIMIT 50" if use_limits else ""
                    return f"SELECT {email_cols[0]} FROM {table_name} WHERE {email_cols[0]} IS NOT NULL{limit_clause}"
            elif any(word in query_lower for word in ['customer', 'client', 'user', 'account']):
                customer_cols = [col for col in columns if any(term in col.lower() for term in ['customer', 'client', 'user', 'account', 'name'])]
                if customer_cols:
                    limit_clause = " LIMIT 20" if use_limits else ""
                    return f"SELECT {', '.join(customer_cols[:3])} FROM {table_name}{limit_clause}"
            else:
                limit_clause = " LIMIT 20" if use_limits else ""
                return f"SELECT * FROM {table_name}{limit_clause}"
        
        elif any(phrase in query_lower for phrase in ['what is', 'what are', 'what data', 'what columns', 'describe', 'overview']):
            limit_clause = " LIMIT 5" if use_limits else ""
            return f"SELECT * FROM {table_name}{limit_clause}"
        
        elif any(word in query_lower for word in ['group', 'breakdown', 'by category', 'categorize', 'segment']):
            text_cols = [col for col in columns if any(term in col.lower() for term in ['category', 'type', 'name', 'group', 'class', 'region', 'department', 'status'])]
            numeric_cols = [col for col in columns if any(term in col.lower() for term in ['amount', 'price', 'value', 'cost', 'revenue', 'sales', 'income'])]
            
            if text_cols and numeric_cols:
                return f"SELECT {text_cols[0]}, COUNT(*) as count, SUM({numeric_cols[0]}) as total_{numeric_cols[0].lower()} FROM {table_name} WHERE {text_cols[0]} IS NOT NULL GROUP BY {text_cols[0]} ORDER BY total_{numeric_cols[0].lower()} DESC"
            elif text_cols:
                return f"SELECT {text_cols[0]}, COUNT(*) as count FROM {table_name} WHERE {text_cols[0]} IS NOT NULL GROUP BY {text_cols[0]} ORDER BY count DESC"
        
        elif any(word in query_lower for word in ['max', 'maximum', 'highest', 'largest', 'peak']):
            numeric_cols = [col for col in columns if any(term in col.lower() for term in ['amount', 'price', 'value', 'cost', 'revenue', 'sales', 'income', 'profit'])]
            if numeric_cols:
                return f"SELECT MAX({numeric_cols[0]}) as max_{numeric_cols[0].lower()}, MIN({numeric_cols[0]}) as min_{numeric_cols[0].lower()}, AVG({numeric_cols[0]}) as avg_{numeric_cols[0].lower()} FROM {table_name}"
        
        elif any(word in query_lower for word in ['min', 'minimum', 'lowest', 'smallest']):
            numeric_cols = [col for col in columns if any(term in col.lower() for term in ['amount', 'price', 'value', 'cost', 'revenue', 'sales', 'income'])]
            if numeric_cols:
                return f"SELECT MIN({numeric_cols[0]}) as minimum_{numeric_cols[0].lower()} FROM {table_name}"
        
        elif any(phrase in query_lower for phrase in ['growth', 'trend', 'over time', 'monthly', 'yearly']):
            date_cols = [col for col in columns if any(term in col.lower() for term in ['date', 'time', 'month', 'year', 'created', 'updated'])]
            numeric_cols = [col for col in columns if any(term in col.lower() for term in ['amount', 'price', 'value', 'cost', 'revenue', 'sales', 'income'])]
            
            if date_cols and numeric_cols:
                return f"SELECT strftime('%Y-%m', {date_cols[0]}) as month, SUM({numeric_cols[0]}) as total, COUNT(*) as transactions FROM {table_name} GROUP BY strftime('%Y-%m', {date_cols[0]}) ORDER BY month"
            elif date_cols:
                return f"SELECT strftime('%Y-%m', {date_cols[0]}) as month, COUNT(*) as count FROM {table_name} GROUP BY strftime('%Y-%m', {date_cols[0]}) ORDER BY month"
        
        elif any(phrase in query_lower for phrase in ['profit', 'margin', 'profitability']):
            profit_cols = [col for col in columns if any(term in col.lower() for term in ['profit', 'margin', 'net', 'gross'])]
            revenue_cols = [col for col in columns if any(term in col.lower() for term in ['revenue', 'sales', 'income'])]
            cost_cols = [col for col in columns if any(term in col.lower() for term in ['cost', 'expense', 'spend'])]
            
            if profit_cols:
                return f"SELECT SUM({profit_cols[0]}) as total_profit, AVG({profit_cols[0]}) as avg_profit FROM {table_name}"
            elif revenue_cols and cost_cols:
                return f"SELECT SUM({revenue_cols[0]} - {cost_cols[0]}) as calculated_profit, SUM({revenue_cols[0]}) as total_revenue, SUM({cost_cols[0]}) as total_cost FROM {table_name}"
        
        elif any(phrase in query_lower for phrase in ['performance', 'kpi', 'metrics', 'analytics']):
            numeric_cols = [col for col in columns if any(term in col.lower() for term in ['amount', 'price', 'value', 'cost', 'revenue', 'sales', 'income', 'profit', 'score', 'rating'])]
            if len(numeric_cols) >= 1:
                col = numeric_cols[0]
                return f"SELECT COUNT(*) as total_records, SUM({col}) as total, AVG({col}) as average, MIN({col}) as minimum, MAX({col}) as maximum FROM {table_name}"
        
        # Advanced pattern matching for business scenarios
        elif any(phrase in query_lower for phrase in ['customer', 'client']):
            customer_cols = [col for col in columns if any(term in col.lower() for term in ['customer', 'client', 'user', 'account', 'name'])]
            if customer_cols:
                limit_clause = " LIMIT 20" if use_limits else ""
                return f"SELECT {customer_cols[0]}, COUNT(*) as transactions FROM {table_name} GROUP BY {customer_cols[0]} ORDER BY transactions DESC{limit_clause}"
        
        elif any(phrase in query_lower for phrase in ['product', 'item']):
            product_cols = [col for col in columns if any(term in col.lower() for term in ['product', 'item', 'sku', 'name'])]
            if product_cols:
                limit_clause = " LIMIT 20" if use_limits else ""
                return f"SELECT {product_cols[0]}, COUNT(*) as frequency FROM {table_name} GROUP BY {product_cols[0]} ORDER BY frequency DESC{limit_clause}"
        
        # For any other query, return comprehensive overview
        limit_clause = " LIMIT 10" if use_limits else ""
        return f"SELECT * FROM {table_name}{limit_clause}"
    
    def generate_chart_if_requested(self, df: pd.DataFrame, query: str) -> str:
        """Only generate charts when user specifically requests visualization"""
        # Check if user is asking for a chart/graph/plot
        chart_keywords = [
            'chart', 'graph', 'plot', 'visualize', 'visualization', 'show me a chart',
            'create a graph', 'plot this', 'make a chart', 'draw a graph', 'bar chart',
            'line chart', 'pie chart', 'scatter plot', 'histogram', 'visual'
        ]
        
        query_lower = query.lower()
        if not any(keyword in query_lower for keyword in chart_keywords):

            return None

        return self.generate_chart(df, query)
    
    def generate_chart(self, df: pd.DataFrame, query: str) -> str:
        """Let Gemini AI handle ALL chart generation intelligently"""
        if df.empty or len(df) == 0:
            return None
        
        try:
            # Always use AI - it's smarter than hardcoded logic
            return self.create_ai_chart(df, query)
            
        except Exception as e:

            return self.create_simple_fallback_chart(df, query)
    
    def create_ai_chart(self, df: pd.DataFrame, query: str) -> str:
        """Let Gemini AI understand the data and create the perfect chart"""
        if not self.model:
            return self.create_simple_fallback_chart(df, query)
        
        try:
            # Get data summary for AI
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            text_cols = df.select_dtypes(include=[object]).columns.tolist()
            
            # Let AI see sample data to be smart about it
            sample_data = df.head(3).to_string(index=False) if len(df) > 3 else df.to_string(index=False)
            
            prompt = f"""You are a data visualization expert. Create the perfect chart for this request.

USER REQUEST: "{query}"

DATA INFO:
- Rows: {len(df)}
- Numeric columns: {numeric_cols}
- Text/Category columns: {text_cols}
- Sample data:
{sample_data}

Analyze the data and request, then return ONLY this format:
chart_type: bar/line/scatter/pie/histogram/box/heatmap/area
x_column: best_column_for_x_axis
y_column: best_column_for_y_axis
title: Perfect Chart Title
style: colorful/professional/minimal

Be smart about:
- Date/time data for trends
- Sales/revenue data for business charts
- Categories for grouping
- What the user actually wants to see"""

            response = self.fast_model.generate_content(prompt) if self.fast_model else self.model.generate_content(prompt)
            
            # Parse AI response
            lines = response.text.strip().split('\n')
            chart_config = {}
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    chart_config[key.strip()] = value.strip()
            
            # Create chart based on AI decisions
            return self.create_smart_chart(df, chart_config, query)
            
        except Exception as e:

            return self.create_simple_fallback_chart(df, query)
    
    def create_smart_chart(self, df: pd.DataFrame, config: dict, query: str) -> str:
        """Create chart based on AI's smart decisions"""
        chart_type = config.get('chart_type', 'bar')
        x_col = config.get('x_column', '')
        y_col = config.get('y_column', '')
        title = config.get('title', 'Data Visualization')
        style = config.get('style', 'professional')

        # Set colors based on style
        if style == 'colorful':
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD']
        else:
            colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#592E83']
        
        plt.figure(figsize=(12, 7))
        
        try:
            # Let AI's column choices guide the chart
            if chart_type == 'line' and x_col in df.columns and y_col in df.columns:
                plt.plot(df[x_col], df[y_col], marker='o', linewidth=3, color=colors[0], markersize=6)
                if style == 'colorful':
                    plt.fill_between(df[x_col], df[y_col], alpha=0.3, color=colors[0])
                plt.xticks(rotation=45, ha='right')
                
            elif chart_type == 'bar' and x_col in df.columns and y_col in df.columns:
                plt.bar(df[x_col], df[y_col], color=colors[:len(df)] if len(df) < len(colors) else colors[0], alpha=0.8)
                plt.xticks(rotation=45, ha='right')
                
            elif chart_type == 'scatter' and x_col in df.columns and y_col in df.columns:
                plt.scatter(df[x_col], df[y_col], c=colors[0], s=80, alpha=0.7, edgecolors=colors[1])
                
            elif chart_type == 'pie' and x_col in df.columns:
                if y_col in df.columns:
                    values = df.groupby(x_col)[y_col].sum()
                else:
                    values = df[x_col].value_counts()
                plt.pie(values.values, labels=values.index, autopct='%1.1f%%', colors=colors)
                
            elif chart_type == 'histogram' and y_col in df.columns:
                plt.hist(df[y_col], bins=20, alpha=0.7, color=colors[0], edgecolor=colors[1])
                
            else:
                # AI couldn't find columns, auto-detect
                numeric_cols = df.select_dtypes(include=[np.number]).columns
                text_cols = df.select_dtypes(include=[object]).columns
                
                if len(text_cols) > 0 and len(numeric_cols) > 0:
                    plt.bar(df[text_cols[0]], df[numeric_cols[0]], color=colors[0], alpha=0.8)
                    plt.xticks(rotation=45, ha='right')
                elif len(numeric_cols) >= 2:
                    plt.plot(df[numeric_cols[0]], df[numeric_cols[1]], marker='o', color=colors[0])
                else:
                    plt.hist(df[numeric_cols[0]], bins=20, color=colors[0]) if len(numeric_cols) > 0 else None
            
            plt.title(title, fontsize=16, weight='bold')
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            
            # Convert to base64
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close()
            
            if chart_data:  # Make sure we have valid chart data

                return f"data:image/png;base64,{chart_data}"
            else:

                return self.create_simple_fallback_chart(df, query)
            
        except Exception as e:

            plt.close()
            return self.create_simple_fallback_chart(df, query)
    
    def create_simple_fallback_chart(self, df, query):
        """Ultra-fast fallback chart"""
        plt.figure(figsize=(8, 5))
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        if len(df) == 1 and len(df.columns) == 1:
            # Single value display
            value = df.iloc[0, 0]
            plt.text(0.5, 0.5, f"{value:,}", ha='center', va='center', 
                    fontsize=32, weight='bold', transform=plt.gca().transAxes)
            plt.axis('off')
        elif len(numeric_cols) > 0:
            col = numeric_cols[0]
            if len(df) <= 15:
                plt.bar(range(len(df)), df[col], color='#2E86AB', alpha=0.8)
            else:
                plt.hist(df[col], bins=15, alpha=0.7, color='#2E86AB')
            plt.title(col.replace('_', ' ').title())
        
        plt.tight_layout()
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        chart_data = base64.b64encode(buffer.getvalue()).decode()
        plt.close()

        return f"data:image/png;base64,{chart_data}"

# File cleanup functions
def cleanup_old_files():
    """Remove uploaded files and charts older than FILE_RETENTION_HOURS"""
    try:
        current_time = time.time()
        cleanup_count = 0
        
        # Cleanup uploaded files
        upload_files = glob.glob(os.path.join(UPLOAD_FOLDER, "*"))
        for file_path in upload_files:
            if os.path.isfile(file_path):
                file_age_hours = (current_time - os.path.getctime(file_path)) / 3600
                if file_age_hours > FILE_RETENTION_HOURS:
                    try:
                        os.remove(file_path)
                        cleanup_count += 1

                    except OSError as e:

        # Cleanup chart files
        chart_files = glob.glob(os.path.join(CHARTS_FOLDER, "*"))
        for file_path in chart_files:
            if os.path.isfile(file_path):
                file_age_hours = (current_time - os.path.getctime(file_path)) / 3600
                if file_age_hours > FILE_RETENTION_HOURS:
                    try:
                        os.remove(file_path)
                        cleanup_count += 1

                    except OSError as e:

        if cleanup_count > 0:

        else:

    except Exception as e:

def cleanup_old_database_entries():
    """Remove database entries for files older than FILE_RETENTION_HOURS"""
    try:
        # Get list of table names to check which ones are old
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result.fetchall()]
            
        # You could add logic here to clean up database entries
        # For now, we'll keep the database entries as they're small

    except Exception as e:

def run_scheduled_cleanup():
    """Run scheduled file cleanup in background"""

    # Schedule cleanup every 2 hours
    schedule.every(2).hours.do(cleanup_old_files)
    schedule.every(2).hours.do(cleanup_old_database_entries)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

def start_cleanup_service():
    """Start the background cleanup service"""
    cleanup_thread = threading.Thread(target=run_scheduled_cleanup, daemon=True)
    cleanup_thread.start()
    
    # Run initial cleanup
    cleanup_old_files()

# Initialize processors
data_processor = DataProcessor()
ai_agent = AIAgent()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    user_id = request.form.get('user_id', f'user_{datetime.now().timestamp()}')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        try:
            # Process the Excel file
            processed_data = data_processor.process_excel_file(file_path, user_id)
            
            # Clean up uploaded file with retry logic for Windows file locking
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    time.sleep(0.1)  # Small delay to allow file handles to close
                    os.remove(file_path)
                    break
                except OSError as e:
                    if attempt == max_retries - 1:

                    else:
                        time.sleep(0.5)  # Wait longer before retry
            
            return jsonify({
                'message': 'File uploaded and processed successfully',
                'user_id': user_id,
                'processed_data': processed_data
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Invalid file type. Please upload Excel files only.'}), 400

@app.route('/api/query', methods=['POST'])
def process_query():
    try:
        data = request.json
        query = data.get('query', '')
        user_id = data.get('user_id', '')
        
        if not query or not user_id:
            return jsonify({'error': 'Query and user_id are required'}), 400
        
        # Get available tables for this user
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE :pattern"), {'pattern': f'{user_id}_%'})
            tables = result.fetchall()
        
        if not tables:
            return jsonify({'error': 'No data available. Please upload a file first.'}), 400
        
        # Get table info
        available_tables = {}
        for table in tables:
            table_name = table[0]
            with engine.connect() as conn:
                # Use direct SQL for PRAGMA since it doesn't support parameters
                result = conn.execute(text(f"PRAGMA table_info({table_name})"))
                columns = [row[1] for row in result.fetchall()]
                available_tables[table_name.replace(f'{user_id}_', '')] = {
                    'table_name': table_name,
                    'columns': columns
                }
        
        # Process query with AI agent
        response = ai_agent.analyze_query(query, available_tables)
        
        return jsonify(response)
        
    except Exception as e:

        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'gemini_initialized': ai_agent.model is not None
    })

# For Vercel deployment
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Start cleanup service
start_cleanup_service()

if __name__ == '__main__':
    # Local development
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # Production (Vercel)
    app.debug = False 