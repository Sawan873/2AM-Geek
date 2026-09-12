import React, { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import MessageBubble from './MessageBubble'

const WELCOME_MESSAGE = {
  role: 'assistant',
  content:
    "Hey. It's 2AM and your exam is in a few hours — I get it.\n\n" +
    "Upload your lecture PDFs, slides, photos of handwritten notes, or any text files using the left panel. " +
    "Then ask me anything. I'll answer **strictly from your materials** and show you exactly which page the answer is on.\n\n" +
    "I remember what we've talked about, so follow-up questions work. Ask me to explain something further, " +
    "compare concepts, or just say *'what else does the material say about this?'*",
  citations: [],
  timestamp: new Date().toISOString(),
}

export default function ChatPanel({ hasDocuments, onCitationClick, debugMode, onSaveRevision }) {
  const [messages, setMessages] = useState([WELCOME_MESSAGE])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [loadingPhase, setLoadingPhase] = useState(0)
  const [error, setError] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  useEffect(() => {
    let interval;
    if (isLoading) {
      setLoadingPhase(1);
      const startTime = Date.now();
      interval = setInterval(() => {
        const elapsed = Date.now() - startTime;
        if (elapsed > 4000) {
          setLoadingPhase(3);
        } else if (elapsed > 2000) {
          setLoadingPhase(2);
        }
      }, 500);
    } else {
      setLoadingPhase(0);
    }
    return () => clearInterval(interval);
  }, [isLoading]);

  // Build conversation history for the API (exclude the welcome message)
  const buildHistory = () => {
    return messages
      .filter(m => m !== WELCOME_MESSAGE)
      .map(m => ({ role: m.role === 'assistant' ? 'assistant' : 'user', content: m.content }))
  }

  const sendMessage = async () => {
    const question = input.trim()
    if (!question || isLoading) return

    const userMsg = {
      role: 'user',
      content: question,
      timestamp: new Date().toISOString(),
    }

    const currentHistory = buildHistory()
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsLoading(true)
    setError(null)

    try {
      const res = await axios.post('/api/chat', {
        question,
        history: currentHistory,
      })
      const aiMsg = {
        role: 'assistant',
        content: res.data.answer,
        citations: res.data.citations || [],
        debug_info: res.data.debug_info,
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, aiMsg])
    } catch (e) {
      const detail = e.response?.data?.detail || e.message
      setError(`Error: ${detail}`)
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `⚠️ Something went wrong: ${detail}`,
          citations: [],
          timestamp: new Date().toISOString(),
        },
      ])
    } finally {
      setIsLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const clearChat = () => {
    setMessages([WELCOME_MESSAGE])
    setError(null)
  }

  // Suggested prompts for empty state
  const suggestions = [
    "What's the difference between the two main algorithms in my notes?",
    "Summarize the key points from my lecture slides",
    "Which page covers time complexity?",
    "Explain the concept mentioned on page 3 in more detail",
  ]
  
  const getLoadingText = () => {
    if (loadingPhase === 1) return "🔍 Searching course materials..."
    if (loadingPhase === 2) return "⚖️ Evaluating evidence..."
    if (loadingPhase === 3) return "✍️ Generating cited response..."
    return "..."
  }

  return (
    <div className="flex flex-col h-full">
      {/* Chat header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-dark-border shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">
            Chat
            <span className="ml-2 text-xs font-normal text-slate-500 bg-dark-card px-2 py-0.5 rounded-full normal-case tracking-normal">
              Multi-turn · {messages.length - 1} turn{messages.length !== 2 ? 's' : ''}
            </span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {hasDocuments
              ? 'Answers from your materials only · follow-ups remember context'
              : 'Upload documents first to enable Q&A'}
          </p>
        </div>
        <button
          onClick={clearChat}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors px-2 py-1 rounded border border-transparent hover:border-dark-border"
          title="Start a new session"
        >
          ↺ New session
        </button>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {messages.map((msg, i) => (
          <MessageBubble 
            key={i} 
            message={msg} 
            onCitationClick={onCitationClick}
            debugMode={debugMode}
            onSaveRevision={onSaveRevision}
          />
        ))}

        {isLoading && (
          <div className="flex items-end gap-2 mb-4">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center text-xs font-bold text-white shrink-0">
              AI
            </div>
            <div className="bg-dark-card border border-dark-border rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-slate-400 italic flex items-center gap-2">
              <span className="w-3 h-3 border-2 border-slate-500 border-t-slate-200 rounded-full animate-spin"></span>
              {getLoadingText()}
            </div>
          </div>
        )}

        {/* Suggestion chips when only welcome message is visible */}
        {messages.length === 1 && hasDocuments && !isLoading && (
          <div className="mt-4 mb-2">
            <p className="text-xs text-slate-600 mb-2 ml-9">Try asking:</p>
            <div className="flex flex-wrap gap-2 ml-9">
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  onClick={() => { setInput(s); inputRef.current?.focus() }}
                  className="text-xs bg-dark-card border border-dark-border text-slate-400 hover:text-slate-200 hover:border-slate-500 px-3 py-1.5 rounded-full transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* No-documents warning */}
      {!hasDocuments && (
        <div className="mx-5 mb-3 bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-2.5 text-xs text-amber-400 flex items-center gap-2">
          <span>⚠️</span>
          <span>No documents yet. Upload your notes or slides on the left — I'll answer from them and refuse anything they don't cover.</span>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="mx-5 mb-2 bg-red-500/10 border border-red-500/30 text-red-400 text-xs px-3 py-2 rounded-lg">
          {error}
        </div>
      )}

      {/* Input area */}
      <div className="shrink-0 px-5 pb-5 pt-3 border-t border-dark-border">
        <div className="flex gap-3 items-end">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={hasDocuments
                ? 'Ask anything about your notes… follow-up questions work too'
                : 'Upload your study materials to get started…'}
              disabled={isLoading}
              rows={1}
              className="
                w-full bg-dark-card border border-dark-border rounded-xl px-4 py-3 pr-12
                text-sm text-slate-200 placeholder-slate-600
                resize-none overflow-hidden
                focus:outline-none focus:border-accent-blue/60
                transition-colors duration-200
                disabled:opacity-50 disabled:cursor-not-allowed
              "
              style={{ minHeight: '46px', maxHeight: '160px' }}
              onInput={e => {
                e.target.style.height = 'auto'
                e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
              }}
            />
          </div>
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            className="
              shrink-0 w-11 h-11 flex items-center justify-center rounded-xl
              bg-accent-blue hover:bg-blue-500 text-white
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-all duration-200 active:scale-95
            "
            title="Send (Enter)"
          >
            {isLoading ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M22 2L11 13M22 2L15 22L11 13L2 9L22 2Z" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-xs text-slate-600 mt-2 text-center">
          Shift+Enter for new line · Enter to send · Answers cite exact pages
        </p>
      </div>
    </div>
  )
}
