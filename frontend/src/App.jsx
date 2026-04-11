import { useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchRandomQuestion,
  fetchUploadedFiles,
  fetchWrongAnswerHistory,
  importPdfs,
  streamAIExplanation,
  submitAnswer,
  updateWrongQuestionState,
} from './api'
import QuestionCard from './components/QuestionCard'
import AnswerResult from './components/AnswerResult'

function formatDateTime(value) {
  if (!value) {
    return ''
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

function getImportStatusMeta(status) {
  if (status === 'success') {
    return { label: '成功', className: 'success' }
  }
  if (status === 'partial_success') {
    return { label: '部分成功', className: 'partial' }
  }
  return { label: '失败', className: 'failed' }
}

function getImportSummary(result) {
  if (!result) {
    return ''
  }
  if (result.failed_file_count === 0 && result.partial_file_count === 0) {
    return '批量导入完成'
  }
  if (result.success_file_count === 0 && result.partial_file_count === 0) {
    return '导入失败'
  }
  return '批量导入完成，部分文件需要处理'
}

function getUploadStageText(stage) {
  if (stage === 'uploading') {
    return '正在上传文件'
  }
  if (stage === 'processing') {
    return '文件上传完成，正在解析中'
  }
  if (stage === 'saving') {
    return '解析完成，正在写入题库'
  }
  if (stage === 'done') {
    return '导入完成'
  }
  return ''
}

export default function App() {
  const [question, setQuestion] = useState(null)
  const [selectedAnswer, setSelectedAnswer] = useState('')
  const [result, setResult] = useState(null)
  const [aiExplanation, setAIExplanation] = useState('')
  const [loadingQuestion, setLoadingQuestion] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [loadingAI, setLoadingAI] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadStage, setUploadStage] = useState('idle')
  const [uploadProgress, setUploadProgress] = useState(0)
  const [selectedFiles, setSelectedFiles] = useState([])
  const [importResult, setImportResult] = useState(null)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [selectedSourceFile, setSelectedSourceFile] = useState('all')
  const [wrongHistory, setWrongHistory] = useState([])
  const [historyTab, setHistoryTab] = useState('wrong')
  const [expandedQuestionIds, setExpandedQuestionIds] = useState([])
  const [loadingFiles, setLoadingFiles] = useState(true)
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [historyActionQuestionId, setHistoryActionQuestionId] = useState('')
  const [libraryPanelOpen, setLibraryPanelOpen] = useState(false)
  const [initialized, setInitialized] = useState(false)
  const [error, setError] = useState('')
  const aiAbortRef = useRef(null)
  const uploadInputRef = useRef(null)
  const submitLockRef = useRef(false)

  const sourceLabelMap = useMemo(() => {
    const pairs = uploadedFiles.map((item) => [item.source_file, item.file_name])
    return Object.fromEntries(pairs)
  }, [uploadedFiles])

  const currentSourceLabel = question ? (sourceLabelMap[question.source_file] || question.source_file) : ''
  const historyTitle = historyTab === 'wrong' ? '错题' : '收藏'
  const selectedFileCountText = selectedFiles.length ? `已选择 ${selectedFiles.length} 个文件` : ''
  const currentScopeLabel = selectedSourceFile === 'all'
    ? '全部题库'
    : (sourceLabelMap[selectedSourceFile] || '当前文件')
  const selectedFileInfo = uploadedFiles.find((item) => item.source_file === selectedSourceFile) || null
  const displayHistory = historyTab === 'favorites'
    ? wrongHistory
    : wrongHistory.filter((item) => !item.hidden_from_wrong_history)

  async function refreshUploadedFiles() {
    setLoadingFiles(true)
    try {
      const files = await fetchUploadedFiles()
      setUploadedFiles(files)
      if (selectedSourceFile !== 'all' && !files.some((item) => item.source_file === selectedSourceFile)) {
        setSelectedSourceFile('all')
      }
    } finally {
      setLoadingFiles(false)
    }
  }

  async function refreshWrongHistory(sourceFile = selectedSourceFile, view = historyTab) {
    setLoadingHistory(true)
    try {
      const history = await fetchWrongAnswerHistory(sourceFile, { favoritesOnly: view === 'favorites' })
      setWrongHistory(history)
      setExpandedQuestionIds((current) => current.filter((id) => history.some((item) => item.question_id === id)))
    } finally {
      setLoadingHistory(false)
    }
  }

  async function loadQuestion(sourceFile = selectedSourceFile) {
    if (aiAbortRef.current) {
      aiAbortRef.current.abort()
      aiAbortRef.current = null
    }
    setLoadingQuestion(true)
    submitLockRef.current = false
    setError('')
    setSelectedAnswer('')
    setResult(null)
    setAIExplanation('')
    try {
      const data = await fetchRandomQuestion(sourceFile)
      setQuestion(data)
    } catch (err) {
      setError(err.message)
      setQuestion(null)
    } finally {
      setLoadingQuestion(false)
    }
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        await Promise.all([
          refreshUploadedFiles(),
          refreshWrongHistory('all', 'wrong'),
          loadQuestion('all'),
        ])
      } catch (err) {
        setError(err.message)
      } finally {
        setInitialized(true)
      }
    }

    bootstrap()

    return () => {
      if (aiAbortRef.current) {
        aiAbortRef.current.abort()
      }
    }
  }, [])

  useEffect(() => {
    if (!initialized) {
      return
    }
    loadQuestion(selectedSourceFile).catch((err) => setError(err.message))
  }, [initialized, selectedSourceFile])

  useEffect(() => {
    if (!initialized) {
      return
    }
    refreshWrongHistory(selectedSourceFile, historyTab).catch((err) => setError(err.message))
  }, [initialized, selectedSourceFile, historyTab])

  async function handleSubmit(answerToSubmit = selectedAnswer) {
    if (!question || !answerToSubmit || submitLockRef.current || result) {
      return
    }
    submitLockRef.current = true
    setSubmitting(true)
    setError('')
    setSelectedAnswer(answerToSubmit)
    try {
      const data = await submitAnswer(question.id, answerToSubmit)
      setResult(data)
      await refreshWrongHistory(selectedSourceFile, historyTab)
    } catch (err) {
      setError(err.message)
    } finally {
      submitLockRef.current = false
      setSubmitting(false)
    }
  }

  async function handleAIExplanation() {
    if (!question) {
      return
    }
    if (aiAbortRef.current) {
      aiAbortRef.current.abort()
    }

    const controller = new AbortController()
    aiAbortRef.current = controller
    setLoadingAI(true)
    setError('')
    setAIExplanation('')

    try {
      await streamAIExplanation(question.id, {
        signal: controller.signal,
        onChunk: (chunk) => {
          setAIExplanation((current) => current + chunk)
        },
      })
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err.message)
      }
    } finally {
      if (aiAbortRef.current === controller) {
        aiAbortRef.current = null
      }
      setLoadingAI(false)
    }
  }

  async function handleImport() {
    if (!selectedFiles.length) {
      setError('请先选择至少一个 PDF 文件')
      return
    }

    setUploading(true)
    setUploadStage('uploading')
    setUploadProgress(0)
    setError('')
    setImportResult(null)
    try {
      const data = await importPdfs(selectedFiles, {
        onProgress: (progress) => {
          setUploadProgress(progress)
          if (progress >= 100) {
            setUploadStage('processing')
          }
        },
      })
      setUploadStage('saving')
      setImportResult(data)
      setSelectedFiles([])
      if (uploadInputRef.current) {
        uploadInputRef.current.value = ''
      }
      await refreshUploadedFiles()
      await refreshWrongHistory(selectedSourceFile, historyTab)
      if (!question) {
        await loadQuestion(selectedSourceFile)
      }
      setUploadStage('done')
    } catch (err) {
      setError(err.message)
      setUploadStage('idle')
    } finally {
      setUploading(false)
    }
  }

  async function handleToggleFavorite(item) {
    setHistoryActionQuestionId(item.question_id)
    setError('')
    const nextFavorite = !item.is_favorite
    try {
      await updateWrongQuestionState(item.question_id, { is_favorite: nextFavorite })
      if (question?.id === item.question_id) {
        setQuestion((current) => (current ? { ...current, is_favorite: nextFavorite } : current))
      }
      await refreshWrongHistory(selectedSourceFile, historyTab)
    } catch (err) {
      setError(err.message)
    } finally {
      setHistoryActionQuestionId('')
    }
  }

  async function handleHideWrongItem(item) {
    if (item.hidden_from_wrong_history) {
      return
    }
    setHistoryActionQuestionId(item.question_id)
    setError('')
    try {
      await updateWrongQuestionState(item.question_id, { hidden_from_wrong_history: true })
      await refreshWrongHistory(selectedSourceFile, historyTab)
    } catch (err) {
      setError(err.message)
    } finally {
      setHistoryActionQuestionId('')
    }
  }

  function toggleExpandedQuestion(questionId) {
    setExpandedQuestionIds((current) => (
      current.includes(questionId)
        ? current.filter((id) => id !== questionId)
        : [...current, questionId]
    ))
  }

  return (
    <main className="page">
      <div className="container">
        <header className="header">
          <div>
            <h1>护理刷题系统</h1>
            <p>支持多文件导入、按文件练题、错题收藏与紧凑错题管理</p>
          </div>
          <button type="button" className="secondary-button" onClick={() => loadQuestion()} disabled={loadingQuestion}>
            {loadingQuestion ? '加载中...' : '换一题'}
          </button>
        </header>

        <section className="card library-card">
          <div className="library-toolbar">
            <div className="library-toolbar-main">
              <h2>做题范围</h2>
              <p className="section-subtitle">
                当前：{currentScopeLabel} · {loadingFiles ? '文件加载中...' : `共 ${uploadedFiles.length} 个文件`}
              </p>
            </div>
            <div className="library-toolbar-actions">
              <button
                type="button"
                className="secondary-button compact-toggle-button"
                onClick={() => setLibraryPanelOpen((open) => !open)}
              >
                {libraryPanelOpen ? '收起题库' : '管理题库'}
              </button>
            </div>
          </div>

          <div className="scope-selector-bar">
            <select
              className="scope-select"
              value={selectedSourceFile}
              onChange={(event) => setSelectedSourceFile(event.target.value)}
              aria-label="做题范围选择"
            >
              <option value="all">全部题库</option>
              {uploadedFiles.map((item) => (
                <option key={item.source_file} value={item.source_file}>
                  {item.file_name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="ghost-button scope-random-button"
              onClick={() => loadQuestion(selectedSourceFile)}
              disabled={loadingQuestion}
            >
              {loadingQuestion ? '加载中...' : '刷新范围题目'}
            </button>
          </div>

          {selectedFileInfo ? (
            <div className="selected-scope-summary">
              <strong>{selectedFileInfo.file_name}</strong>
              <p>
                题目 {selectedFileInfo.question_count} 题 · 新增 {selectedFileInfo.inserted_count} ·
                重复 {selectedFileInfo.skipped_count} · 兜底 {selectedFileInfo.fallback_question_count}
              </p>
            </div>
          ) : (
            <div className="selected-scope-summary all-scope-summary">
              <strong>全部题库随机练习</strong>
              <p>会从所有已导入文件中随机抽题，更适合连续刷题。</p>
            </div>
          )}

          {libraryPanelOpen ? (
            <div className="library-panel">
              <div className="library-upload-block">
                <div className="section-header compact-section-header">
                  <div>
                    <h3>导入 PDF</h3>
                    <p className="upload-help">一次可选多个 PDF。单个文件失败时，其他文件仍继续导入。</p>
                  </div>
                </div>
                <div className="upload-row compact-upload-row">
                  <label className="file-picker-button">
                    <input
                      ref={uploadInputRef}
                      type="file"
                      accept=".pdf,application/pdf"
                      multiple
                      className="sr-only"
                      onChange={(event) => setSelectedFiles(Array.from(event.target.files || []))}
                    />
                    <span>{selectedFiles.length ? '重新选择文件' : '选择 PDF 文件'}</span>
                  </label>
                  <button type="button" className="primary-button" onClick={handleImport} disabled={uploading || !selectedFiles.length}>
                    {uploading ? '导入中...' : '开始导入'}
                  </button>
                </div>
                {selectedFileCountText ? <p className="upload-file">{selectedFileCountText}</p> : null}
                {uploading || uploadStage === 'done' ? (
                  <div className="upload-progress-card" aria-live="polite">
                    <div className="upload-progress-top">
                      <strong>{getUploadStageText(uploadStage)}</strong>
                      <span>{uploadStage === 'uploading' || uploadStage === 'processing' ? `${uploadProgress}%` : ''}</span>
                    </div>
                    <div className="upload-progress-track">
                      <div
                        className={`upload-progress-bar ${uploadStage === 'processing' ? 'processing' : ''} ${uploadStage === 'done' ? 'done' : ''}`}
                        style={{ width: uploadStage === 'done' ? '100%' : `${uploadProgress}%` }}
                      />
                    </div>
                    {uploadStage === 'processing' ? <p className="upload-stage-text">服务器正在解析 PDF 内容。</p> : null}
                    {uploadStage === 'saving' ? <p className="upload-stage-text">服务器正在写入题库，请稍候。</p> : null}
                    {uploadStage === 'done' ? <p className="upload-stage-text">本次导入流程已完成。</p> : null}
                  </div>
                ) : null}
                {selectedFiles.length ? (
                  <div className="selected-file-list compact-selected-files">
                    {selectedFiles.map((file) => (
                      <span key={`${file.name}-${file.size}-${file.lastModified}`} className="file-chip">{file.name}</span>
                    ))}
                  </div>
                ) : null}
                {importResult ? (
                  <div className="import-result">
                    <div className="import-summary">
                      <strong>{getImportSummary(importResult)}</strong>
                      <p>
                        共 {importResult.total_files} 个文件 · 成功 {importResult.success_file_count} 个 ·
                        部分成功 {importResult.partial_file_count} 个 · 失败 {importResult.failed_file_count} 个
                      </p>
                      <p>
                        解析题目 {importResult.total_parsed_question_count} 题 · 新增 {importResult.total_inserted_count} 题 ·
                        跳过重复 {importResult.total_skipped_count} 题
                      </p>
                    </div>
                    <div className="import-batch-list">
                      {importResult.results.map((item) => {
                        const statusMeta = getImportStatusMeta(item.status)
                        return (
                          <div key={`${item.file_name}-${item.source_file || item.message}`} className="import-file-item">
                            <div className="import-file-top">
                              <strong>{item.file_name}</strong>
                              <span className={`status-badge ${statusMeta.className}`}>{statusMeta.label}</span>
                            </div>
                            <p className="import-file-meta">
                              解析 {item.parsed_question_count} 题 · 新增 {item.inserted_count} 题 · 重复 {item.skipped_count} 题 ·
                              AI 兜底 {item.fallback_question_count} 题 · 失败 {item.failed_question_count} 题
                            </p>
                            <p className="import-file-message">{item.message}</p>
                            {item.errors?.length ? (
                              <ul className="import-error-list">
                                {item.errors.slice(0, 3).map((errorText) => (
                                  <li key={errorText}>{errorText}</li>
                                ))}
                              </ul>
                            ) : null}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="library-files-block">
                <div className="section-header compact-section-header">
                  <div>
                    <h3>已导入文件</h3>
                    <p className="section-subtitle">{loadingFiles ? '加载中...' : `共 ${uploadedFiles.length} 个文件`}</p>
                  </div>
                </div>
                {uploadedFiles.length ? (
                  <div className="file-list compact-file-list">
                    {uploadedFiles.map((item) => (
                      <button
                        key={item.source_file}
                        type="button"
                        className={`file-item compact-file-item ${selectedSourceFile === item.source_file ? 'active' : ''}`}
                        onClick={() => setSelectedSourceFile(item.source_file)}
                      >
                        <div>
                          <strong>{item.file_name}</strong>
                          <p className="file-meta">题目 {item.question_count} 题 · 最近导入 {formatDateTime(item.last_imported_at)}</p>
                        </div>
                        <div className="file-stats">
                          <span>新增 {item.inserted_count}</span>
                          <span>重复 {item.skipped_count}</span>
                          <span>兜底 {item.fallback_question_count}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="empty-text">还没有已记录的上传文件。</p>
                )}
              </div>
            </div>
          ) : null}
        </section>

        {error ? <div className="error-box">{error}</div> : null}

        {loadingQuestion ? <section className="card">正在加载题目...</section> : null}

        {question ? (
          <>
            <QuestionCard
              question={question}
              selectedAnswer={selectedAnswer}
              disabled={Boolean(result) || submitting}
              onSelect={(answer) => handleSubmit(answer)}
              sourceLabel={currentSourceLabel}
              submitting={submitting}
            />

            <div className="actions single-action-row">
              <button type="button" className="secondary-button" onClick={() => loadQuestion()} disabled={loadingQuestion}>
                下一题
              </button>
            </div>

            <AnswerResult
              result={result}
              aiExplanation={aiExplanation}
              loadingAI={loadingAI}
              onRequestAIExplanation={handleAIExplanation}
            />
          </>
        ) : null}

        <section className="card">
          <div className="section-header history-header">
            <div>
              <h2>题目管理</h2>
              <span className="section-subtitle">{loadingHistory ? '加载中...' : `当前 ${historyTitle} ${displayHistory.length} 条`}</span>
            </div>
            <div className="history-tabs">
              <button
                type="button"
                className={`tab-button ${historyTab === 'wrong' ? 'active' : ''}`}
                onClick={() => setHistoryTab('wrong')}
              >
                错题
              </button>
              <button
                type="button"
                className={`tab-button ${historyTab === 'favorites' ? 'active' : ''}`}
                onClick={() => setHistoryTab('favorites')}
              >
                收藏
              </button>
            </div>
          </div>
          {displayHistory.length ? (
            <div className="history-list compact-history-list">
              {displayHistory.map((item) => {
                const isExpanded = expandedQuestionIds.includes(item.question_id)
                const actionLoading = historyActionQuestionId === item.question_id
                return (
                  <div key={item.question_id} className={`history-item compact ${isExpanded ? 'expanded' : ''}`}>
                    <div className="history-row">
                      <div className="history-main">
                        <div className="history-title-row">
                          <strong>第 {item.question_number} 题</strong>
                          <span className="history-file-name">{item.file_name}</span>
                          {item.is_favorite ? <span className="mini-badge favorite">已收藏</span> : null}
                          {item.hidden_from_wrong_history ? <span className="mini-badge muted">已移出错题</span> : null}
                        </div>
                        <p className={`history-preview ${isExpanded ? 'expanded' : ''}`}>{item.stem}</p>
                        <p className="history-meta">
                          你的答案 {item.selected_answer} · 正确答案 {item.correct_answer}
                          {item.subject ? ` · ${item.subject}` : ''}
                          {item.year ? ` · ${item.year}` : ''}
                          {item.answered_at ? ` · ${formatDateTime(item.answered_at)}` : ''}
                        </p>
                      </div>
                      <div className="history-actions-inline">
                        <button
                          type="button"
                          className={`ghost-button ${item.is_favorite ? 'active' : ''}`}
                          onClick={() => handleToggleFavorite(item)}
                          disabled={actionLoading}
                        >
                          {item.is_favorite ? '取消收藏' : '收藏'}
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => toggleExpandedQuestion(item.question_id)}
                        >
                          {isExpanded ? '收起' : '详情'}
                        </button>
                        <button
                          type="button"
                          className="danger-button"
                          onClick={() => handleHideWrongItem(item)}
                          disabled={actionLoading || item.hidden_from_wrong_history}
                        >
                          {item.hidden_from_wrong_history ? '已移除' : '删除'}
                        </button>
                      </div>
                    </div>
                    {isExpanded ? (
                      <div className="history-detail">
                        <p><strong>题干：</strong>{item.stem}</p>
                        <p><strong>文件：</strong>{item.file_name}</p>
                        <p><strong>作答时间：</strong>{formatDateTime(item.answered_at)}</p>
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="empty-text">{historyTab === 'wrong' ? '当前范围下还没有错题。' : '当前范围下还没有收藏题。'}</p>
          )}
        </section>
      </div>
    </main>
  )
}
