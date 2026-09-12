import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import CitationChip from './CitationChip'

export default function MessageBubble({ message, onCitationClick, debugMode, onSaveRevision }) {
  const [debugExpanded, setDebugExpanded] = useState(false)
  const isUser = message.role === 'user'
  
  // Refusal can be detected by text or evidence decision
  const isRefusal = 
    message.content?.trim() === 'I cannot answer this based on the provided materials.' ||
    message.debug_info?.evidence_decision === 'NO_CANDIDATES'

  const { debug_info } = message

  return (
    <div className={`flex items-end gap-2 mb-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar */}
      <div
        className={`
          w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0
          ${isUser
            ? 'bg-accent-yellow/20 text-accent-yellow border border-accent-yellow/30'
            : 'bg-gradient-to-br from-accent-blue to-accent-purple text-white'}
        `}
      >
        {isUser ? '👤' : 'AI'}
      </div>

      {/* Bubble */}
      <div className={`flex flex-col gap-2 max-w-[85%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`
            px-4 py-3 rounded-2xl text-sm leading-relaxed
            ${isUser
              ? 'bg-accent-blue text-white rounded-br-sm'
              : 'bg-dark-card border border-dark-border text-slate-200 rounded-bl-sm'}
          `}
        >
          {isRefusal ? (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 text-amber-400 font-semibold mb-1">
                <span>📚</span> Insufficient Evidence
              </div>
              <p className="text-slate-300">
                I couldn't find enough evidence in your course materials to answer this reliably.
              </p>
              
              {debug_info?.searched_documents?.length > 0 && (
                <div className="bg-dark-bg p-3 rounded-lg border border-dark-border">
                  <p className="text-xs text-slate-400 mb-1">📂 Searched:</p>
                  <ul className="list-disc list-inside text-xs text-slate-300">
                    {debug_info.searched_documents.map((doc, idx) => (
                      <li key={idx} className="truncate">{doc}</li>
                    ))}
                  </ul>
                </div>
              )}
              
              <div className="text-xs text-slate-400 bg-accent-blue/10 border border-accent-blue/20 p-2 rounded-lg flex gap-2 items-start mt-1">
                <span>💡</span>
                <span>Try rephrasing your question or check if this topic is covered in your uploaded materials.</span>
              </div>
            </div>
          ) : (
            <>
              {message.debug_info?.fallback_used && (
                <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                  Model response timed out — showing source excerpts only, not an invented answer.
                </div>
              )}
              <ReactMarkdown
                components={{
                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                strong: ({ children }) => <strong className="font-semibold text-slate-100">{children}</strong>,
                em: ({ children }) => <em className="text-slate-300">{children}</em>,
                code: ({ children, className }) => {
                  const isBlock = className?.includes('language-')
                  return isBlock ? (
                    <pre className="bg-dark-bg rounded-lg p-3 mt-2 mb-2 overflow-x-auto">
                      <code className="font-mono text-xs text-slate-300">{children}</code>
                    </pre>
                  ) : (
                    <code className="font-mono text-xs bg-dark-bg px-1.5 py-0.5 rounded text-accent-blue">
                      {children}
                    </code>
                  )
                },
                ul: ({ children }) => <ul className="list-disc list-inside space-y-1 my-2">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 my-2">{children}</ol>,
                li: ({ children }) => <li className="text-slate-300">{children}</li>,
              }}
              >
                {message.content}
              </ReactMarkdown>
            </>
          )}
        </div>

        {/* Citations */}
        {!isUser && !isRefusal && message.citations && message.citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-0.5">
            <span className="text-xs text-slate-600 self-center mr-0.5">Sources:</span>
            {message.citations.map((c, i) => (
              <CitationChip 
                key={i} 
                filename={c.filename} 
                page_number={c.page_number} 
                source_type={c.source_type}
                onClick={onCitationClick}
              />
            ))}
          </div>
        )}

        {!isUser && !isRefusal && message.citations?.length > 0 && (
          <button
            onClick={() => onSaveRevision?.(message)}
            className="text-xs text-slate-500 hover:text-accent-blue transition-colors px-1"
            title="Save this cited answer for later revision"
          >
            ⊕ Save to revision board
          </button>
        )}

        {/* Debug Panel */}
        {debugMode && debug_info && !isUser && (
          <div className="mt-2 w-full max-w-lg bg-dark-bg border border-dark-border rounded-lg overflow-hidden">
            <button 
              onClick={() => setDebugExpanded(!debugExpanded)}
              className="w-full px-3 py-2 text-left text-xs font-mono text-slate-400 bg-dark-panel flex justify-between items-center hover:bg-dark-card transition-colors"
            >
              <span>🛠️ Debug Info</span>
              <span>{debugExpanded ? '▼' : '▶'}</span>
            </button>
            {debugExpanded && (
              <div className="p-3 text-xs space-y-3 font-mono text-slate-300">
                <div>
                  <span className="text-slate-500">Decision: </span>
                  <span className={`px-1.5 py-0.5 rounded font-bold ${
                    debug_info.evidence_decision === 'SUPPORTED' ? 'bg-accent-green/20 text-accent-green' :
                    debug_info.evidence_decision === 'PARTIALLY_SUPPORTED' ? 'bg-accent-yellow/20 text-accent-yellow' :
                    'bg-red-500/20 text-red-400'
                  }`}>
                    {debug_info.evidence_decision}
                  </span>
                </div>
                
                <div>
                  <div className="text-slate-500 mb-1">Fast local search queries:</div>
                  <ul className="list-disc list-inside pl-2 space-y-1">
                    {debug_info.expanded_queries?.map((q, i) => (
                      <li key={i} className="text-slate-400">{q}</li>
                    ))}
                  </ul>
                </div>

                <div className="flex flex-wrap gap-2 text-[10px] text-slate-500">
                  <span>Latency: {debug_info.latency_ms ?? '…'} ms</span>
                  <span>{debug_info.cache_hit ? 'Cache hit' : 'Fresh answer'}</span>
                </div>

                <div>
                  <div className="text-slate-500 mb-1">
                    Candidates ({debug_info.retrieved_candidates_count}):
                  </div>
                  <div className="space-y-2">
                    {debug_info.retrieved_candidates?.slice(0, 3).map((c, i) => (
                      <div key={i} className="bg-dark-panel p-2 rounded border border-dark-border">
                        <div className="flex justify-between mb-1">
                          <span className="text-accent-blue truncate">{c.source} p.{c.page}</span>
                          <span className="text-slate-500">Score: {c.score?.toFixed(3)}</span>
                        </div>
                        <div className="text-slate-400 text-[10px] truncate">{c.preview}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Timestamp */}
        {message.timestamp && (
          <span className="text-xs text-slate-600 px-1 mt-1">
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>
    </div>
  )
}
