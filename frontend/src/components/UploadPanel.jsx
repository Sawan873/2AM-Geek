import React, { useCallback, useEffect, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import axios from 'axios'

const ACCEPTED_TYPES = {
  'application/pdf': ['.pdf'],
  'text/plain': ['.txt'],
  'text/markdown': ['.md'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
}

function FileIcon({ filename }) {
  const ext = filename.split('.').pop().toLowerCase()
  const icons = {
    pdf: { icon: '📄', color: 'text-red-400 bg-red-400/10' },
    png: { icon: '🖼️', color: 'text-blue-400 bg-blue-400/10' },
    jpg: { icon: '🖼️', color: 'text-blue-400 bg-blue-400/10' },
    jpeg: { icon: '🖼️', color: 'text-blue-400 bg-blue-400/10' },
    md: { icon: '📝', color: 'text-green-400 bg-green-400/10' },
    txt: { icon: '📝', color: 'text-green-400 bg-green-400/10' },
  }
  const { icon, color } = icons[ext] || { icon: '📎', color: 'text-slate-400 bg-slate-400/10' }
  return (
    <span className={`w-7 h-7 flex items-center justify-center rounded-md text-sm ${color}`}>
      {icon}
    </span>
  )
}

export default function UploadPanel({ documents, setDocuments, onStartQuiz }) {
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState({}) // { filename: status }
  const [error, setError] = useState(null)

  const fetchDocuments = async () => {
    try {
      const res = await axios.get('/api/documents')
      setDocuments(res.data.documents || [])
    } catch (e) {
      console.error('Failed to fetch documents', e)
    }
  }

  useEffect(() => {
    fetchDocuments()
  }, [])

  const onDrop = useCallback(async (acceptedFiles) => {
    if (acceptedFiles.length === 0) return
    setError(null)
    setUploading(true)

    for (const file of acceptedFiles) {
      setUploadProgress(prev => ({ ...prev, [file.name]: 'uploading' }))
      const formData = new FormData()
      formData.append('file', file)
      try {
        const res = await axios.post('/api/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        setUploadProgress(prev => ({ ...prev, [file.name]: `done:${res.data.chunks_stored}` }))
      } catch (e) {
        const msg = e.response?.data?.detail || e.message
        setUploadProgress(prev => ({ ...prev, [file.name]: `error:${msg}` }))
        setError(`Failed to upload ${file.name}: ${msg}`)
      }
    }

    setUploading(false)
    // Refresh list
    await fetchDocuments()
    // Clear progress after 4s
    setTimeout(() => setUploadProgress({}), 4000)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    multiple: true,
  })

  const handleDelete = async (filename) => {
    try {
      await axios.delete(`/api/documents/${encodeURIComponent(filename)}`)
      await fetchDocuments()
    } catch (e) {
      setError(`Failed to delete ${filename}`)
    }
  }

  return (
    <div className="flex flex-col h-full p-4 gap-4 overflow-hidden">
      {/* Section header */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">
          Study Materials
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">Upload PDFs, images, or notes</p>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all duration-200
          ${isDragActive
            ? 'border-accent-blue bg-accent-blue/10 scale-[1.01]'
            : 'border-dark-border hover:border-slate-500 hover:bg-dark-card/50'
          }
        `}
      >
        <input {...getInputProps()} />
        <div className="text-3xl mb-2">{isDragActive ? '📂' : '☁️'}</div>
        {isDragActive ? (
          <p className="text-sm text-accent-blue font-medium">Drop files here…</p>
        ) : (
          <>
            <p className="text-sm text-slate-300 font-medium">Drag & drop files here</p>
            <p className="text-xs text-slate-500 mt-1">or click to browse</p>
            <p className="text-xs text-slate-600 mt-2">PDF · PNG · JPG · MD · TXT</p>
          </>
        )}
      </div>

      {/* Upload progress toasts */}
      {Object.keys(uploadProgress).length > 0 && (
        <div className="flex flex-col gap-1.5">
          {Object.entries(uploadProgress).map(([fname, status]) => {
            const isDone = status.startsWith('done')
            const isErr = status.startsWith('error')
            const chunks = isDone ? status.split(':')[1] : null
            return (
              <div
                key={fname}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs
                  ${isDone ? 'bg-accent-green/10 border border-accent-green/30 text-accent-green'
                    : isErr ? 'bg-red-500/10 border border-red-500/30 text-red-400'
                    : 'bg-accent-blue/10 border border-accent-blue/30 text-accent-blue'}`}
              >
                {isDone ? '✅' : isErr ? '❌' : (
                  <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                )}
                <span className="truncate flex-1">{fname}</span>
                {isDone && <span className="shrink-0">{chunks} chunks</span>}
              </div>
            )
          })}
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-xs px-3 py-2 rounded-lg">
          {error}
        </div>
      )}

      {/* Document list */}
      <div className="flex-1 overflow-y-auto">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-500">
            {documents.length} document{documents.length !== 1 ? 's' : ''} ingested
          </span>
          {documents.length > 0 && (
            <button
              onClick={fetchDocuments}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
              title="Refresh list"
            >
              ↻ Refresh
            </button>
          )}
        </div>

        {documents.length === 0 ? (
          <div className="text-center py-8 text-slate-600 text-sm">
            <p>No documents yet.</p>
            <p className="text-xs mt-1">Upload something to get started.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {documents.map((doc) => (
              <div
                key={doc.filename}
                className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-dark-card border border-dark-border hover:border-slate-600 transition-all group"
              >
                <FileIcon filename={doc.filename} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-200 truncate" title={doc.filename}>
                    {doc.filename}
                  </p>
                  <p className="text-xs text-slate-500">{doc.chunks} chunks</p>
                </div>
                <button
                  onClick={() => onStartQuiz?.(doc)}
                  className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-accent-blue hover:bg-accent-blue/10 bg-dark-bg border border-dark-border transition-all text-[10px] px-2 py-1 rounded-md"
                  title="Generate Quiz"
                >
                  📝 Quiz
                </button>
                <button
                  onClick={() => handleDelete(doc.filename)}
                  className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 transition-all text-xs px-1.5 py-1 rounded"
                  title="Remove document"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
