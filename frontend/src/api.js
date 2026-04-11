const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || '请求失败')
  }

  return response.json()
}

export function fetchUploadedFiles() {
  return request('/files')
}

export function fetchRandomQuestion(sourceFile = 'all') {
  const query = sourceFile && sourceFile !== 'all'
    ? `?source_file=${encodeURIComponent(sourceFile)}`
    : ''
  return request(`/question/random${query}`)
}

export function fetchWrongAnswerHistory(sourceFile = 'all', { favoritesOnly = false } = {}) {
  const params = new URLSearchParams()
  if (sourceFile && sourceFile !== 'all') {
    params.set('source_file', sourceFile)
  }
  if (favoritesOnly) {
    params.set('favorites_only', 'true')
  }
  const query = params.toString() ? `?${params.toString()}` : ''
  return request(`/history/wrong-answers${query}`)
}

export function submitAnswer(questionId, answer) {
  return request('/answer', {
    method: 'POST',
    body: JSON.stringify({ question_id: questionId, answer }),
  })
}

export function updateWrongQuestionState(questionId, payload) {
  return request(`/question/${questionId}/wrong-state`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function importPdfs(files, { onProgress } = {}) {
  const formData = new FormData()
  files.forEach((file) => {
    formData.append('uploaded_files', file)
  })

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/import/pdf/batch`)
    xhr.responseType = 'json'

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || !onProgress) {
        return
      }
      onProgress(Math.round((event.loaded / event.total) * 100))
    }

    xhr.upload.onload = () => {
      if (onProgress) {
        onProgress(100)
      }
    }

    xhr.onload = () => {
      const payload = xhr.response || JSON.parse(xhr.responseText || '{}')
      if (xhr.status >= 200 && xhr.status < 300) {
        if (onProgress) {
          onProgress(100)
        }
        resolve(payload)
        return
      }
      reject(new Error(payload.detail || '导入失败'))
    }

    xhr.onerror = () => reject(new Error('导入失败'))
    xhr.send(formData)
  })
}

export async function streamAIExplanation(questionId, { onChunk, signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/question/${questionId}/ai-explanation/stream`, {
    method: 'POST',
    signal,
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || 'AI 讲解生成失败')
  }

  if (!response.body) {
    throw new Error('浏览器不支持流式读取')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    const chunk = decoder.decode(value, { stream: true })
    if (chunk && onChunk) {
      onChunk(chunk)
    }
  }
}
