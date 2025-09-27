import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { saveChatMessage, loadChatHistory, clearUserChatHistory } from './firebase';
import './App.css';

// Dynamic API base URL for unified deployment
const API_BASE = process.env.NODE_ENV === 'production' 
  ? '/api'  // Same domain in production (unified deployment)
  : 'http://localhost:5000/api';  // Separate backend in development

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [userId, setUserId] = useState(null);
  const [file, setFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [currentResults, setCurrentResults] = useState(null);
  const [currentCharts, setCurrentCharts] = useState([]);
  const [currentAiTable, setCurrentAiTable] = useState(null);
  const [showAllResults, setShowAllResults] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [displayMode, setDisplayMode] = useState('both'); // 'charts', 'table', 'both'
  const [mobileResultsOpen, setMobileResultsOpen] = useState(false);
  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    const savedUserId = localStorage.getItem('userId');
    const savedDarkMode = localStorage.getItem('darkMode') === 'true';
    setDarkMode(savedDarkMode);
    
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

  const toggleDarkMode = () => {
    const newDarkMode = !darkMode;
    setDarkMode(newDarkMode);
    localStorage.setItem('darkMode', newDarkMode.toString());
  };

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
    
    // Detect display preference from user query
    const query = input.toLowerCase();
    if (query.includes('show graph') || query.includes('show chart') || query.includes('create graph') || query.includes('create chart') || query.includes('visualize') || query.includes('plot')) {
      setDisplayMode('charts');
    } else if (query.includes('show table') || query.includes('show data') || query.includes('tabular') || query.includes('rows') || query.includes('columns')) {
      setDisplayMode('table');
    } else {
      setDisplayMode('both');
    }
    
    setIsLoading(true);
    const queryText = input;
    setInput('');

    try {
      const response = await axios.post(`${API_BASE}/query`, {
        query: queryText,
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
        timestamp: new Date().toLocaleTimeString()
      };

      setMessages(prev => [...prev, aiMessage]);
      
      // Update separate results, charts, and AI table state
      if (response.data.results && response.data.results.length > 0) {
        setCurrentResults(response.data);
        setShowAllResults(false); // Reset to show limited view for new queries
      }
      if (response.data.charts && response.data.charts.length > 0) {
        setCurrentCharts(response.data.charts);
      }
      if (response.data.ai_table) {
        setCurrentAiTable(response.data.ai_table);
      }
      
      // Save AI response to Firebase (without data to keep chat clean)
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
      setCurrentResults(null);
      setCurrentCharts([]);
      setCurrentAiTable(null);
    } catch (error) {
    }
  };

  const newChat = () => {
    setMessages([]);
    setCurrentResults(null);
    setCurrentCharts([]);
    setCurrentAiTable(null);
  };

  const renderMessage = (message, index) => {
    const { type, content, timestamp, fileInfo } = message;

    return (
      <div key={index} className={`message-wrapper ${type}`}>
        <div className="message-container">
          <div className="message-avatar">
            {type === 'user' ? (
              <div className="avatar user-avatar">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                </svg>
              </div>
            ) : type === 'assistant' ? (
              <div className="avatar assistant-avatar">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                </svg>
              </div>
            ) : (
              <div className="avatar system-avatar">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                </svg>
              </div>
            )}
          </div>
          <div className="message-content">
            <div className="message-header">
              <span className="message-sender">
                {type === 'user' ? 'You' : type === 'assistant' ? 'DataInsight' : type === 'system' ? 'System' : 'Error'}
              </span>
              <span className="message-time">{timestamp}</span>
            </div>
            <div className="message-text">
              {type === 'assistant' ? (
                <ReactMarkdown>{content}</ReactMarkdown>
              ) : (
                <p>{content}</p>
              )}
              
              {fileInfo && (
                <div className="file-info-card">
                  <div className="file-info-header">
                    <svg className="file-icon" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
                    </svg>
                    <span>Data Summary</span>
                  </div>
                  {Object.entries(fileInfo).map(([sheetName, info]) => (
                    <div key={sheetName} className="sheet-summary">
                      <div className="sheet-name">{sheetName}</div>
                      <div className="sheet-details">
                        <span className="detail-item">
                          <span className="detail-label">Rows:</span>
                          <span className="detail-value">{info.row_count}</span>
                        </span>
                        <span className="detail-item">
                          <span className="detail-label">Columns:</span>
                          <span className="detail-value">{info.columns.join(', ')}</span>
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className={`app ${darkMode ? 'dark-mode' : 'light-mode'}`}>
      {/* Sidebar */}
      <div className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <div className="sidebar-header">
          <div className="logo">
            <svg className="logo-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M9,17H15V15H9V17M9,13H15V11H9V13M9,9H15V7H9V9M5,19H19V5H5V19M5,3H19A2,2 0 0,1 21,5V19A2,2 0 0,1 19,21H5A2,2 0 0,1 3,19V5A2,2 0 0,1 5,3Z" />
            </svg>
            <span>DataInsight</span>
          </div>
          <button 
            className="sidebar-toggle mobile-only"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
            </svg>
          </button>
        </div>
        
        <div className="sidebar-actions">
          <button 
            className="sidebar-btn primary"
            onClick={newChat}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z" />
            </svg>
            New Chat
          </button>
          
          <button 
            className="sidebar-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
            </svg>
            {isUploading ? 'Uploading...' : 'Upload File'}
          </button>
        </div>

        <div className="sidebar-footer">
          <button 
            className="sidebar-btn"
            onClick={toggleDarkMode}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              {darkMode ? (
                <path d="M12,18V6A6,6 0 0,1 18,12A6,6 0 0,1 12,18Z" />
              ) : (
                <path d="M12,8A4,4 0 0,0 8,12A4,4 0 0,0 12,16A4,4 0 0,0 16,12A4,4 0 0,0 12,8Z" />
              )}
            </svg>
            {darkMode ? 'Light Mode' : 'Dark Mode'}
          </button>
          
          {messages.length > 0 && (
            <button 
              className="sidebar-btn danger"
              onClick={clearChatHistory}
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z" />
              </svg>
              Clear History
            </button>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="main-container">
        {/* Header */}
        <header className="main-header">
          <button 
            className="sidebar-toggle desktop-hidden"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z" />
            </svg>
          </button>
          <div className="header-title">
            <h1>DataInsight AI</h1>
            <p>Intelligent data analysis powered by AI</p>
          </div>
        </header>

        {/* Chat Content */}
        <div className="chat-content">
          <div className="messages-section">
            {messages.length === 0 ? (
              <div className="welcome-screen">
                <div className="welcome-content">
                  <div className="welcome-icon">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path d="M9,17H15V15H9V17M9,13H15V11H9V13M9,9H15V7H9V9M5,19H19V5H5V19M5,3H19A2,2 0 0,1 21,5V19A2,2 0 0,1 19,21H5A2,2 0 0,1 3,19V5A2,2 0 0,1 5,3Z" />
                    </svg>
                  </div>
                  <h2>Welcome to DataInsight</h2>
                  <p>Upload your Excel data and start asking questions in natural language</p>
                  
                  <div className="welcome-steps">
                    <div className="welcome-step">
                      <div className="step-number">1</div>
                      <div className="step-content">
                        <h3>Upload Data</h3>
                        <p>Click the upload button to add your Excel file</p>
                      </div>
                    </div>
                    <div className="welcome-step">
                      <div className="step-number">2</div>
                      <div className="step-content">
                        <h3>Ask Questions</h3>
                        <p>Type natural language questions about your data</p>
                      </div>
                    </div>
                    <div className="welcome-step">
                      <div className="step-number">3</div>
                      <div className="step-content">
                        <h3>Get Insights</h3>
                        <p>Receive instant analysis and visualizations</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="messages-container">
                {messages.map((message, index) => renderMessage(message, index))}
                
                {isLoading && (
                  <div className="message-wrapper assistant">
                    <div className="message-container">
                      <div className="message-avatar">
                        <div className="avatar assistant-avatar">
                          <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                          </svg>
                        </div>
                      </div>
                      <div className="message-content">
                        <div className="message-header">
                          <span className="message-sender">DataInsight</span>
                        </div>
                        <div className="message-text">
                          <div className="typing-indicator">
                            <div className="typing-dots">
                              <span></span>
                              <span></span>
                              <span></span>
                            </div>
                            <span>Analyzing your query...</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Data Results Panel */}
          {(currentResults || currentCharts?.length > 0 || currentAiTable) && (
            <div className={`results-panel ${mobileResultsOpen ? 'mobile-open' : ''}`}>
              {/* Mobile Close Button */}
              <button 
                className="mobile-close-btn"
                onClick={() => setMobileResultsOpen(false)}
                style={{ display: window.innerWidth <= 768 ? 'flex' : 'none' }}
              >
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
                </svg>
              </button>
              {/* Display Tables when mode is 'table' or 'both' */}
              {(displayMode === 'table' || displayMode === 'both') && currentResults && (
                <div className="results-section">
                  <div className="section-header">
                    <h3>
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M3,3H21V5H3V3M4,6H20V8H4V6M4,9H20V11H4V9M4,12H20V14H4V12M4,15H20V17H4V15M4,18H20V20H4V18Z" />
                      </svg>
                      Data Results
                    </h3>
                    <div className="section-controls">
                      <span className="results-count">{currentResults.results.length} records</span>
                      {currentResults.results.length > 50 && (
                        <button 
                          className="toggle-btn"
                          onClick={() => setShowAllResults(!showAllResults)}
                        >
                          {showAllResults ? 'Show Less' : 'Show All'}
                        </button>
                      )}
                    </div>
                  </div>
                  
                  <div className="table-container">
                    <table className="data-table">
                      <thead>
                        <tr>
                          {currentResults.columns.map(col => (
                            <th key={col}>{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(showAllResults ? currentResults.results : currentResults.results.slice(0, 50)).map((row, idx) => (
                          <tr key={idx}>
                            {currentResults.columns.map(col => (
                              <td key={col}>{row[col]}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Display AI Tables when mode is 'table' or 'both' */}
              {(displayMode === 'table' || displayMode === 'both') && currentAiTable && (
                <div className="ai-analysis-section">
                  <div className="section-header">
                    <h3>
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                      </svg>
                      AI Analysis
                    </h3>
                    <span className="ai-badge">AI Generated</span>
                  </div>
                  
                  <div className="ai-analysis-content">
                    <h4>{currentAiTable.title}</h4>
                    <p>{currentAiTable.description}</p>
                    
                    <div className="table-container">
                      <table className="data-table ai-table">
                        <thead>
                          <tr>
                            {currentAiTable.columns.map(col => (
                              <th key={col}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {currentAiTable.rows.map((row, idx) => (
                            <tr key={idx}>
                              {currentAiTable.columns.map(col => (
                                <td key={col}>{row[col]}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {/* Display Charts when mode is 'charts' or 'both' */}
              {(displayMode === 'charts' || displayMode === 'both') && currentCharts && currentCharts.length > 0 && (
                <div className="charts-section">
                  <div className="section-header">
                    <h3>
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M22,21H2V3H4V19H6V10H10V19H12V6H16V19H18V14H22V21Z" />
                      </svg>
                      Visualizations
                    </h3>
                    <span className="charts-count">{currentCharts.length} chart{currentCharts.length > 1 ? 's' : ''}</span>
                  </div>
                  <div className="charts-grid">
                    {currentCharts.map((chart, index) => (
                      <div key={index} className="chart-item">
                        <h4>{chart.title}</h4>
                        <div className="chart-container">
                          <img src={chart.data} alt={chart.title} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="input-area">
          <div className="input-container">
            {file && !isUploading && (
              <div className="file-preview">
                <div className="file-info">
                  <svg className="file-icon" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
                  </svg>
                  <span>Selected: {file.name}</span>
                </div>
                <div className="file-actions">
                  <button onClick={uploadFile} className="upload-btn">
                    Upload
                  </button>
                  <button onClick={() => setFile(null)} className="cancel-btn">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
                    </svg>
                  </button>
                </div>
              </div>
            )}
            
            <div className="input-wrapper">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={userId ? "Message DataInsight..." : "Please upload a file first"}
                disabled={!userId || isLoading}
                className="message-input"
                rows="1"
              />
              <div className="input-actions">
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
                  className="action-btn attach-btn"
                  title="Upload Excel file"
                >
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M16.5,6V17.5A4,4 0 0,1 12.5,21.5A4,4 0 0,1 8.5,17.5V5A2.5,2.5 0 0,1 11,2.5A2.5,2.5 0 0,1 13.5,5V15.5A1,1 0 0,1 12.5,16.5A1,1 0 0,1 11.5,15.5V6H10V15.5A2.5,2.5 0 0,0 12.5,18A2.5,2.5 0 0,0 15,15.5V5A4,4 0 0,0 11,1A4,4 0 0,0 7,5V17.5A5.5,5.5 0 0,0 12.5,23A5.5,5.5 0 0,0 18,17.5V6H16.5Z" />
                  </svg>
                </button>
                <button 
                  onClick={sendQuery}
                  disabled={!input.trim() || !userId || isLoading}
                  className="action-btn send-btn"
                >
                  {isLoading ? (
                    <svg className="loading-spinner" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12,4V2A10,10 0 0,0 2,12H4A8,8 0 0,1 12,4Z" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path d="M2,21L23,12L2,3V10L17,12L2,14V21Z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sidebar Overlay for Mobile */}
      {sidebarOpen && (
        <div 
          className="sidebar-overlay"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile Results Toggle Button */}
      {(currentResults || currentCharts?.length > 0 || currentAiTable) && (
        <button 
          className="mobile-results-toggle"
          onClick={() => setMobileResultsOpen(true)}
          style={{ display: window.innerWidth <= 768 ? 'flex' : 'none' }}
          title="View Results"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M3,3H21V5H3V3M4,6H20V8H4V6M4,9H20V11H4V9M4,12H20V14H4V12M4,15H20V17H4V15M4,18H20V20H4V18Z" />
          </svg>
        </button>
      )}
    </div>
  );
}

export default App; 