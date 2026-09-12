import React, { useEffect, useState } from 'react'
import axios from 'axios'

export default function DashboardPanel() {
  const [stats, setStats] = useState({
    total_documents: 0,
    total_chunks: 0,
    total_questions_asked: 0,
    recent_topics: []
  })
  const [loading, setLoading] = useState(true)
  const [readiness, setReadiness] = useState(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [statsResponse, readinessResponse] = await Promise.all([
          axios.get('/api/stats'),
          axios.get('/api/readiness'),
        ])
        setStats(statsResponse.data)
        setReadiness(readinessResponse.data)
      } catch (e) {
        console.error('Failed to fetch stats', e)
      } finally {
        setLoading(false)
      }
    }
    fetchStats()
  }, [])

  if (loading) {
    return <div className="p-4 text-slate-500 text-sm">Loading stats...</div>
  }

  return (
    <div className="flex flex-col h-full p-4 gap-4 overflow-y-auto">
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">
          Dashboard
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">Overview of your study materials</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-dark-card/50 backdrop-blur-sm border border-dark-border rounded-xl p-4 shadow-sm">
          <p className="text-xs text-slate-500 mb-1">Documents</p>
          <p className="text-2xl font-bold text-accent-blue">{stats.total_documents}</p>
        </div>
        <div className="bg-dark-card/50 backdrop-blur-sm border border-dark-border rounded-xl p-4 shadow-sm">
          <p className="text-xs text-slate-500 mb-1">Chunks</p>
          <p className="text-2xl font-bold text-accent-purple">{stats.total_chunks}</p>
        </div>
        <div className="bg-dark-card/50 backdrop-blur-sm border border-dark-border rounded-xl p-4 shadow-sm col-span-2 flex justify-between items-center">
          <p className="text-xs text-slate-500">Questions Asked</p>
          <p className="text-xl font-bold text-accent-green">{stats.total_questions_asked}</p>
        </div>
      </div>

      {readiness && (
        <div className="mt-1">
          <div className="flex items-end justify-between mb-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-300">Submission Readiness</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                {readiness.ingested_pages} source pages · {readiness.formats.length} formats
              </p>
            </div>
          </div>
          <div className="space-y-2">
            {readiness.checks.map((check, index) => (
              <div key={index} className={`rounded-lg border px-3 py-2 text-xs ${
                check.passed
                  ? 'border-accent-green/30 bg-accent-green/10 text-slate-200'
                  : 'border-dark-border bg-dark-card text-slate-400'
              }`}>
                <div className="flex gap-2 items-start">
                  <span>{check.passed ? '✓' : '○'}</span>
                  <div>
                    <p className="font-medium text-slate-300">{check.label}</p>
                    <p className="mt-0.5 text-slate-500">{check.detail}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Recent Topics</h3>
        {stats.recent_topics && stats.recent_topics.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {stats.recent_topics.map((topic, i) => (
              <li key={i} className="text-xs text-slate-400 bg-dark-card border border-dark-border rounded-lg px-3 py-2 truncate">
                {topic}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-500 italic">No questions asked yet.</p>
        )}
      </div>
    </div>
  )
}
