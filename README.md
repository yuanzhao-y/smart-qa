# Smart QA - 智能文档问答系统

基于 RAG（检索增强生成）的智能问答系统，集成答案评估、文档摘要等高级功能。

## 功能特性

### 核心 RAG
- 支持 PDF（含扫描件 OCR）、DOCX（含文本框/表格）、TXT、Markdown 文档上传
- 混合检索：向量语义检索 + BM25 关键词检索 + RRF 融合 + CrossEncoder 重排序
- HyDE 查询改写（简单问题自动跳过）
- 大模型流式回答并附带来源引用
- 多轮对话 + 会话管理（历史记录持久化）

### 高级功能
- **文档智能摘要**：上传时自动生成摘要、关键词、文档类型分类
- **引用高亮定位**：回答中的来源引用可点击，直接跳转到对应知识库片段
- **答案质量评估**：LLM-as-Judge 自动评分（忠实度/相关性/完整性）+ 用户反馈
- **多轮对话压缩**：超 10 轮对话自动压缩历史为摘要，降低 token 消耗
- **自适应切片**：可选语义切片策略，基于 embedding 相似度找自然断点

### 前端
- 仿 DeepSeek 风格现代聊天界面
- 知识库片段可视化查看
- 文件去重上传，删除同步清除所有关联数据

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python + FastAPI |
| 前端 | 原生 HTML/CSS/JS |
| 向量数据库 | ChromaDB |
| Embedding | paraphrase-multilingual-MiniLM-L12-v2 |
| BM25 检索 | rank-bm25 + jieba |
| Rerank | BAAI/bge-reranker-base |
| OCR | PaddleOCR（扫描件 PDF 自动识别） |
| LLM | OpenAI 兼容 API（DeepSeek / Qwen / Claude 等） |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

### 3. 启动后端

```bash
python run_backend.py
```

首次运行会自动下载 Embedding 模型和 Reranker 模型。

### 4. 启动前端（新终端）

```bash
python run_frontend.py
```

浏览器打开 http://localhost:8501 即可使用。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload` | 上传文档并索引（含摘要） |
| POST | `/chat` | 问答（支持 stream 流式） |
| POST | `/evaluate` | 评估答案质量 |
| POST | `/feedback` | 提交用户反馈 |
| GET | `/stats` | 知识库片段数 |
| GET | `/chunks?source=xxx` | 知识库片段列表（支持来源过滤） |
| GET | `/documents` | 已上传文档列表（含摘要预览） |
| GET | `/documents/{file_id}/summary` | 文档摘要详情 |
| DELETE | `/documents/{file_id}` | 删除文档及所有关联数据 |
| POST | `/sessions` | 创建会话 |
| GET | `/sessions` | 会话列表 |
| GET | `/sessions/{id}` | 加载会话 |
| PUT | `/sessions/{id}` | 更新会话 |
| DELETE | `/sessions/{id}` | 删除会话 |
| GET | `/health` | 健康检查 |

## 项目结构

```
smart-qa/
├── backend/
│   ├── main.py              # FastAPI 主应用
│   ├── config.py            # 配置管理
│   ├── document_loader.py   # 文档解析（PDF/DOCX/TXT/MD + OCR）
│   ├── text_splitter.py     # 固定切片
│   ├── semantic_splitter.py # 语义切片
│   ├── vector_store.py      # ChromaDB + 混合检索 + Rerank
│   ├── bm25_search.py       # BM25 关键词检索
│   ├── query_rewriter.py    # HyDE 查询改写
│   ├── reranker.py          # CrossEncoder 重排序
│   ├── llm.py               # LLM 调用
│   ├── summarizer.py        # 文档智能摘要
│   ├── evaluator.py         # 答案质量评估
│   ├── compressor.py        # 对话历史压缩
│   └── logger.py            # 日志配置
├── frontend/
│   ├── index.html           # 主页面
│   └── static/
│       ├── css/style.css    # 样式
│       └── js/app.js        # 交互逻辑
├── data/
│   ├── uploads/             # 上传文件
│   ├── chroma/              # ChromaDB 数据
│   ├── sessions/            # 会话记录
│   ├── summaries/           # 文档摘要
│   └── logs/                # 日志
├── 开发日志/                 # 版本迭代记录
├── requirements.txt
├── run_backend.py
└── run_frontend.py
```

## 配置项（.env）

```env
# LLM API
LLM_API_KEY=你的 API Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-flash

# Embedding 模型（可选）
# EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# Reranker（可选）
# ENABLE_RERANK=true
# RERANKER_MODEL=BAAI/bge-reranker-base
# RERANK_TOP_N=5

# 切片策略（可选）
# CHUNK_SIZE=500
# CHUNK_STRATEGY=fixed   # fixed 或 semantic
```

## 注意事项

- `.env` 包含 API Key，已在 `.gitignore` 中，切勿提交
- 首次运行需联网下载模型
- 扫描件 PDF 首次 OCR 会自动下载 PaddleOCR 模型（约 100MB）
- 删除 `data/chroma/` 可清空知识库（需先停后端）
- 日志文件在 `data/logs/smartqa.log`
