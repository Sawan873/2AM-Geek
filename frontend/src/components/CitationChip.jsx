import React from 'react'

/**
 * CitationChip — a small badge showing "📄 filename — Page N"
 */
export default function CitationChip({ filename, page_number, source_type, onClick }) {
  const ext = filename.split('.').pop().toLowerCase()
  const isImage = source_type === 'image' || ['png', 'jpg', 'jpeg'].includes(ext)
  const isPdf = source_type === 'pdf' || ext === 'pdf'

  const icon = isImage ? '🖼️' : isPdf ? '📄' : '📝'

  // Colour coding by source type
  const colorClass = isImage
    ? 'bg-blue-500/15 border-blue-500/30 text-blue-300 hover:bg-blue-500/25'
    : isPdf
    ? 'bg-purple-500/15 border-purple-500/30 text-purple-300 hover:bg-purple-500/25'
    : 'bg-green-500/15 border-green-500/30 text-green-300 hover:bg-green-500/25'

  // Truncate very long filenames
  const displayName = filename.length > 30 ? filename.slice(0, 28) + '…' : filename

  return (
    <span
      onClick={() => onClick?.({ filename, page_number, source_type })}
      className={`
        inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium 
        transition-colors duration-150 select-none ${onClick ? 'cursor-pointer' : 'cursor-default'} ${colorClass}
      `}
      title={`${filename} — Page ${page_number}`}
    >
      <span>{icon}</span>
      <span className="font-mono">{displayName}</span>
      <span className="opacity-60">·</span>
      <span>p.{page_number}</span>
    </span>
  )
}
