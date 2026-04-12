import ReactMarkdown from 'react-markdown'

export default function AnswerResult({ result, aiExplanation, loadingAI, onRequestAIExplanation, embedded = false }) {
  if (!result) {
    return null
  }

  return (
    <section className={`result-card ${embedded ? 'embedded' : 'card'}`}>
      <div className={`result-badge ${result.correct ? 'correct' : 'wrong'}`}>
        {result.correct ? '回答正确' : '回答错误'}
      </div>
      <p><strong>正确答案：</strong>{result.answer}</p>
      <p className="explanation"><strong>解析：</strong>{result.explanation || '暂无解析'}</p>
      <button type="button" className="secondary-button" onClick={onRequestAIExplanation} disabled={loadingAI}>
        {loadingAI ? 'AI 讲解生成中...' : 'AI 讲题'}
      </button>
      {(aiExplanation || loadingAI) ? (
        <div className={`ai-box markdown-body ${embedded ? 'embedded' : ''}`}>
          <strong>AI 讲解</strong>
          <ReactMarkdown>{aiExplanation || 'AI 正在生成讲解，请稍候...'}</ReactMarkdown>
        </div>
      ) : null}
    </section>
  )
}
