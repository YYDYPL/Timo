# Timo 面试背题工具

一个本地运行的面试题复习工具，包含题库管理、SM-2 间隔重复、项目追问生成、AI 回答评估和学习统计。除两项 AI 功能外，所有能力都不依赖外部服务。

## 启动

```powershell
python -m pip install -r requirements.txt
python backend/seed.py
python -m uvicorn backend.main:app --reload
```

浏览器打开 `http://127.0.0.1:8000`。

初次启动时应用也会自动初始化 SQLite，并在空题库中写入 25 道内置题目。数据库保存在 `backend/data.db`。

## 配置 LLM

复制 `.env.example` 为 `.env`，填写 OpenAI 兼容服务：

```dotenv
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://your-provider.example/v1
LLM_MODEL=your-model-name
```

- OpenAI：可留空 `LLM_BASE_URL`，填写 API Key 和模型名。
- DeepSeek、智谱 GLM：填写服务商提供的兼容地址、Key 和模型名。
- Ollama 等本地服务：填写本地兼容地址和模型名；不要求真实 Key。

未配置 LLM 时，题库、复习、项目管理和统计仍可正常使用。

## 数据与复习规则

- 新题默认当天进入复习队列。
- 评分支持 `重来(1)`、`困难(3)`、`良好(4)`、`简单(5)`。
- 成功回忆按 `1 天 -> 6 天 -> 上次间隔 × 熟练度` 推进。
- `重来` 会重置连续记忆次数，并在当前复习会话中再次出现。
- 删除题目时会级联删除它的复习状态和历史记录。

## API

FastAPI 的交互式文档位于 `http://127.0.0.1:8000/docs`。

