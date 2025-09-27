import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { saveChatMessage, loadChatHistory, clearUserChatHistory } from './firebase';
import './App.css';

// Dynamic API base URL for development and production
const API_BASE = process.env.NODE_ENV === 'production' 
  ? process.env.REACT_APP_API_URL || 'https://your-backend-url.vercel.app/api'
  : 'http://localhost:5000/api';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [userId, setUserId] = useState(null);
  const [file, setFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [displayMode, setDisplayMode] = useState('both'); // 'charts', 'table', 'both'
  const [showAllResults, setShowAllResults] = useState(false);
  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    const savedUserId = localStorage.getItem('userId');
    if (savedUserId) {
      setUserId(savedUserId);
      // Load chat history from Firebase
      loadChatHistory(savedUserId).then(history => {
        if (history.length > 0) {
          setMessages(history);
  
        }
      });
    }
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleFileUpload = async (uploadedFile) => {
    if (!uploadedFile) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', uploadedFile);
    
    const newUserId = userId || `user_${Date.now()}`;
    formData.append('user_id', newUserId);

    try {
      const response = await axios.post(`${API_BASE}/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (!userId) {
        setUserId(newUserId);
        localStorage.setItem('userId', newUserId);
      }

      const uploadMessage = {
        type: 'system',
        content: `File "${uploadedFile.name}" uploaded successfully! You can now ask questions about your data.`,
        timestamp: new Date().toLocaleTimeString(),
        fileInfo: response.data.processed_data
      };

      setMessages(prev => [...prev, uploadMessage]);
      
      // Save to Firebase
      if (newUserId) {
        saveChatMessage(newUserId, uploadMessage).catch(() => {});
      }
      setFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }

    } catch (error) {
      const errorMessage = {
        type: 'error',
        content: `Error uploading file: ${error.response?.data?.error || error.message}`,
        timestamp: new Date().toLocaleTimeString()
      };
      setMessages(prev => [...prev, errorMessage]);
      
      // Save error to Firebase
      if (newUserId) {
        saveChatMessage(newUserId, errorMessage).catch(() => {});
      }
    } finally {
      setIsUploading(false);
    }
  };

  const handleFileSelect = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  const uploadFile = () => {
    if (file) {
      handleFileUpload(file);
    }
  };

  const sendQuery = async () => {
    if (!input.trim() || !userId) return;

    const userMessage = {
      type: 'user',
      content: input,
      timestamp: new Date().toLocaleTimeString()
    };

    setMessages(prev => [...prev, userMessage]);
    
    // Save user message to Firebase
    saveChatMessage(userId, userMessage).catch(() => {});
    
    // Reset show all results for new queries
    setShowAllResults(false);
    
    setIsLoading(true);
    const query = input;
    setInput('');

    try {
      const response = await axios.post(`${API_BASE}/query`, {
        query: query,
        user_id: userId
      });

      // Improved content handling
      let content;
      if (response.data.error) {
        content = `❌ ${response.data.error}`;
      } else if (response.data.summary) {
        content = response.data.summary;
      } else if (response.data.results && response.data.results.length > 0) {
        content = `Found ${response.data.results.length} results for your query.`;
      } else {
        content = 'Here are the results for your query:';
      }

      const aiMessage = {
        type: 'assistant',
        content: content,
        timestamp: new Date().toLocaleTimeString(),
        data: response.data
      };

      setMessages(prev => [...prev, aiMessage]);
      
      // Save AI response to Firebase
      saveChatMessage(userId, aiMessage).catch(() => {});

    } catch (error) {
      let errorContent;
      if (error.response?.status === 400 && error.response?.data?.error?.includes('No data available')) {
        errorContent = '📁 Please upload an Excel file first before asking questions about your data.';
      } else {
        errorContent = `Error: ${error.response?.data?.error || error.message}`;
      }
      
      const errorMessage = {
        type: 'error',
        content: errorContent,
        timestamp: new Date().toLocaleTimeString()
      };
      setMessages(prev => [...prev, errorMessage]);
      
      // Save error to Firebase
              saveChatMessage(userId, errorMessage).catch(() => {});
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuery();
    }
  };

  const clearChatHistory = async () => {
    if (!userId) return;
    
    try {
      await clearUserChatHistory(userId);
      setMessages([]);
    } catch (error) {
    }
  };

  const renderMessage = (message, index) => {
    const { type, content, timestamp, data, fileInfo } = message;

    return (
      <div key={index} className={`message ${type}`}>
        <div className="message-header">
          <span className="message-type">
            {type === 'user' ? '👤 You' : type === 'assistant' ? '🤖 AI Assistant' : type === 'system' ? '📁 System' : '❌ Error'}
          </span>
          <span className="timestamp">{timestamp}</span>
        </div>
        
        <div className="message-content">
          {type === 'assistant' ? (
            <ReactMarkdown>{content}</ReactMarkdown>
          ) : (
            content
          )}
          
          {fileInfo && (
            <div className="file-info">
              <h4>📊 Data Summary:</h4>
              {Object.entries(fileInfo).map(([sheetName, info]) => (
                <div key={sheetName} className="sheet-info">
                  <strong>Sheet: {sheetName}</strong>
                  <ul>
                    <li>Rows: {info.row_count}</li>
                    <li>Columns: {info.columns.join(', ')}</li>
                  </ul>
                </div>
              ))}
            </div>
          )}

          {data && (
            <div className="query-results">
              {data.results && data.results.length > 0 && (
                <div className="results-table">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                    <strong>Results:</strong>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                        {data.results.length} total records
                      </span>
                      {data.results.length > 50 && (
                        <button 
                          onClick={() => setShowAllResults(!showAllResults)}
                          style={{
                            padding: '4px 12px',
                            fontSize: '0.75rem',
                            backgroundColor: 'var(--btn-primary)',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            cursor: 'pointer',
                            transition: 'all 0.2s ease'
                          }}
                          onMouseOver={(e) => e.target.style.backgroundColor = 'var(--btn-primary-hover)'}
                          onMouseOut={(e) => e.target.style.backgroundColor = 'var(--btn-primary)'}
                        >
                          {showAllResults ? 'Show Less' : 'Show All'}
                        </button>
                      )}
                    </div>
                  </div>
                  <table>
                    <thead>
                      <tr>
                        {data.columns.map(col => (
                          <th key={col}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(showAllResults ? data.results : data.results.slice(0, 50)).map((row, idx) => (
                        <tr key={idx}>
                          {data.columns.map(col => (
                            <td key={col}>{row[col]}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!showAllResults && data.results.length > 50 && (
                    <p className="results-note">
                      Showing first 50 of {data.results.length} results. 
                      <button 
                        onClick={() => setShowAllResults(true)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'var(--btn-primary)',
                          textDecoration: 'underline',
                          cursor: 'pointer',
                          fontSize: 'inherit',
                          padding: '0 4px'
                        }}
                      >
                        Click "Show All" to see more
                      </button>
                    </p>
                  )}
                  {showAllResults && data.results.length > 50 && (
                    <p className="results-note">
                      Showing all {data.results.length} results
                    </p>
                  )}
                </div>
              )}

              {data.chart && (
                <div className="chart">
                  <strong>Visualization:</strong>
                  <img src={data.chart} alt="Data visualization" />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="App">
      <header className="app-header">
        <div className="header-content">
          <div className="title-section">
            <h1>DataInsight</h1>
            <p>Intelligent data analysis powered by AI</p>
          </div>
          {messages.length > 0 && (
            <button 
              onClick={clearChatHistory}
              className="clear-chat-btn"
              title="Clear chat history"
            >
              🗑️ Clear History
            </button>
          )}
        </div>
      </header>

      <div className="chat-container">
        <div className="messages-container">
          {messages.length === 0 && (
            <div className="welcome-message">
              <h3>Welcome to DataInsight</h3>
              <p>Upload your Excel data and ask questions in natural language</p>
              <div className="quick-start">
                <div className="step">
                  <span className="step-number">1</span>
                  <span>Upload Excel file using the 📎 button</span>
                </div>
                <div className="step">
                  <span className="step-number">2</span>
                  <span>Ask questions about your data</span>
                </div>
                <div className="step">
                  <span className="step-number">3</span>
                  <span>Get instant insights and visualizations</span>
                </div>
              </div>
            </div>
          )}
          
          {messages.map((message, index) => renderMessage(message, index))}
          
          {isLoading && (
            <div className="message assistant loading">
              <div className="message-header">
                <span className="message-type">🤖 AI Assistant</span>
              </div>
              <div className="message-content">
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                Analyzing your query...
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        <div className="input-container">
          <div className="input-row">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={userId ? "Ask a question about your data..." : "Please upload a file first"}
              disabled={!userId || isLoading}
              rows="2"
              className="chat-input"
            />
            <div className="input-buttons">
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileSelect}
                accept=".xlsx,.xls"
                style={{ display: 'none' }}
              />
              <button 
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                className="upload-btn"
                title="Upload Excel file"
              >
                {isUploading ? '📤⏳' : '📎'}
              </button>
              <button 
                onClick={sendQuery}
                disabled={!input.trim() || !userId || isLoading}
                className="send-btn"
              >
                {isLoading ? '⏳' : '📤'}
              </button>
            </div>
          </div>
          {file && !isUploading && (
            <div className="selected-file">
              📄 Selected: {file.name}
              <button onClick={uploadFile} className="upload-confirm-btn">
                Upload File
              </button>
              <button onClick={() => setFile(null)} className="cancel-btn">
                ✖
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App; 