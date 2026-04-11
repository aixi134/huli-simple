# 护理刷题系统

一个面向护理考试题库的本地刷题应用，支持 PDF 批量导入、随机做题、错题/收藏管理，以及 AI 讲解。

## 功能

- 多 PDF 批量导入
- 导入时显示上传进度、解析中、入库中状态
- 题目按文件范围或全部题库随机抽取
- 点击选项直接提交答案
- 错题历史、收藏、隐藏错题
- AI 流式讲解 Markdown
- Docker Compose 一键启动

## 项目结构

- `backend/`：FastAPI + SQLAlchemy + 解析服务
- `frontend/`：React + Vite 前端
- `scripts/`：PDF 解析和导入脚本
- `pdf/`：题库 PDF 源文件
- `data/`：数据库和解析产物

## 本地开发

### 后端

```bash
SSL_CERT_FILE=/etc/ssl/cert.pem python3 -m venv .venv
SSL_CERT_FILE=/etc/ssl/cert.pem .venv/bin/pip install -r backend/requirements.txt
PYTHONPATH=. .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### 前端

```bash
npm install --prefix frontend
npm run dev --prefix frontend
```

前端默认通过 `/api` 访问后端；Vite 开发环境会把 `/api` 代理到 `http://127.0.0.1:8000`。

## Docker Compose 启动

先复制环境变量：

```bash
cp .env.example .env
```

然后启动：

```bash
docker compose up --build -d
```

启动后访问：

- `http://localhost`

## 环境变量

根目录 `.env.example`：

- `QUIZ_LLM_BASE_URL`：本地 OpenAI 兼容模型地址
- `QUIZ_LLM_API_KEY`：本地模型鉴权 key
- `OPENAI_API_KEY`：备用 key
- `QUIZ_LLM_MODEL`：模型名
- `QUIZ_CORS_ORIGINS`：后端允许的来源

前端 `frontend/.env.example`：

- `VITE_API_BASE_URL=/api`

## 常用命令

### 构建前端

```bash
npm run build --prefix frontend
```

### 检查 Python 语法

```bash
python3 -m compileall backend scripts
```

### 解析单个 PDF

```bash
.venv/bin/python scripts/parse_pdf_to_json.py "pdf/你的文件.pdf"
```

## 数据说明

- `data/quiz.db`：SQLite 数据库
- `data/raw_pages/`：PDF 页面文本提取结果
- `data/parsed_questions/`：结构化题库 JSON
- `data/failed/`：失败或兜底过程产物
- `pdf/uploaded/`：通过网页导入后保存的 PDF

## 当前导入策略

- 题号不连续不会阻止上传
- 同一文件中的重复题号会自动跳过
- 单个题解析失败不会影响整批其他题/其他文件
- 重复导入同一文件时，会优先跳过已存在题目
