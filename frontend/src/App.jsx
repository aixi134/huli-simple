import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  deleteQuestion,
  deleteUploadedFile,
  fetchPracticeRecords,
  fetchRandomQuestion,
  fetchScopeStats,
  fetchUploadedFiles,
  fetchWeaknessAnalysis,
  fetchWeaknessRecommendation,
  fetchWrongAnswerHistory,
  importPdfs,
  streamAIExplanation,
  submitAnswer,
  updateWrongQuestionState,
} from './api'
import QuestionCard from './components/QuestionCard'

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

function getScopeQuery(scopeType, sourceFile) {
  if (scopeType === 'wrong_only') {
    return { scopeType: 'wrong_only' }
  }
  if (scopeType === 'source_file' && sourceFile && sourceFile !== 'all') {
    return { scopeType: 'source_file', sourceFile }
  }
  return { scopeType: 'all' }
}

function createEmptyWeaknessAnalysis() {
  return {
    wrong_attempt_count: 0,
    wrong_question_count: 0,
    top_subjects: [],
    top_confusion_pairs: [],
    repeated_wrong_questions: [],
    sample_questions: [],
  }
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
  const [scopeType, setScopeType] = useState('all')
  const [selectedSourceFile, setSelectedSourceFile] = useState('all')
  const [activeView, setActiveView] = useState('quiz')
  const [wrongHistory, setWrongHistory] = useState([])
  const [historyTab, setHistoryTab] = useState('wrong')
  const [expandedQuestionIds, setExpandedQuestionIds] = useState([])
  const [loadingFiles, setLoadingFiles] = useState(true)
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [historyActionQuestionId, setHistoryActionQuestionId] = useState('')
  const [historyAIByQuestionId, setHistoryAIByQuestionId] = useState({})
  const [historyAILoadingId, setHistoryAILoadingId] = useState('')
  const [recordBuckets, setRecordBuckets] = useState([])
  const [loadingRecords, setLoadingRecords] = useState(true)
  const [weaknessAnalysis, setWeaknessAnalysis] = useState(createEmptyWeaknessAnalysis())
  const [loadingWeaknessAnalysis, setLoadingWeaknessAnalysis] = useState(true)
  const [weaknessRecommendation, setWeaknessRecommendation] = useState(null)
  const [loadingWeaknessRecommendation, setLoadingWeaknessRecommendation] = useState(false)
  const [scopeStats, setScopeStats] = useState({ total_count: 0, completed_count: 0, remaining_count: 0 })
  const [loadingScopeStats, setLoadingScopeStats] = useState(true)
  const [deletingQuestion, setDeletingQuestion] = useState(false)
  const [deletingFileId, setDeletingFileId] = useState('')
  const [libraryPanelOpen, setLibraryPanelOpen] = useState(false)
  const [questionHistory, setQuestionHistory] = useState([])
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(-1)
  const [initialized, setInitialized] = useState(false)
  const [error, setError] = useState('')
  const aiAbortRef = useRef(null)
  const uploadInputRef = useRef(null)
  const submitLockRef = useRef(false)
  const questionHistoryRef = useRef([])
  const currentQuestionIndexRef = useRef(-1)

  const sourceLabelMap = useMemo(() => {
    const pairs = uploadedFiles.map((item) => [item.source_file, item.file_name])
    return Object.fromEntries(pairs)
  }, [uploadedFiles])

  useEffect(() => {
    questionHistoryRef.current = questionHistory
  }, [questionHistory])

  useEffect(() => {
    currentQuestionIndexRef.current = currentQuestionIndex
  }, [currentQuestionIndex])

  const currentSourceLabel = question ? (sourceLabelMap[question.source_file] || question.source_file) : ''
  const historyTitle = historyTab === 'wrong' ? '错题' : '收藏'
  const selectedFileCountText = selectedFiles.length ? `已选择 ${selectedFiles.length} 个文件` : ''
  const canGoPreviousQuestion = currentQuestionIndex > 0
  const canGoNextQuestion = currentQuestionIndex >= 0 && currentQuestionIndex < questionHistory.length - 1
  const canSwipePrevious = canGoPreviousQuestion && !loadingQuestion && !submitting
  const canSwipeNext = !loadingQuestion && !submitting
  const questionProgressText = currentQuestionIndex >= 0 ? `本轮第 ${currentQuestionIndex + 1} / ${questionHistory.length} 题` : ''
  const currentScopeLabel = scopeType === 'wrong_only'
    ? '错题库'
    : scopeType === 'source_file'
      ? (selectedSourceFile !== 'all' ? (sourceLabelMap[selectedSourceFile] || '当前文件') : '未选择文件')
      : '全部题库'
  const currentScopeHint = scopeType === 'wrong_only'
    ? '仅推送仍未订正的错题'
    : scopeType === 'source_file'
      ? '优先未做题，已答对题默认不再推送'
      : '优先未做题，已答对题默认不再推送'
  const selectedFileInfo = uploadedFiles.find((item) => item.source_file === selectedSourceFile) || null
  const displayHistory = historyTab === 'favorites'
    ? wrongHistory
    : wrongHistory.filter((item) => !item.hidden_from_wrong_history)
  const currentScopeQuery = getScopeQuery(scopeType, selectedSourceFile)
  const recordsSourceFile = scopeType === 'source_file' ? selectedSourceFile : 'all'
  const totalRecordAttemptCount = useMemo(
    () => recordBuckets.reduce((total, bucket) => total + (bucket.attempt_count ?? bucket.items?.length ?? 0), 0),
    [recordBuckets],
  )

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

  async function refreshPracticeRecords(sourceFile = recordsSourceFile) {
    setLoadingRecords(true)
    try {
      const records = await fetchPracticeRecords(sourceFile)
      setRecordBuckets(records)
    } finally {
      setLoadingRecords(false)
    }
  }

  async function refreshWeaknessAnalysis(scope = currentScopeQuery) {
    setLoadingWeaknessAnalysis(true)
    setWeaknessRecommendation(null)
    try {
      const analysis = await fetchWeaknessAnalysis(scope)
      setWeaknessAnalysis(analysis)
    } finally {
      setLoadingWeaknessAnalysis(false)
    }
  }

  async function refreshScopeStats(scope = currentScopeQuery) {
    setLoadingScopeStats(true)
    try {
      const stats = await fetchScopeStats(scope)
      setScopeStats(stats)
    } finally {
      setLoadingScopeStats(false)
    }
  }

  function resetQuestionView() {
    if (aiAbortRef.current) {
      aiAbortRef.current.abort()
      aiAbortRef.current = null
    }
    submitLockRef.current = false
    setError('')
    setSelectedAnswer('')
    setResult(null)
    setAIExplanation('')
  }

  function applyQuestion(data) {
    resetQuestionView()
    setQuestion(data)
  }

  async function loadQuestion(scope = currentScopeQuery, options = {}) {
    const { appendHistory = true, resetHistory = false } = options
    setLoadingQuestion(true)
    resetQuestionView()
    try {
      const data = await fetchRandomQuestion(scope)
      setQuestion(data)
      if (resetHistory) {
        setQuestionHistory([data])
        setCurrentQuestionIndex(0)
      } else if (appendHistory) {
        const baseIndex = currentQuestionIndexRef.current
        const nextHistory = questionHistoryRef.current.slice(0, baseIndex + 1)
        nextHistory.push(data)
        setQuestionHistory(nextHistory)
        setCurrentQuestionIndex(nextHistory.length - 1)
      }
    } catch (err) {
      setError(err.message)
      setQuestion(null)
      if (resetHistory) {
        setQuestionHistory([])
        setCurrentQuestionIndex(-1)
      }
    } finally {
      setLoadingQuestion(false)
    }
  }

  function showQuestionFromHistory(index) {
    const target = questionHistoryRef.current[index]
    if (!target) {
      return
    }
    setLoadingQuestion(false)
    setCurrentQuestionIndex(index)
    applyQuestion(target)
  }

  function handlePreviousQuestion() {
    if (!canGoPreviousQuestion) {
      return
    }
    showQuestionFromHistory(currentQuestionIndex - 1)
  }

  async function handleNextQuestion() {
    if (canGoNextQuestion) {
      showQuestionFromHistory(currentQuestionIndex + 1)
      return
    }
    await loadQuestion(currentScopeQuery)
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        await refreshUploadedFiles()
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
    loadQuestion(currentScopeQuery, { resetHistory: true }).catch((err) => setError(err.message))
  }, [initialized, scopeType, selectedSourceFile])

  useEffect(() => {
    if (!initialized) {
      return
    }
    refreshWrongHistory(selectedSourceFile, historyTab).catch((err) => setError(err.message))
    refreshPracticeRecords(recordsSourceFile).catch((err) => setError(err.message))
    refreshWeaknessAnalysis(currentScopeQuery).catch((err) => setError(err.message))
    refreshScopeStats(currentScopeQuery).catch((err) => setError(err.message))
  }, [initialized, selectedSourceFile, historyTab, scopeType])

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
      setQuestion((current) => (current ? { ...current, attempt_count: data.attempt_count } : current))
      await refreshPracticeRecords(recordsSourceFile)
      await refreshWeaknessAnalysis(currentScopeQuery)
      await refreshScopeStats(currentScopeQuery)
      if (data.correct) {
        await handleNextQuestion()
        return
      }
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
      await refreshPracticeRecords(recordsSourceFile)
      await refreshWeaknessAnalysis(currentScopeQuery)
      await refreshScopeStats(currentScopeQuery)
      if (!question) {
        await loadQuestion(currentScopeQuery)
      }
      setUploadStage('done')
    } catch (err) {
      setError(err.message)
      setUploadStage('idle')
    } finally {
      setUploading(false)
    }
  }

  async function handleDeleteUploadedFile(item) {
    if (!item || deletingFileId) {
      return
    }
    const confirmed = window.confirm(`确认删除文件“${item.file_name}”吗？删除后将同时移除该文件下的题目、作答记录和错题记录。`)
    if (!confirmed) {
      return
    }

    const removedQuestionIds = wrongHistory
      .filter((historyItem) => historyItem.source_file === item.source_file)
      .map((historyItem) => historyItem.question_id)

    setDeletingFileId(item.id)
    setError('')
    try {
      await deleteUploadedFile(item.id)
      const nextScopeType = scopeType === 'source_file' && selectedSourceFile === item.source_file ? 'all' : scopeType
      const nextSourceFile = selectedSourceFile === item.source_file ? 'all' : selectedSourceFile
      const nextScopeQuery = getScopeQuery(nextScopeType, nextSourceFile)
      const nextHistory = questionHistoryRef.current.filter((entry) => entry.source_file !== item.source_file)
      const currentQuestionDeleted = question?.source_file === item.source_file

      setQuestionHistory(nextHistory)
      setCurrentQuestionIndex(-1)
      setWrongHistory((current) => current.filter((historyItem) => historyItem.source_file !== item.source_file))
      setExpandedQuestionIds((current) => current.filter((id) => !removedQuestionIds.includes(id)))
      setHistoryAIByQuestionId((current) => {
        const next = { ...current }
        removedQuestionIds.forEach((questionId) => {
          delete next[questionId]
        })
        return next
      })
      if (currentQuestionDeleted) {
        setQuestion(null)
        setResult(null)
        setAIExplanation('')
      }
      if (selectedSourceFile === item.source_file) {
        setSelectedSourceFile('all')
      }
      if (scopeType === 'source_file' && selectedSourceFile === item.source_file) {
        setScopeType('all')
      }
      await refreshUploadedFiles()
      await refreshWrongHistory(nextSourceFile, historyTab)
      await refreshPracticeRecords(nextScopeType === 'source_file' ? nextSourceFile : 'all')
      await refreshWeaknessAnalysis(nextScopeQuery)
      await refreshScopeStats(nextScopeQuery)
      if (currentQuestionDeleted || nextHistory.length === 0 || scopeType !== nextScopeType || selectedSourceFile !== nextSourceFile) {
        await loadQuestion(nextScopeQuery, { resetHistory: true })
      }
      setLibraryPanelOpen(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingFileId('')
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

  async function handleDeleteCurrentQuestion() {
    if (!question || deletingQuestion) {
      return
    }
    const confirmed = window.confirm('确认从题库删除当前题目吗？删除后将同时移除作答记录和错题记录。')
    if (!confirmed) {
      return
    }
    setDeletingQuestion(true)
    setError('')
    try {
      await deleteQuestion(question.id)
      const nextHistory = questionHistoryRef.current.filter((item) => item.id !== question.id)
      setQuestionHistory(nextHistory)
      setCurrentQuestionIndex(-1)
      setQuestion(null)
      setResult(null)
      setAIExplanation('')
      setWrongHistory((current) => current.filter((item) => item.question_id !== question.id))
      setExpandedQuestionIds((current) => current.filter((id) => id !== question.id))
      setHistoryAIByQuestionId((current) => {
        const next = { ...current }
        delete next[question.id]
        return next
      })
      await refreshUploadedFiles()
      await refreshWrongHistory(selectedSourceFile, historyTab)
      await refreshPracticeRecords(recordsSourceFile)
      await refreshWeaknessAnalysis(currentScopeQuery)
      await refreshScopeStats(currentScopeQuery)
      await loadQuestion(currentScopeQuery, { resetHistory: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingQuestion(false)
    }
  }

  async function handleHistoryAIExplanation(questionId) {
    if (!questionId || historyAILoadingId === questionId || historyAIByQuestionId[questionId]) {
      return
    }
    if (aiAbortRef.current) {
      aiAbortRef.current.abort()
    }
    const controller = new AbortController()
    aiAbortRef.current = controller
    setHistoryAILoadingId(questionId)
    setError('')
    try {
      let content = ''
      await streamAIExplanation(questionId, {
        signal: controller.signal,
        onChunk: (chunk) => {
          content += chunk
          setHistoryAIByQuestionId((current) => ({ ...current, [questionId]: content }))
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
      setHistoryAILoadingId('')
    }
  }

  function toggleExpandedQuestion(questionId) {
    setExpandedQuestionIds((current) => (
      current.includes(questionId)
        ? current.filter((id) => id !== questionId)
        : [...current, questionId]
    ))
  }

  function handleScopeTypeChange(value) {
    setScopeType(value)
    if (value !== 'source_file') {
      setSelectedSourceFile('all')
    }
    if (window.innerWidth <= 720 && value !== 'source_file') {
      setLibraryPanelOpen(false)
    }
  }

  function handleSelectSourceFile(value) {
    setScopeType('source_file')
    setSelectedSourceFile(value)
    if (window.innerWidth <= 720 && value !== 'all') {
      setLibraryPanelOpen(false)
    }
  }

  function renderScopeProgressBadges() {
    if (loadingScopeStats) {
      return <span className="section-subtitle">统计中...</span>
    }

    return (
      <div className="summary-badge-row">
        <span className="mini-badge done">已做 {scopeStats.completed_count}</span>
        <span className="mini-badge pending">未做 {scopeStats.remaining_count}</span>
      </div>
    )
  }

  function renderPracticeRecordSummaryBadges() {
    if (loadingRecords) {
      return <span className="section-subtitle">加载中...</span>
    }

    return (
      <div className="summary-badge-row">
        <span className="mini-badge muted">时间段 {recordBuckets.length}</span>
        <span className="mini-badge total">已做总数 {totalRecordAttemptCount}</span>
      </div>
    )
  }

  async function handleGenerateWeaknessRecommendation() {
    setLoadingWeaknessRecommendation(true)
    setWeaknessRecommendation(null)
    setError('')
    try {
      const recommendation = await fetchWeaknessRecommendation(currentScopeQuery)
      setWeaknessRecommendation(recommendation)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingWeaknessRecommendation(false)
    }
  }

  function renderScopeSummary() {
    if (scopeType === 'source_file' && selectedFileInfo) {
      return (
        <div className="selected-scope-summary">
          <strong>{selectedFileInfo.file_name}</strong>
          <p>
            题目 {selectedFileInfo.question_count} 题 · 新增 {selectedFileInfo.inserted_count} ·
            重复 {selectedFileInfo.skipped_count} · 兜底 {selectedFileInfo.fallback_question_count}
          </p>
          {renderScopeProgressBadges()}
        </div>
      )
    }
    if (scopeType === 'wrong_only') {
      return (
        <div className="selected-scope-summary all-scope-summary">
          <strong>错题库练习</strong>
          <p>只推送仍未订正的错题，适合集中复习薄弱点。</p>
          {renderScopeProgressBadges()}
        </div>
      )
    }
    return (
      <div className="selected-scope-summary all-scope-summary">
        <strong>全部题库随机练习</strong>
        <p>优先推送未做题，已答对题默认不再重复出现。</p>
        {renderScopeProgressBadges()}
      </div>
    )
  }

  return (
    <main className="page">
      <div className="container">
        <header className="header">
          <div>
            <h1>护理刷题系统</h1>
            <p>支持多文件导入、按文件练题、错题收藏与紧凑错题管理</p>
            {questionProgressText ? <p className="session-progress">{questionProgressText}</p> : null}
            <div className="scope-status-chip">
              <strong>当前范围：</strong>{currentScopeLabel}
              <span>{currentScopeHint}</span>
              {renderScopeProgressBadges()}
            </div>
          </div>
          <div className="header-actions">
            <div className="view-tabs">
              <button type="button" className={`tab-button ${activeView === 'quiz' ? 'active' : ''}`} onClick={() => setActiveView('quiz')}>
                刷题
              </button>
              <button type="button" className={`tab-button ${activeView === 'records' ? 'active' : ''}`} onClick={() => setActiveView('records')}>
                练习记录
              </button>
              <button type="button" className={`tab-button ${activeView === 'analysis' ? 'active' : ''}`} onClick={() => setActiveView('analysis')}>
                薄弱点分析
              </button>
            </div>
            <button type="button" className="secondary-button" onClick={() => handleNextQuestion()} disabled={loadingQuestion || submitting}>
              {loadingQuestion ? '加载中...' : '换一题'}
            </button>
          </div>
        </header>

        {libraryPanelOpen ? <button type="button" className="library-overlay-backdrop" aria-label="关闭题库面板" onClick={() => setLibraryPanelOpen(false)} /> : null}

        <button
          type="button"
          className={`library-fab ${libraryPanelOpen ? 'open' : ''}`}
          onClick={() => setLibraryPanelOpen((open) => !open)}
          aria-expanded={libraryPanelOpen}
          aria-controls="library-panel"
        >
          <span className="library-fab-label">题库</span>
          <span className="library-fab-meta">{currentScopeLabel}</span>
        </button>

        {libraryPanelOpen ? (
          <section id="library-panel" className="library-overlay card" role="dialog" aria-modal="true" aria-label="题库管理抽屉">
            <div className="library-sheet-handle" aria-hidden="true" />
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
                  onClick={() => setLibraryPanelOpen(false)}
                >
                  关闭题库
                </button>
              </div>
            </div>

            <div className="scope-selector-bar">
              <select
                className="scope-select"
                value={scopeType}
                onChange={(event) => handleScopeTypeChange(event.target.value)}
                aria-label="做题范围类型选择"
              >
                <option value="all">全部题库</option>
                <option value="source_file">按文件</option>
                <option value="wrong_only">错题库</option>
              </select>
              {scopeType === 'source_file' ? (
                <select
                  className="scope-select"
                  value={selectedSourceFile}
                  onChange={(event) => handleSelectSourceFile(event.target.value)}
                  aria-label="做题范围文件选择"
                >
                  <option value="all">请选择文件</option>
                  {uploadedFiles.map((item) => (
                    <option key={item.source_file} value={item.source_file}>
                      {item.file_name}
                    </option>
                  ))}
                </select>
              ) : null}
              <button
                type="button"
                className="ghost-button scope-random-button"
                onClick={() => loadQuestion(currentScopeQuery, { resetHistory: true })}
                disabled={loadingQuestion}
              >
                {loadingQuestion ? '加载中...' : '刷新范围题目'}
              </button>
            </div>

            {renderScopeSummary()}

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
                      <div
                        key={item.source_file}
                        className={`file-item compact-file-item ${scopeType === 'source_file' && selectedSourceFile === item.source_file ? 'active' : ''}`}
                      >
                        <button
                          type="button"
                          className="file-item-main"
                          onClick={() => handleSelectSourceFile(item.source_file)}
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
                        <button
                          type="button"
                          className="danger-button file-delete-button"
                          onClick={() => handleDeleteUploadedFile(item)}
                          disabled={deletingFileId === item.id}
                        >
                          {deletingFileId === item.id ? '删除中...' : '删除文件'}
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="empty-text">还没有已记录的上传文件。</p>
                )}
              </div>
            </div>
          </section>
        ) : null}

        {error ? <div className="error-box">{error}</div> : null}

        {activeView === 'quiz' && loadingQuestion ? <section className="card">正在加载题目...</section> : null}

        {activeView === 'quiz' && question ? (
          <>
            <QuestionCard
              question={question}
              selectedAnswer={selectedAnswer}
              disabled={Boolean(result) || submitting}
              onSelect={(answer) => handleSubmit(answer)}
              onSwipePrevious={handlePreviousQuestion}
              onSwipeNext={handleNextQuestion}
              canSwipePrevious={canSwipePrevious}
              canSwipeNext={canSwipeNext}
              sourceLabel={currentSourceLabel}
              submitting={submitting}
              result={result}
              aiExplanation={aiExplanation}
              loadingAI={loadingAI}
              onRequestAIExplanation={handleAIExplanation}
            />

            <div className="actions question-navigation-actions">

              <button type="button" className="secondary-button" onClick={handleNextQuestion} disabled={loadingQuestion || submitting}>
                {canGoNextQuestion ? '下一题' : '换一题'}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={handlePreviousQuestion}
                disabled={!canGoPreviousQuestion || loadingQuestion || submitting}
              >
                上一题
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={handleDeleteCurrentQuestion}
                disabled={loadingQuestion || submitting || deletingQuestion}
              >
                {deletingQuestion ? '删除中...' : '删除当前题目'}
              </button>
            </div>

          </>
        ) : null}

        {activeView === 'quiz' ? (
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
                  const historyAI = historyAIByQuestionId[item.question_id] || ''
                  const loadingHistoryAI = historyAILoadingId === item.question_id
                  return (
                    <div key={item.question_id} className={`history-item compact ${isExpanded ? 'expanded' : ''}`}>
                      <div className="history-row">
                        <div className="history-main">
                          <div className="history-title-row">
                            <strong>第 {item.question_number} 题</strong>
                            <span className="history-file-name">{item.file_name}</span>
                            <span className="mini-badge muted">已作答 {item.attempt_count || 0} 次</span>
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
                          <p><strong>解析：</strong>{item.explanation || '暂无解析'}</p>
                          <div className="history-option-list">
                            {item.options.map((option) => (
                              <div key={`${item.question_id}-${option.label}`} className="history-option-item">
                                <span className="option-label">{option.label}</span>
                                <span>{option.content}</span>
                              </div>
                            ))}
                          </div>
                          <button
                            type="button"
                            className="secondary-button history-ai-button"
                            onClick={() => handleHistoryAIExplanation(item.question_id)}
                            disabled={loadingHistoryAI}
                          >
                            {loadingHistoryAI ? 'AI 解析生成中...' : 'AI 解析'}
                          </button>
                          {(historyAI || loadingHistoryAI) ? (
                            <div className="ai-box markdown-body">
                              <strong>AI 解析</strong>
                              <ReactMarkdown>{historyAI || 'AI 正在生成解析，请稍候...'}</ReactMarkdown>
                            </div>
                          ) : null}
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
        ) : null}

        {activeView === 'records' ? (
          <section className="card">
            <div className="section-header history-header">
              <div>
                <h2>练习记录</h2>
                {renderPracticeRecordSummaryBadges()}
              </div>
            </div>
            {recordBuckets.length ? (
              <div className="record-bucket-list">
                {recordBuckets.map((bucket) => (
                  <div key={bucket.bucket_start} className="record-bucket-item">
                    <div className="record-bucket-header">
                      <strong>{formatDateTime(bucket.bucket_start)}</strong>
                      <span>
                        练习 {bucket.attempt_count} 题 · 正确 {bucket.correct_count} · 错误 {bucket.wrong_count}
                      </span>
                    </div>
                    <div className="record-bucket-entries">
                      {bucket.items.map((item) => (
                        <div key={item.attempt_id} className="record-entry-item">
                          <div>
                            <strong>第 {item.question_number} 题</strong>
                            <p className="history-meta">{item.file_name} · {formatDateTime(item.answered_at)}</p>
                            <p className="history-preview expanded">{item.stem}</p>
                          </div>
                          <span className={`status-badge ${item.is_correct ? 'success' : 'failed'}`}>
                            {item.is_correct ? '正确' : '错误'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-text">还没有练习记录。</p>
            )}
          </section>
        ) : null}

        {activeView === 'analysis' ? (
          <section className="card">
            <div className="section-header history-header">
              <div>
                <h2>薄弱点分析</h2>
                <span className="section-subtitle">基于当前范围内的错题记录和错误选项模式生成专项建议</span>
                {loadingWeaknessAnalysis ? (
                  <span className="section-subtitle">分析中...</span>
                ) : (
                  <div className="summary-badge-row">
                    <span className="mini-badge failed">错误次数 {weaknessAnalysis.wrong_attempt_count || 0}</span>
                    <span className="mini-badge muted">错题数量 {weaknessAnalysis.wrong_question_count || 0}</span>
                  </div>
                )}
              </div>
              <div className="analysis-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => refreshWeaknessAnalysis(currentScopeQuery).catch((err) => setError(err.message))}
                  disabled={loadingWeaknessAnalysis}
                >
                  {loadingWeaknessAnalysis ? '分析中...' : '刷新分析'}
                </button>
                <button
                  type="button"
                  className="primary-button"
                  onClick={handleGenerateWeaknessRecommendation}
                  disabled={loadingWeaknessRecommendation || loadingWeaknessAnalysis || !weaknessAnalysis.wrong_attempt_count}
                >
                  {loadingWeaknessRecommendation ? 'AI 生成中...' : '生成 AI 学习建议'}
                </button>
              </div>
            </div>

            {!loadingWeaknessAnalysis && !weaknessAnalysis.wrong_attempt_count ? (
              <p className="empty-text">当前范围下还没有错题，先做题后再来查看薄弱点分析。</p>
            ) : null}

            {weaknessAnalysis.top_subjects?.length ? (
              <div className="analysis-grid">
                <div className="analysis-panel">
                  <h3>高频薄弱主题</h3>
                  <div className="analysis-list">
                    {weaknessAnalysis.top_subjects.map((item) => (
                      <div key={item.label} className="analysis-list-item">
                        <strong>{item.label}</strong>
                        <span>错误 {item.wrong_count} 次 · 涉及 {item.question_count} 题</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="analysis-panel">
                  <h3>高频误选模式</h3>
                  <div className="analysis-list">
                    {weaknessAnalysis.top_confusion_pairs?.length ? weaknessAnalysis.top_confusion_pairs.map((item) => (
                      <div key={`${item.selected_answer}-${item.correct_answer}`} className="analysis-list-item">
                        <strong>{item.selected_answer} → {item.correct_answer}</strong>
                        <span>出现 {item.wrong_count} 次</span>
                      </div>
                    )) : <p className="empty-text">暂未发现明显的固定误选模式。</p>}
                  </div>
                </div>
              </div>
            ) : null}

            {weaknessAnalysis.repeated_wrong_questions?.length ? (
              <div className="analysis-panel">
                <h3>代表性错题</h3>
                <div className="analysis-list">
                  {weaknessAnalysis.repeated_wrong_questions.map((item) => (
                    <div key={item.question_id} className="analysis-question-card">
                      <div className="history-title-row">
                        <strong>第 {item.question_number} 题</strong>
                        <span className="history-file-name">{item.file_name}</span>
                        <span className="mini-badge failed">错 {item.wrong_count || 0} 次</span>
                      </div>
                      <p className="history-preview expanded">{item.stem}</p>
                      <p className="history-meta">
                        你的答案 {item.selected_answer} · 正确答案 {item.correct_answer}
                        {item.subject ? ` · ${item.subject}` : ''}
                        {item.year ? ` · ${item.year}` : ''}
                      </p>
                      <p className="history-meta">解析：{item.explanation || '暂无解析'}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {weaknessRecommendation || loadingWeaknessRecommendation ? (
              <div className="ai-box markdown-body analysis-ai-box">
                <strong>AI 学习建议</strong>
                {loadingWeaknessRecommendation ? (
                  <p>AI 正在根据你的错题模式生成专项学习建议，请稍候...</p>
                ) : (
                  <>
                    {weaknessRecommendation?.summary ? <p>{weaknessRecommendation.summary}</p> : null}
                    {weaknessRecommendation?.weak_points?.length ? (
                      <>
                        <h3>重点薄弱点</h3>
                        <ul>
                          {weaknessRecommendation.weak_points.map((item, index) => (
                            <li key={`${item.title}-${index}`}>
                              <strong>{item.title}</strong>（{item.priority}）- {item.reason}
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    {weaknessRecommendation?.confusion_advice?.length ? (
                      <>
                        <h3>误选纠偏建议</h3>
                        <ul>
                          {weaknessRecommendation.confusion_advice.map((item, index) => (
                            <li key={`${item.pattern}-${index}`}>
                              <strong>{item.pattern}</strong>：{item.reason}；建议：{item.advice}
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                    {weaknessRecommendation?.study_plan?.length ? (
                      <>
                        <h3>专项学习步骤</h3>
                        <ol>
                          {weaknessRecommendation.study_plan.map((item) => (
                            <li key={`${item.step}-${item.action}`}>
                              <strong>{item.action}</strong>：{item.goal}
                            </li>
                          ))}
                        </ol>
                      </>
                    ) : null}
                    {weaknessRecommendation?.next_action ? (
                      <p><strong>下一步：</strong>{weaknessRecommendation.next_action}</p>
                    ) : null}
                  </>
                )}
              </div>
            ) : null}
          </section>
        ) : null}
      </div>
    </main>
  )
}
