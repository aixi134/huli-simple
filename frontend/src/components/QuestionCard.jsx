import { useRef } from 'react'
import AnswerResult from './AnswerResult'

export default function QuestionCard({
  question,
  selectedAnswer,
  disabled,
  onSelect,
  onSwipePrevious,
  onSwipeNext,
  canSwipePrevious = false,
  canSwipeNext = false,
  sourceLabel,
  submitting = false,
  result = null,
  aiExplanation = '',
  loadingAI = false,
  onRequestAIExplanation,
}) {
  const touchStartRef = useRef(null)

  function handleTouchStart(event) {
    const touch = event.touches[0]
    if (!touch) {
      return
    }
    touchStartRef.current = {
      x: touch.clientX,
      y: touch.clientY,
    }
  }

  function handleTouchEnd(event) {
    const start = touchStartRef.current
    touchStartRef.current = null
    const touch = event.changedTouches[0]
    if (!start || !touch) {
      return
    }
    const deltaX = touch.clientX - start.x
    const deltaY = touch.clientY - start.y
    if (Math.abs(deltaX) < 60 || Math.abs(deltaX) < Math.abs(deltaY)) {
      return
    }
    if (deltaX > 0 && canSwipePrevious) {
      onSwipePrevious?.()
      return
    }
    if (deltaX < 0 && canSwipeNext) {
      onSwipeNext?.()
    }
  }

  return (
    <section className="card question-card" onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
      <div className="meta">
        <span>第 {question.question_number} 题</span>
        {question.subject ? <span>{question.subject}</span> : null}
        {question.year ? <span>{question.year}</span> : null}
        {sourceLabel ? <span>{sourceLabel}</span> : null}
        <span>已作答 {question.attempt_count || 0} 次</span>
      </div>
      <h2 className="stem">{question.stem}</h2>
      <p className="tap-hint">点击选项后直接提交答案，左右滑动可切换上一题或下一题</p>
      <div className="options">
        {question.options.map((option) => {
          const active = selectedAnswer === option.label
          return (
            <button
              key={option.label}
              type="button"
              className={`option ${active ? 'active' : ''}`}
              disabled={disabled}
              onClick={() => onSelect(option.label)}
            >
              <span className="option-label">{option.label}</span>
              <span>{option.content}</span>
              {submitting && active ? <span className="option-state">提交中...</span> : null}
            </button>
          )
        })}
      </div>
      <AnswerResult
        result={result}
        aiExplanation={aiExplanation}
        loadingAI={loadingAI}
        onRequestAIExplanation={onRequestAIExplanation}
        embedded
      />
    </section>
  )
}
