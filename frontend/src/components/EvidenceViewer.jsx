import React, { useState } from 'react'

export default function EvidenceViewer({ citation, onClose }) {
  const [imageError, setImageError] = useState(false)

  if (!citation) return null

  const { filename, page_number, source_type } = citation

  const ext = filename.split('.').pop().toLowerCase()
  const isImageSource = ['png', 'jpg', 'jpeg'].includes(ext) || source_type === 'image'
  const isPdf = ext === 'pdf' || source_type === 'pdf'

  const imageUrl = isImageSource 
    ? `/api/images/${filename}` 
    : `/api/images/${filename}_page_${page_number}.png`

  return (
    <div className="flex flex-col h-full bg-dark-panel border-l border-dark-border">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border">
        <div>
          <h3 className="text-sm font-semibold text-slate-200 truncate" title={filename}>
            {filename}
          </h3>
          <p className="text-xs text-slate-500">
            Page {page_number}
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white transition-colors"
          title="Close Evidence Viewer"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 bg-dark-bg flex flex-col items-center">
        {isImageSource && (
          <div className="mb-4 bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs px-3 py-2 rounded-lg w-full text-center">
            OCR-extracted text — verify against original image above.
          </div>
        )}
        
        <div className="w-full bg-dark-card border border-dark-border rounded-lg overflow-hidden shadow-lg relative min-h-[200px] flex items-center justify-center">
          {!imageError ? (
            <img 
              src={imageUrl} 
              alt={`Evidence from ${filename} page ${page_number}`}
              className="w-full h-auto object-contain"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="text-slate-500 text-sm py-12 flex flex-col items-center gap-2">
              <span className="text-2xl">📄</span>
              Page image not available
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
