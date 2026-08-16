import { useState, useRef, useEffect } from 'react'
import './index.css'

const API_BASE = 'http://localhost:8000/api'

const MAX_DOCUMENTS = 10

const EXAMPLE_QUESTIONS = [
  "What are the key components of the 5G Core Network architecture?",
  "How does the AMF handle registration procedures?",
  "What is network slicing and how is it implemented in 5GS?",
  "Describe the PDU session establishment procedure.",
  "What are the NAS security procedures in 5G?",
  "What is the role of the SMF in the 5G system?",
]

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function EvidenceIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" width="40" height="40">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
    </svg>
  )
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedSpecs, setSelectedSpecs] = useState([])
  const [activeEvidence, setActiveEvidence] = useState(null)
  const [evidenceTab, setEvidenceTab] = useState('evidence')
  const [corpusStatus, setCorpusStatus] = useState(null)
  const [health, setHealth] = useState(null)
  
  // Add Document state
  const [showAddModal, setShowAddModal] = useState(false)
  const [newSpec, setNewSpec] = useState('')
  const [uploadFile, setUploadFile] = useState(null)
  const [addingDoc, setAddingDoc] = useState(false)
  const [addError, setAddError] = useState(null)
  
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  const refreshCorpus = () => {
    fetch(`${API_BASE}/corpus/status`).then(r => r.json()).then(data => {
      setCorpusStatus(data)
    }).catch(() => {})
  }

  // Fetch health and corpus on mount
  useEffect(() => {
    fetch(`${API_BASE}/health`).then(r => r.json()).then(setHealth).catch(() => {})
    fetch(`${API_BASE}/corpus/status`).then(r => r.json()).then(data => {
      setCorpusStatus(data)
      // Automatically select all specifications from the backend state on startup
      setSelectedSpecs(data.specifications.map(s => s.specification))
    }).catch(() => {})
  }, [])

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px'
    }
  }, [input])

  const toggleSpec = (specId) => {
    setSelectedSpecs(prev =>
      prev.includes(specId) ? prev.filter(s => s !== specId) : [...prev, specId]
    )
  }

  const sendQuery = async (queryText) => {
    const query = queryText || input.trim()
    if (!query || loading) return

    const userMsg = { role: 'user', content: query }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    setActiveEvidence(null)

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          release: '18',
          specifications: selectedSpecs,
        }),
      })

      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()

      const assistantMsg = {
        role: 'assistant',
        content: data.answer,
        evidence: data.evidence,
        latency: data.latency,
        llm_used: data.llm_used,
        knowledge_scope: data.knowledge_scope,
      }

      setMessages(prev => [...prev, assistantMsg])
      setActiveEvidence(data)
      setEvidenceTab('evidence')
    } catch (err) {
      const errorMsg = {
        role: 'assistant',
        content: `System error: ${err.message}. Please ensure the backend is running on port 8000.`,
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendQuery()
    }
  }

  const handleAddDocument = async () => {
    if (!newSpec || !uploadFile) {
      setAddError('Specification and file are required')
      return
    }
    setAddingDoc(true)
    setAddError(null)
    try {
      const formData = new FormData()
      formData.append('release', '18')
      formData.append('specification', newSpec)
      formData.append('file', uploadFile)

      const res = await fetch(`${API_BASE}/corpus/upload`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to add document')
      
      // Refresh corpus
      refreshCorpus()
      
      // Auto-select the newly added spec
      setSelectedSpecs(prev => {
        if (!prev.includes(newSpec)) return [...prev, newSpec]
        return prev
      })
      
      setShowAddModal(false)
      setNewSpec('')
      setUploadFile(null)
    } catch (err) {
      setAddError(err.message)
    } finally {
      setAddingDoc(false)
    }
  }

  const handleRemoveDocument = async (specification) => {
    // V1 Requirement: Do NOT physically delete the indexed document. 
    // "Remove" simply removes it from the user's active document scope (unchecks it).
    setSelectedSpecs(prev => prev.filter(s => s !== specification))
  }

  const totalDocs = corpusStatus?.total_documents || 0
  const atCapacity = totalDocs >= MAX_DOCUMENTS

  return (
    <div className="app-layout">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-brand">
          <img src="/mavenir_logo.png" alt="Mavenir" />
          <div className="header-title">
            <h1>TeleRAG</h1>
            <span>3GPP Standards Intelligence</span>
          </div>
        </div>
        <div className="header-status">
          <div className="status-badge">
            <span className={`status-dot ${health?.status === 'ok' ? 'ok' : 'loading'}`} />
            {health?.status === 'ok' ? 'System Online' : 'Connecting...'}
          </div>
          {health?.index_ready && (
            <div className="status-badge">
              <span className="status-dot ok" />
              {health.corpus_chunks?.toLocaleString()} chunks indexed
            </div>
          )}
          {health?.llm_available && health.llm_available !== 'missing_key' && (
            <div className="status-badge">
              <span className="status-dot ok" />
              LLM Ready
            </div>
          )}
        </div>
      </header>

      {/* ── Sidebar ── */}
      <aside className="sidebar">
        <div className="sidebar-section">
          <div className="sidebar-section-title">Knowledge Scope</div>
          <div className="status-badge" style={{ marginBottom: 10, width: 'fit-content' }}>
            Release {corpusStatus ? corpusStatus.release : '18'}
          </div>
          <div className="spec-list">
            {(corpusStatus?.specifications || []).map(spec => (
              <div className="spec-item" key={spec.specification}>
                <input
                  type="checkbox"
                  checked={selectedSpecs.includes(spec.specification)}
                  onChange={() => toggleSpec(spec.specification)}
                  id={`spec-${spec.specification}`}
                />
                <div className="spec-item-info" onClick={() => toggleSpec(spec.specification)}>
                  <label htmlFor={`spec-${spec.specification}`}>{spec.specification}</label>
                  <span className="spec-title">{spec.title || `v${spec.version}`}</span>
                </div>
                <button
                  className="spec-remove-btn"
                  title={`Remove ${spec.specification} from corpus`}
                  onClick={(e) => { e.stopPropagation(); handleRemoveDocument(spec.specification) }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
          
          <div className="doc-counter">{totalDocs} / {MAX_DOCUMENTS} documents</div>
          
          {atCapacity ? (
            <div className="doc-limit-msg">Maximum {MAX_DOCUMENTS} documents reached.</div>
          ) : (
            <button className="add-doc-btn" onClick={() => setShowAddModal(true)}>
              + Add 3GPP Document
            </button>
          )}
        </div>

        {corpusStatus && (
          <div className="sidebar-section">
            <div className="sidebar-section-title">Corpus Status</div>
            <div className="corpus-stats">
              <div className="stat-card">
                <div className="stat-value">{corpusStatus.total_documents}</div>
                <div className="stat-label">Documents</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{corpusStatus.total_chunks?.toLocaleString()}</div>
                <div className="stat-label">Chunks</div>
              </div>
            </div>
          </div>
        )}

        <div className="sidebar-section">
          <div className="sidebar-section-title">Try asking</div>
          <div className="example-questions">
            {EXAMPLE_QUESTIONS.map((q, i) => (
              <button className="example-question" key={i} onClick={() => sendQuery(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      </aside>

      {/* ── Chat Area ── */}
      <main className="chat-area">
        <div className="chat-messages">
          {messages.length === 0 && !loading && (
            <div className="chat-welcome">
              <img src="/mavenir_logo.png" alt="" />
              <h2>TeleRAG Intelligence Assistant</h2>
              <p>Ask technical questions about 3GPP Release 18 specifications. Answers are generated using retrieved evidence from official standards.</p>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div className={`message ${msg.role}`} key={idx}>
              <div className="message-avatar">
                {msg.role === 'user' ? 'U' : 'T'}
              </div>
              <div className="message-content">
                {msg.content.split('\n').map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
                {msg.llm_used && (
                  <div className="message-meta">
                    <span>LLM: {msg.llm_used}</span>
                    {msg.knowledge_scope && <span> · {msg.knowledge_scope}</span>}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="message assistant">
              <div className="message-avatar">T</div>
              <div className="message-content">
                <div className="loading-dots">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <div className="chat-input-wrapper">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about 3GPP Release 18 standards..."
              rows={1}
              disabled={loading}
            />
            <button className="send-button" onClick={() => sendQuery()} disabled={!input.trim() || loading}>
              <SendIcon />
            </button>
          </div>
        </div>
      </main>

      {/* ── Evidence Panel ── */}
      <aside className="evidence-panel">
        <div className="evidence-panel-header">
          <h3>Evidence & Debug</h3>
        </div>
        <div className="evidence-tabs">
          <button className={`evidence-tab ${evidenceTab === 'evidence' ? 'active' : ''}`} onClick={() => setEvidenceTab('evidence')}>
            Evidence
          </button>
          <button className={`evidence-tab ${evidenceTab === 'latency' ? 'active' : ''}`} onClick={() => setEvidenceTab('latency')}>
            Latency
          </button>
        </div>

        <div className="evidence-content">
          {!activeEvidence ? (
            <div className="empty-state">
              <EvidenceIcon />
              <p>Submit a query to see retrieved evidence chunks and pipeline latency.</p>
            </div>
          ) : (
            <>
              {evidenceTab === 'evidence' && (
                activeEvidence.evidence?.length > 0 ? (
                  activeEvidence.evidence.map((chunk, i) => (
                    <div className="evidence-chunk" key={i}>
                      <div className="evidence-chunk-header">
                        <span className="evidence-chunk-spec">{chunk.specification}</span>
                        <span className="evidence-chunk-score">
                          {chunk.rerank_score != null ? `rerank: ${chunk.rerank_score.toFixed(3)}` : chunk.rrf_score != null ? `rrf: ${chunk.rrf_score.toFixed(4)}` : ''}
                        </span>
                      </div>
                      <div className="evidence-chunk-meta">
                        <span>v{chunk.version}</span>
                        <span>·</span>
                        <span>Pg {chunk.page}</span>
                        {chunk.section && <><span>·</span><span>§{chunk.section}</span></>}
                      </div>
                      <div className="evidence-chunk-text">{chunk.text}</div>
                    </div>
                  ))
                ) : (
                  <div className="empty-state"><p>No evidence retrieved.</p></div>
                )
              )}

              {evidenceTab === 'latency' && activeEvidence.latency && (
                <div className="latency-grid">
                  {[
                    ['Dense', activeEvidence.latency.dense_retrieval_ms],
                    ['BM25', activeEvidence.latency.bm25_retrieval_ms],
                    ['RRF', activeEvidence.latency.rrf_fusion_ms],
                    ['Rerank', activeEvidence.latency.reranking_ms],
                    ['LLM', activeEvidence.latency.llm_generation_ms],
                    ['Total', activeEvidence.latency.total_ms],
                  ].map(([label, value]) => value != null && (
                    <div className="latency-item" key={label}>
                      <span className="latency-label">{label}</span>
                      <span className="latency-value">{value.toFixed(0)}ms</span>
                    </div>
                  ))}
                  {activeEvidence.llm_used && (
                    <div className="latency-item">
                      <span className="latency-label">LLM</span>
                      <span className="latency-value">{activeEvidence.llm_used}</span>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </aside>

      {/* ── Add Document Modal ── */}
      {showAddModal && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <h3>Add 3GPP Document</h3>
            
            <div className="modal-body">
              <div className="form-group">
                <label>Release</label>
                <select disabled defaultValue="18" className="form-select">
                  <option value="18">Release 18</option>
                </select>
              </div>
              <div className="form-group">
                <label>Specification (e.g. TS 29.500)</label>
                <input 
                  type="text" 
                  placeholder="TS XX.YYY" 
                  className="form-input" 
                  value={newSpec}
                  onChange={e => setNewSpec(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label>Document (.zip, .pdf, .docx)</label>
                <input 
                  type="file" 
                  accept=".zip,.pdf,.docx" 
                  className="form-input" 
                  onChange={e => setUploadFile(e.target.files[0])}
                />
              </div>
              {addError && <div className="modal-error">{addError}</div>}
              {addingDoc && <div className="modal-loading">Extracting, and indexing document... This may take a minute.</div>}
            </div>

            <div className="modal-footer">
              <button className="btn-cancel" onClick={() => { setShowAddModal(false); setAddError(null); setNewSpec(''); setUploadFile(null) }} disabled={addingDoc}>Cancel</button>
              <button className="btn-primary" onClick={handleAddDocument} disabled={addingDoc || !newSpec.trim() || !uploadFile}>
                {addingDoc ? 'Adding...' : 'Add Document'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
