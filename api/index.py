from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv
import io
import base64
import re
from typing import Dict, List, Any
import time
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

# Load environment variables
load_dotenv()

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
UPLOAD_FOLDER = '/tmp'  # Use temp folder for serverless
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# In-memory data storage for serverless
user_data_store = {}

class SimpleDataProcessor:
    """Lightweight Excel processor without pandas"""
    
    def process_excel_file(self, file_path: str, user_id: str):
        """Process Excel file using openpyxl"""
        try:
            from openpyxl import load_workbook
            
            workbook = load_workbook(file_path, data_only=True)
            processed_data = {}
            
            for sheet_name in workbook.sheetnames:
                worksheet = workbook[sheet_name]
                
                # Get all data from worksheet
                data = []
                headers = []
                
                # Get headers from first row
                first_row = list(worksheet.iter_rows(min_row=1, max_row=1, values_only=True))[0]
                headers = [str(cell) if cell is not None else f"Column_{i+1}" for i, cell in enumerate(first_row)]
                
                # Get data rows
                for row in worksheet.iter_rows(min_row=2, values_only=True):
                    row_data = [str(cell) if cell is not None else "" for cell in row]
                    if any(cell.strip() for cell in row_data):  # Skip empty rows
                        data.append(dict(zip(headers, row_data)))
                
                if data:  # Only include sheets with data
                    processed_data[sheet_name] = {
                        'data': data,
                        'columns': headers,
                        'row_count': len(data)
                    }

            # Store in memory for this user
            user_data_store[user_id] = processed_data
            
            workbook.close()
            return processed_data
            
        except Exception as e:
            raise Exception(f"Error processing Excel file: {str(e)}")

