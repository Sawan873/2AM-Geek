import React, { useEffect, useState } from 'react'
import axios from 'axios'
import CitationChip from './CitationChip'

export default function ExamMode({ document, onClose }) {
  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  
  // State for user answers: { [questionIndex]: selectedOptionLabel }
  const [answers, setAnswers] = useState({})
  const [submitted, setSubmitted] = useState(false)
  const [score, setScore] = useState(0)

  useEffect(() => {
    const fetchQuiz = async () => {
      try {
        const res = await axios.post('/api/quiz', {
          filename: document.filename,
          num_questions: 5
        })
        setQuestions(res.data.questions || [])
      } catch (e) {
        setError(e.response?.data?.detail || e.message)
      } finally {
        setLoading(false)
      }
    }
    fetchQuiz()
  }, [document.filename])

  const handleSelectOption = (qIndex, label) => {
    if (submitted) return
    setAnswers(prev => ({ ...prev, [qIndex]: label }))
  }

  const handleSubmit = () => {
    let currentScore = 0
    questions.forEach((q, i) => {
      if (answers[i] === q.correct_answer) {
        currentScore += 1
      }
    })
    setScore(currentScore)
    setSubmitted(true)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-dark-bg/80 backdrop-blur-sm p-6">
      <div className="bg-dark-panel border border-dark-border w-full max-w-3xl h-full max-h-[85vh] rounded-2xl flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-dark-border bg-dark-card shrink-0">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <span>📝</span> Quiz Mode
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Document: {document.filename}
            </p>
          </div>
          <button 
            onClick={onClose}
            className="text-slate-400 hover:text-white bg-dark-bg px-3 py-1.5 rounded-lg border border-dark-border transition-colors"
          >
            Close
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-4">
              <span className="w-8 h-8 border-4 border-accent-blue/30 border-t-accent-blue rounded-full animate-spin" />
              Generating quiz from {document.filename}...
            </div>
          ) : error ? (
            <div className="text-red-400 bg-red-500/10 p-4 rounded-lg border border-red-500/30">
              Failed to generate quiz: {error}
            </div>
          ) : (
            <div className="space-y-8 pb-8">
              {questions.map((q, i) => {
                const isCorrect = answers[i] === q.correct_answer
                
                return (
                  <div key={i} className="bg-dark-card border border-dark-border rounded-xl p-5">
                    <h3 className="text-sm font-semibold text-slate-200 mb-4">
                      <span className="text-accent-blue mr-2">Q{i + 1}.</span>
                      {q.question}
                    </h3>
                    
                    <div className="flex flex-col gap-2">
                      {q.options.map((opt) => {
                        const isSelected = answers[i] === opt.label
                        const isOptionCorrect = opt.label === q.correct_answer
                        
                        let optionClass = "border-dark-border bg-dark-bg hover:border-slate-500"
                        if (isSelected) optionClass = "border-accent-blue bg-accent-blue/10"
                        if (submitted) {
                          if (isOptionCorrect) optionClass = "border-accent-green bg-accent-green/10 text-accent-green"
                          else if (isSelected && !isOptionCorrect) optionClass = "border-red-500 bg-red-500/10 text-red-400"
                          else optionClass = "border-dark-border bg-dark-bg opacity-50"
                        }

                        return (
                          <button
                            key={opt.label}
                            onClick={() => handleSelectOption(i, opt.label)}
                            disabled={submitted}
                            className={`flex items-start gap-3 p-3 rounded-lg border text-left transition-all ${optionClass}`}
                          >
                            <span className="font-mono font-bold shrink-0">{opt.label}.</span>
                            <span className="text-sm">{opt.text}</span>
                          </button>
                        )
                      })}
                    </div>

                    {submitted && (
                      <div className={`mt-4 p-4 rounded-lg border ${isCorrect ? 'bg-accent-green/10 border-accent-green/30' : 'bg-red-500/10 border-red-500/30'}`}>
                        <div className="flex items-center gap-2 mb-2 font-semibold">
                          {isCorrect ? <span className="text-accent-green">✅ Correct!</span> : <span className="text-red-400">❌ Incorrect. The correct answer was {q.correct_answer}.</span>}
                        </div>
                        <p className="text-sm text-slate-300 mb-3">{q.explanation}</p>
                        {q.citation && (
                          <div className="flex items-center gap-2 text-xs">
                            <span className="text-slate-500">Source:</span>
                            <CitationChip filename={q.citation.filename} page_number={q.citation.page_number} />
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        {!loading && !error && (
          <div className="border-t border-dark-border bg-dark-panel p-4 flex justify-between items-center shrink-0">
            {submitted ? (
              <div className="text-lg font-bold">
                You scored <span className={score === questions.length ? 'text-accent-green' : 'text-accent-blue'}>{score}/{questions.length}</span>
              </div>
            ) : (
              <div className="text-xs text-slate-500">Answer all questions to see results</div>
            )}
            
            <button
              onClick={submitted ? onClose : handleSubmit}
              disabled={!submitted && Object.keys(answers).length !== questions.length}
              className="px-6 py-2 rounded-lg bg-accent-blue hover:bg-blue-500 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitted ? 'Finish' : 'Submit Answers'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
