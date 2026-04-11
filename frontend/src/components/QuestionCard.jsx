export default function QuestionCard({ question, selectedAnswer, disabled, onSelect, sourceLabel, submitting = false }) {
  return (
    <section className="card">
      <div className="meta">
        <span>第 {question.question_number} 题</span>
        {question.subject ? <span>{question.subject}</span> : null}
        {question.year ? <span>{question.year}</span> : null}
        {sourceLabel ? <span>{sourceLabel}</span> : null}
      </div>
      <h2 className="stem">{question.stem}</h2>
      <p className="tap-hint">点击选项后直接提交答案</p>
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
    </section>
  )
}
