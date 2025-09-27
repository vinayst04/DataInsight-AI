# AI Data Agent - SDE Hiring Assignment

A conversational interface platform where users can upload Excel files and ask complex business questions about their data in natural language. The system analyzes the uploaded data and provides answers with relevant charts and tables.

## Features

- **File Upload System**: Accepts Excel files (.xlsx, .xls) and converts them for analysis
- **Natural Language Processing**: AI agent that understands user questions about their uploaded data
- **Data Visualization**: Automatic chart generation based on query context
- **Robust Data Handling**: Handles any Excel file format, bad/inconsistent data formatting, unnamed columns, dirty or incomplete data, and vague natural language questions
- **Real-time Chat Interface**: Interactive conversational UI with typing indicators and message history

## Technology Stack

- **Frontend**: React.js
- **Backend**: Python Flask
- **Database**: SQLite (SQL database as specified)
- **AI Processing**: Google Gemini AI for sophisticated natural language understanding and SQL generation
- **Data Processing**: Pandas, NumPy
- **Visualization**: Matplotlib, Seaborn

## Project Structure

```
intern project/
├── backend/
│   └── app.py                # Flask backend with AI agent and data processing
├── frontend/
│   ├── public/
│   │   └── index.html        # HTML template
│   ├── src/
│   │   ├── App.js            # Main React component
│   │   ├── App.css           # Styling
│   │   ├── index.js          # React entry point
│   │   └── index.css         # Base CSS
│   └── package.json          # Frontend dependencies
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## Setup Instructions

### Backend Setup

1. Navigate to the project root directory:
```bash
cd "intern project"
```

2. Create a Python virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
- Windows:
```bash
venv\Scripts\activate
```
- macOS/Linux:
```bash
source venv/bin/activate
```

4. Install Python dependencies:
```bash
pip install -r requirements.txt
```

5. Set up your Gemini API key:
   - Create a `.env.local` file in the project root directory
   - Add this line to the file:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

6. Start the Flask backend:
```bash
cd backend
python app.py
```

The backend will run on `http://localhost:5000`

### Frontend Setup

1. Open a new terminal and navigate to the frontend directory:
```bash
cd "intern project/frontend"
```

2. Install Node.js dependencies:
```bash
npm install
```

3. Start the React development server:
```bash
npm start
```

The frontend will run on `http://localhost:3000`

## Usage

1. **Upload Excel File**: Click the upload button and select any Excel file (.xlsx or .xls)
2. **Ask Complex Business Questions**: Type sophisticated natural language questions such as:
   - "What are the top 10 customers by revenue?"
   - "Show me monthly sales trends over time"
   - "Which product category has the highest profit margin?"
   - "Compare performance between different regions"
   - "Find customers who haven't purchased in the last 6 months"
   - "Calculate year-over-year growth rates"
3. **View Results**: Get instant answers with relevant charts, tables, and data summaries

## Key Capabilities

### Data Processing
- Handles any Excel file structure including multiple sheets
- Cleans and processes inconsistent data formatting
- Manages unnamed columns and sheets
- Processes dirty or incomplete data
- Stores data in SQL database for efficient querying

### AI Agent Features (Powered by Google Gemini)
- Advanced natural language understanding for complex business questions
- Intelligent SQL query generation with fuzzy column matching
- Context-aware chart generation based on query intent
- Smart business insights and pattern recognition
- Sophisticated data analysis with trend identification
- Automatic handling of vague or unclear questions with fallback logic

### Excel File Compatibility
- Supports .xlsx and .xls formats
- Handles multiple sheets per file
- Processes files with irregular structures
- Manages missing or corrupted data gracefully

## API Endpoints

- `POST /api/upload` - Upload and process Excel files
- `POST /api/query` - Process natural language queries
- `GET /api/health` - Health check endpoint

## Development Notes

- The system uses Google Gemini AI for sophisticated natural language understanding with pattern matching fallback
- Charts are generated as base64 encoded images with enhanced visualization logic
- Data is stored per user session for privacy using SQLite database
- Frontend includes responsive design for mobile compatibility
- All file uploads are processed and cleaned before storage
- Gemini AI provides intelligent SQL generation and business-friendly summaries
- System gracefully handles AI failures with robust fallback mechanisms

## Demo

The application provides an intuitive chat interface where users can:
1. Upload their Excel data files
2. Ask business questions in plain English
3. Receive immediate answers with visualizations
4. Continue the conversation to explore their data further

This solution demonstrates exceptional analytical capabilities beyond basic query translation, handling complex real-world data scenarios that users commonly encounter with Excel files. 