import CitationChip from './CitationChip'

export default function RevisionBoard({ cards, onRemove, onCitationClick }) {
  return (
    <div className="flex flex-col h-full p-4 gap-4 overflow-y-auto">
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">
          Revision Board
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Keep the cited answers you want to revisit before the exam.
        </p>
      </div>

      {cards.length === 0 ? (
        <div className="rounded-xl border border-dashed border-dark-border p-5 text-center text-sm text-slate-500">
          Save a cited answer from chat to build your last-minute revision list.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {cards.map(card => (
            <article key={card.id} className="rounded-xl border border-dark-border bg-dark-card p-3">
              <div className="flex justify-between gap-2 mb-2">
                <span className="text-[10px] uppercase tracking-wide text-accent-purple">Saved answer</span>
                <button
                  onClick={() => onRemove(card.id)}
                  className="text-xs text-slate-500 hover:text-red-400"
                  title="Remove from revision board"
                >
                  Remove
                </button>
              </div>
              <p className="text-xs leading-relaxed text-slate-300 whitespace-pre-line">
                {card.content.length > 380 ? `${card.content.slice(0, 380)}…` : card.content}
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {card.citations.map((citation, index) => (
                  <CitationChip
                    key={`${citation.filename}-${citation.page_number}-${index}`}
                    {...citation}
                    onClick={onCitationClick}
                  />
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
      <p className="mt-auto text-[10px] text-slate-600">
        Saved locally in this browser. Up to 20 cards are kept.
      </p>
    </div>
  )
}
