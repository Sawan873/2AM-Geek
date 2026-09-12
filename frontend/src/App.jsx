import React, { useState, useEffect } from 'react'
import UploadPanel from './components/UploadPanel'
import ChatPanel from './components/ChatPanel'
import DashboardPanel from './components/DashboardPanel'
import EvidenceViewer from './components/EvidenceViewer'
import ExamMode from './components/ExamMode'
import RevisionBoard from './components/RevisionBoard'

export default function App() {
  const [documents, setDocuments] = useState([])
  const [selectedCitation, setSelectedCitation] = useState(null)
  const [debugMode, setDebugMode] = useState(false)
  const [sidebarTab, setSidebarTab] = useState('materials')
  const [examDoc, setExamDoc] = useState(null)
  const [revisionCards, setRevisionCards] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('2am-geek-revision-cards') || '[]')
    } catch {
      return []
    }
  })

  useEffect(() => {
    localStorage.setItem('2am-geek-revision-cards', JSON.stringify(revisionCards))
  }, [revisionCards])

  const saveRevisionCard = (message) => {
    setRevisionCards(previous => {
      if (previous.some(card => card.content === message.content)) return previous
      return [{
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        content: message.content,
        citations: message.citations || [],
        savedAt: new Date().toISOString(),
      }, ...previous].slice(0, 20)
    })
  }

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'd') {
        e.preventDefault()
        setDebugMode(prev => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className="flex h-screen bg-dark-bg overflow-hidden">
      {/* ── Header Bar ── */}
      <div className="fixed top-0 left-0 right-0 z-10 flex items-center justify-between px-6 py-3 bg-dark-panel border-b border-dark-border">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center text-white font-bold text-sm">
            2A
          </div>
          <span className="font-semibold text-slate-100 tracking-tight">
            2AM Geek
            <span className="ml-2 text-xs font-normal text-slate-400 bg-dark-card px-2 py-0.5 rounded-full">
              RAG Study Tool
            </span>
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className="w-2 h-2 rounded-full bg-accent-green animate-pulse inline-block" />
          Powered by Gemini
        </div>
      </div>

      {/* ── Main Layout ── */}
      <div className="flex w-full pt-14 h-full">
        {/* Left panel — 280px */}
        <div className="w-[280px] shrink-0 border-r border-dark-border flex flex-col bg-dark-panel">
          <div className="flex p-2 border-b border-dark-border gap-1 shrink-0">
            <button
              onClick={() => setSidebarTab('materials')}
              className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors ${
                sidebarTab === 'materials' 
                  ? 'bg-dark-card text-slate-200 shadow-sm' 
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              Materials
            </button>
            <button
              onClick={() => setSidebarTab('dashboard')}
              className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors ${
                sidebarTab === 'dashboard' 
                  ? 'bg-dark-card text-slate-200 shadow-sm' 
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => setSidebarTab('revision')}
              className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors ${
                sidebarTab === 'revision'
                  ? 'bg-dark-card text-slate-200 shadow-sm'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              Revision
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            {sidebarTab === 'materials' ? (
              <UploadPanel documents={documents} setDocuments={setDocuments} onStartQuiz={setExamDoc} />
            ) : sidebarTab === 'dashboard' ? (
              <DashboardPanel />
            ) : (
              <RevisionBoard
                cards={revisionCards}
                onRemove={(id) => setRevisionCards(previous => previous.filter(card => card.id !== id))}
                onCitationClick={setSelectedCitation}
              />
            )}
          </div>
        </div>

        {/* Center panel */}
        <div className="flex-1 flex flex-col min-w-0">
          <ChatPanel 
            hasDocuments={documents.length > 0} 
            onCitationClick={setSelectedCitation}
            debugMode={debugMode}
            onSaveRevision={saveRevisionCard}
          />
        </div>

        {/* Right panel */}
        {selectedCitation && (
          <div className="w-[380px] shrink-0">
            <EvidenceViewer 
              citation={selectedCitation} 
              onClose={() => setSelectedCitation(null)} 
            />
          </div>
        )}
      </div>

      {examDoc && (
        <ExamMode document={examDoc} onClose={() => setExamDoc(null)} />
      )}
    </div>
  )
}
