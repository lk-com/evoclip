# EvoClip

EvoClip 是一个基于 Agent + MCP + Skill 的视频生产系统，核心能力包括：

- `video-analysis`：视频关键帧与语音内容分析
- `copy-generation`：根据素材场景和商品信息生成文案
- `voice-synthesis`：将文案转为语音音频片段
- `video-render`：视频裁剪、合轨与拼接
- `quality-evaluation`：质量评估（同步/画面/违禁词）
- `skill-optimization`：基于诊断结果进行优化建议与应用

## 1. 环境要求

- Python 3.11+
- Node.js 20+
- FFmpeg / FFprobe
- PostgreSQL 15+
- Redis 7+
- MinIO
- (可选) supervisord + Nginx

## 2. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

cd web
npm install
cd ..
```

## 3. 配置 API 密钥（推荐私有配置文件）

先复制模板配置：

```bash
cp config/config.template.yaml config/config.local.yaml
export EVOCLIP_CONFIG_PATH=config/config.local.yaml
```

再编辑 `config/config.local.yaml` 并填写：

```yaml
credentials:
  # DashScope（阿里云）用于视觉/语音识别
  dashscope_api_key: "your-dashscope-key"
  dashscope_base_url: "https://dashscope.aliyuncs.com/api/v1"

  # LongCat 用于对话型 LLM 调用
  llm_api_key: "your-longcat-key"
  llm_base_url: "https://api.longcat.chat/openai/v1"

  # DashScope 嵌入（OpenAI 兼容端点）
  embedding_api_key: "your-dashscope-key"
  embedding_base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"

  # 可选 OpenAI TTS，仅在 tts.provider=openai 时需要
  openai_api_key: ""
  openai_base_url: "https://api.openai.com/v1"
```

`config/config.local.yaml` 中的推荐模型选择：

```yaml
vision:
  provider: dashscope
  model: qwen-vl-max-latest

llm:
  provider: openai
  model: LongCat-Flash-Chat

tts:
  provider: dashscope_clone
  dashscope_model: cosyvoice-v3-plus
  dashscope_voice: longxiaochun_v2
  # 可选固定克隆音色 ID；如果设置，运行时跳过克隆
  dashscope_voice_id: ""
  # 从上传的源视频自动克隆
  clone_from_video: true
  clone_public_base_url: "https://your-public-minio-domain"
```

注意：DashScope 语音克隆需要可公开访问的样本音频 URL。
当 MinIO 端点是本地（`localhost`）时，将 `tts.clone_public_base_url` 设置为外部域名或直接提供 `tts.clone_audio_url`。

安全建议：

- `config/config.template.yaml` 可提交到 GitHub。
- `config/config.local.yaml` 存放真实密钥，已被 `.gitignore` 忽略。
- 提交前可执行 `rg -n \"(sk-|ak_|api_key: \\\".+\\\")\" config` 自检敏感信息。

## 4. 初始化基础设施

```bash
python scripts/init_db.py --create-database
python scripts/init_storage.py
python scripts/init_redis.py
```

## 5. 启动服务

### 选项 A：使用 supervisord 运行

```bash
mkdir -p logs
supervisord -c supervisord.conf
```

### 选项 B：手动运行

```bash
python -m agent.main_agent
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

在另一个 shell 中：

```bash
cd web
npm run dev
```

## 6. 运行测试

```bash
pytest
```

生成本地 <= 30 秒的测试视频：

```bash
./scripts/generate_fixture_video.sh
```

运行端到端测试（需要运行中的 API/工作线程栈）：

```bash
EVOCLIP_E2E=1 ./scripts/run_e2e.sh
```