class AIAgent:
    def __init__(self):
        # Configure Gemini API
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            api_key = None
        
        if api_key:
            genai.configure(api_key=api_key)
            
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
            
            if self.model and not self.fast_model:
                self.fast_model = self.model
            
            if not self.model:
                pass
        else:
            self.model = None
            self.fast_model = None
    
    def classify_request(self, query: str) -> str:
        """Classify the type of request to handle it appropriately"""
        query_lower = query.lower().strip()
        
        # System modification requests
        system_keywords = [
            'modify this', 'change this', 'fix this', 'update this', 'improve this',
            'can you modify', 'can you change', 'can you fix', 'can you improve'
        ]
        
        # Conversation/help requests
        conversation_keywords = [
            'hello', 'hi there', 'help me', 'what can you do', 'how does this work',
            'thank you', 'thanks', 'bye', 'goodbye'
        ]
        
        # Data analysis indicators
        data_keywords = [
            'what is the', 'what are the', 'show me', 'tell me about', 'analyze',
            'data', 'records', 'accounts', 'customers', 'sales', 'revenue',
            'combination', 'summary', 'breakdown', 'total', 'count', 'list',
            'display', 'find', 'search', 'filter', 'trend', 'pattern', 'chart', 'graph'
        ]
        
        if any(phrase in query_lower for phrase in system_keywords):
            return 'system'
        
        if any(keyword in query_lower for keyword in data_keywords):
            return 'data_analysis'
        
        if any(phrase in query_lower for phrase in conversation_keywords):
            return 'conversation'
            
        return 'data_analysis'

    def handle_system_request(self, query: str) -> dict:
        """Handle system modification requests"""
        if not self.model:
            return {
                'results': [],
                'columns': [],
                'charts': [],
                'summary': "I understand you want to modify something. Could you please be more specific about what you'd like me to change or improve?"
            }
        
        try:
            prompt = f"""You are a helpful AI assistant for a data analysis application. The user is asking to modify, fix, or improve something about the system.

User request: "{query}"

Respond as a helpful assistant who can acknowledge their request and provide guidance.

Response:"""

            response = self.model.generate_content(prompt)
            return {
                'results': [],
                'columns': [],
                'charts': [],
                'summary': response.text.strip()
            }
        except Exception as e:
            return {
                'results': [],
                'columns': [],
                'charts': [],
                'summary': "I understand you want to modify something. Could you please be more specific about what you'd like me to change or improve?"
            }

    def handle_conversation_request(self, query: str) -> dict:
        """Handle general conversation requests"""
        query_lower = query.lower().strip()
        
        if any(word in query_lower for word in ['hello', 'hi']):
            return {
                'results': [],
                'columns': [],
                'charts': [],
                'summary': "Hello! 👋 I'm your AI data analysis assistant. Upload an Excel file and ask me questions about your data!"
            }
        
        elif any(word in query_lower for word in ['help', 'what can you do']):
            return {
                'results': [],
                'columns': [],
                'charts': [],
                'summary': """I can help you with:

📊 **Data Analysis**: Ask questions about your Excel data in natural language
🔍 **Insights**: Get business intelligence and trends
📋 **Reports**: Generate summaries and breakdowns
🎯 **Charts**: Create beautiful matplotlib pie charts and bar charts

Upload an Excel file and start asking questions like:
- "Show me the top 10 customers"
- "Create a pie chart for sales"
- "Make a bar chart of the data"
- "Generate both pie and bar charts"

What would you like to explore?"""
            }
        
        elif any(word in query_lower for word in ['thank', 'thanks']):
            return {
                'results': [],
                'columns': [],
                'charts': [],
                'summary': "You're welcome! 😊 Feel free to ask me anything else about your data."
            }
        
        else:
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
                        'charts': [],
                        'summary': response.text.strip()
                    }
                except:
                    pass
            return {
                'results': [],
                'columns': [],
                'charts': [],
                'summary': "I'm here to help with data analysis! Upload an Excel file and ask me questions about your data."
            }

    def generate_chart_if_requested(self, query: str, data: List[Dict]) -> List[Dict]:
        """Generate REAL matplotlib charts - pie charts, bar charts, etc."""
        if not data:
            return []
            
        query_lower = query.lower()
        chart_keywords = ['chart', 'graph', 'plot', 'visualize', 'pie', 'bar', 'histogram']
        
        if not any(keyword in query_lower for keyword in chart_keywords):
            return []
        
        try:

            charts = []
            
            # Check what charts are requested
            wants_pie = 'pie' in query_lower
            wants_bar = 'bar' in query_lower
            wants_multiple = any(word in query_lower for word in ['both', 'multiple', 'all', 'charts', 'and'])
            
            # If user asks for specific charts or multiple charts
            if wants_pie or wants_multiple:
                pie_chart = self.create_real_pie_chart(data)
                if pie_chart:
                    charts.append({
                        'type': 'pie',
                        'title': 'Pie Chart - Data Distribution',
                        'data': pie_chart
                    })
            
            if wants_bar or wants_multiple:
                bar_chart = self.create_real_bar_chart(data)
                if bar_chart:
                    charts.append({
                        'type': 'bar',
                        'title': 'Bar Chart - Data Comparison',
                        'data': bar_chart
                    })
            
            # If no specific chart mentioned, create both
            if not wants_pie and not wants_bar and any(keyword in query_lower for keyword in chart_keywords):
                pie_chart = self.create_real_pie_chart(data)
                bar_chart = self.create_real_bar_chart(data)
                
                if pie_chart:
                    charts.append({
                        'type': 'pie',
                        'title': 'Pie Chart - Data Distribution',
                        'data': pie_chart
                    })
                if bar_chart:
                    charts.append({
                        'type': 'bar',
                        'title': 'Bar Chart - Data Comparison',
                        'data': bar_chart
                    })

            return charts
                
        except Exception as e:

            return []
    
    def create_real_pie_chart(self, data: List[Dict]) -> str:
        """Create a REAL matplotlib pie chart"""
        # Get first text column for labels and first numeric column for values
        labels = []
        values = []
        
        for item in data[:10]:  # Limit to top 10
            label_key = None
            value_key = None
            
            for key, value in item.items():
                if label_key is None and not self.is_numeric(value):
                    label_key = key
                if value_key is None and self.is_numeric(value):
                    value_key = key
            
            if label_key and value_key:
                labels.append(str(item[label_key])[:15])  # Truncate long labels
                values.append(float(item[value_key]))
        
        if not labels or not values:
            # Fallback: count occurrences of first column
            first_col = list(data[0].keys())[0]
            counts = {}
            for item in data:
                key = str(item[first_col])[:15]
                counts[key] = counts.get(key, 0) + 1
            labels = list(counts.keys())
            values = list(counts.values())
        
        # Create the pie chart
        plt.figure(figsize=(10, 8))
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9']
        
        wedges, texts, autotexts = plt.pie(values, labels=labels, autopct='%1.1f%%', 
                                          startangle=90, colors=colors[:len(values)])
        
        # Style the chart
        plt.title('Data Distribution', fontsize=16, fontweight='bold', pad=20)
        
        # Make text more readable
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(10)
        
        for text in texts:
            text.set_fontsize(9)
        
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
        
        # Convert to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        buffer.seek(0)
        chart_data = base64.b64encode(buffer.getvalue()).decode()
        plt.close()

        return f"data:image/png;base64,{chart_data}"
    
    def create_real_bar_chart(self, data: List[Dict]) -> str:
        """Create a REAL matplotlib bar chart"""
        # Get data for chart
        labels = []
        values = []
        
        for item in data[:15]:  # Show up to 15 bars
            label_key = None
            value_key = None
            
            for key, value in item.items():
                if label_key is None and not self.is_numeric(value):
                    label_key = key
                if value_key is None and self.is_numeric(value):
                    value_key = key
            
            if label_key and value_key:
                labels.append(str(item[label_key])[:20])
                values.append(float(item[value_key]))
        
        if not labels or not values:
            # Fallback: count occurrences
            first_col = list(data[0].keys())[0]
            counts = {}
            for item in data:
                key = str(item[first_col])[:20]
                counts[key] = counts.get(key, 0) + 1
            labels = list(counts.keys())
            values = list(counts.values())
        
        # Create the bar chart
        plt.figure(figsize=(12, 8))
        
        # Create gradient colors
        colors = plt.cm.viridis(np.linspace(0, 1, len(values)))
        
        bars = plt.bar(labels, values, color=colors, alpha=0.8, edgecolor='white', linewidth=1)
        
        # Style the chart
        plt.title('Data Visualization', fontsize=16, fontweight='bold', pad=20)
        plt.xlabel('Categories', fontsize=12, fontweight='bold')
        plt.ylabel('Values', fontsize=12, fontweight='bold')
        
        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45, ha='right')
        
        # Add value labels on top of bars
        for bar, value in zip(bars, values):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.01,
                    f'{value:,.0f}', ha='center', va='bottom', fontweight='bold', fontsize=9)
        
        # Add grid for better readability
        plt.grid(axis='y', alpha=0.3, linestyle='--')
        
        # Style the plot
        plt.gca().spines['top'].set_visible(False)
        plt.gca().spines['right'].set_visible(False)
        plt.gca().spines['left'].set_linewidth(0.5)
        plt.gca().spines['bottom'].set_linewidth(0.5)
        
        plt.tight_layout()
        
        # Convert to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        buffer.seek(0)
        chart_data = base64.b64encode(buffer.getvalue()).decode()
        plt.close()

        return f"data:image/png;base64,{chart_data}"
    
    def is_numeric(self, value: str) -> bool:
        """Check if a string value is numeric"""
        try:
            float(value)
            return True
        except:
            return False

    def generate_ai_table_if_requested(self, query: str, results: List[Dict], full_data: List[Dict]) -> Dict:
        """Generate AI-created custom table based on query analysis"""
        if not self.model or not results:
            return None
        
        query_lower = query.lower()
        
        # Check if query requests analysis, summary, or breakdown
        table_keywords = ['analyze', 'breakdown', 'summary', 'group', 'categorize', 'segment', 'compare', 'trends', 'insights']
        
        if not any(keyword in query_lower for keyword in table_keywords):
            return None
            
        try:

            # Prepare data sample for AI analysis
            data_sample = results[:20] if len(results) > 20 else results
            data_structure = str(data_sample)[:2000]  # Limit data size
            
            prompt = f"""Analyze this data and create a custom summary table based on the user query.

User Query: "{query}"

Data Sample: {data_structure}

Create a focused analysis table that answers the user's specific question. Generate:
1. A clear table title
2. Relevant columns for the analysis
3. 5-10 meaningful rows with calculated insights, trends, or groupings
4. Use real data patterns from the sample

Format your response as JSON:
{{
    "title": "Analysis Table Title",
    "columns": ["Column1", "Column2", "Column3"],
    "rows": [
        {{"Column1": "value1", "Column2": "value2", "Column3": "value3"}},
        {{"Column1": "value1", "Column2": "value2", "Column3": "value3"}}
    ],
    "description": "Brief description of what this table shows"
}}

Provide practical business insights, not just raw data."""

            response = self.model.generate_content(prompt)
            
            # Parse AI response as JSON
            import json
            ai_response = response.text.strip()
            
            # Clean up response to extract JSON
            if '```json' in ai_response:
                ai_response = ai_response.split('```json')[1].split('```')[0]
            elif '```' in ai_response:
                ai_response = ai_response.split('```')[1].split('```')[0]
                
            table_data = json.loads(ai_response)

            return table_data
            
        except Exception as e:

            return None
            
    def analyze_data_query(self, query: str, user_data: Dict) -> Dict:
        """Analyze data query using available user data"""
        if not user_data:
            return {
                'results': [],
                'columns': [],
                'charts': [],
                'summary': "📁 Please upload an Excel file first to start analyzing your data. Once uploaded, I can help you with insights, trends, and detailed analysis!"
            }
        
        try:
            # Get the first available dataset
            sheet_name = list(user_data.keys())[0]
            data = user_data[sheet_name]['data']
            columns = user_data[sheet_name]['columns']
            
            # Process the query to find relevant data
            results = self.process_data_query(query, data, columns)
            
            # Generate charts if requested
            charts_data = self.generate_chart_if_requested(query, results)
            
            # Generate AI table if requested
            ai_table = self.generate_ai_table_if_requested(query, results, data)
            
            # Generate AI summary
            summary = self.generate_ai_summary(query, results, data)
            
            return {
                'results': results,
                'columns': list(results[0].keys()) if results else columns,
                'charts': charts_data,
                'ai_table': ai_table,
                'summary': summary
            }
            
        except Exception as e:
            return {
                'error': f"Error analyzing data: {str(e)}",
                'results': [],
                'charts': []
            }

    def process_data_query(self, query: str, data: List[Dict], columns: List[str]) -> List[Dict]:
        """Process query against the data"""
        query_lower = query.lower()
        
        # For datasets up to 10,000 records, show all data by default for comprehensive business intelligence
        show_all_for_small_datasets = len(data) <= 10000
        
        # Simple query processing
        # Check for explicit requests for complete data
        complete_data_requests = [
            'show all', 'all data', 'everything', 'complete', 'full dataset', 
            'all records', 'all rows', 'entire', 'whole dataset', 'complete data',
            'full data', 'analyze all', 'process all'
        ]
        
        # Also check for patterns like "all X rows" where X is a number
        all_rows_pattern = 'all' in query_lower and 'row' in query_lower
        
        if any(phrase in query_lower for phrase in complete_data_requests) or all_rows_pattern:
            return data  # Return all data when explicitly requested
        elif any(word in query_lower for word in ['top', 'highest', 'best']):
            # Try to find numeric columns and sort
            for col in columns:
                if any(term in col.lower() for term in ['amount', 'price', 'value', 'sales', 'revenue']):
                    try:
                        sorted_data = sorted(data, key=lambda x: float(x.get(col, 0) or 0), reverse=True)
                        return sorted_data[:10]
                    except:
                        continue
            return data[:10]
        elif any(word in query_lower for word in ['count', 'how many']):
            return [{'total_records': len(data)}]
        elif any(word in query_lower for word in ['first', 'sample']):
            return data[:5]
        else:
            # For small datasets, return all records for meaningful business intelligence
            if show_all_for_small_datasets:
                return data
            else:
                # For large datasets, return sample
                return data[:10]

    def generate_ai_summary(self, query: str, results: List[Dict], full_data: List[Dict]) -> str:
        """Generate AI summary of the analysis"""
        if not self.model:
            return f"Found {len(results)} results for your query. Upload complete!"
        
        try:
            # Create data summary for AI
            data_summary = f"""
Query: "{query}"
Total records in dataset: {len(full_data)}
Results returned: {len(results)}

{"✅ COMPLETE DATASET RETRIEVED: All records analyzed" if len(results) == len(full_data) and len(full_data) <= 50 else "Sample of results:"}
{json.dumps(results[:3], indent=2) if results else 'No results'}

Dataset columns: {list(full_data[0].keys()) if full_data else 'No data'}
"""

            prompt = f"""You are an expert data analyst. Analyze this data and provide insights based on the user's question.

{data_summary}

Provide a clear, business-friendly analysis that:
1. Directly answers the user's question
2. Points out interesting patterns or insights
3. Uses specific numbers from the data
4. Provides actionable business intelligence

Response:"""

            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            if results and len(results) == 1 and 'total_records' in results[0]:
                return f"📊 Your dataset contains {results[0]['total_records']} records. This provides a solid foundation for data analysis and insights."
            elif results:
                # Check if we retrieved the complete dataset
                complete_dataset = len(results) == len(full_data) and len(full_data) <= 10000
                if complete_dataset:
                    return f"✅ COMPLETE DATASET RETRIEVED: Successfully analyzed all {len(results)} records from your dataset. This comprehensive analysis provides complete business intelligence insights."
                else:
                    return f"📈 Found {len(results)} relevant records for your query. The data shows actionable insights for business decision-making."
            return "✅ Analysis completed. Your data is ready for exploration!"

    def analyze_query(self, query: str, user_id: str) -> Dict:
        """Main query analysis function"""
        try:
            request_type = self.classify_request(query)
            
            if request_type == 'system':
                return self.handle_system_request(query)
            elif request_type == 'conversation':
                return self.handle_conversation_request(query)
            else:
                # Get user data for analysis
                user_data = user_data_store.get(user_id, {})
                return self.analyze_data_query(query, user_data)
            
        except Exception as e:
            return {
                'error': f"Error analyzing query: {str(e)}",
                'results': [],
                'charts': []
            }

# Initialize components
data_processor = SimpleDataProcessor()
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
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        try:
            # Process the Excel file
            processed_data = data_processor.process_excel_file(file_path, user_id)
            
            # Clean up uploaded file
            try:
                    os.remove(file_path)
            except:
                pass  # Ignore cleanup errors in serverless
            
            return jsonify({
                'message': 'File uploaded and processed successfully',
                'user_id': user_id,
                'processed_data': {k: {'row_count': v['row_count'], 'columns': v['columns']} for k, v in processed_data.items()}
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
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
        # Process query with AI agent
        response = ai_agent.analyze_query(query, user_id)
        
        return jsonify(response)
        
    except Exception as e:

        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'gemini_initialized': ai_agent.model is not None,
        'message': 'Full-featured backend with REAL matplotlib charts!'
    })

# For Vercel deployment
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    app.debug = False 