## ADDED Requirements

### Requirement: 接受场景列表和商品描述生成分句文案
系统 SHALL 接受 `video-analysis` 输出的场景列表 JSON（含 `description`、`objects`、`transcription` 字段）和用户提供的商品描述文本，调用 LLM API 为每个场景生成对应的分句文案，文案须与场景内容语义匹配，并突出商品卖点。

#### Scenario: 正常生成文案
- **WHEN** 接收到有效的场景列表（≥1 条）和非空商品描述
- **THEN** 系统 SHALL 为每个 `scene_id` 生成至少一句文案，输出 JSON 数组

#### Scenario: 商品描述为空
- **WHEN** 用户提供的商品描述字符串为空或仅含空白字符
- **THEN** 系统 SHALL 返回错误 `"empty_product_description"`，不调用 LLM

---

### Requirement: 将素材标签和语音识别结果注入 Prompt
系统 SHALL 在调用 LLM 时，将每个场景的 `description`（场景描述）、`objects`（对象列表）和 `transcription`（语音识别结果）注入 Prompt 上下文，确保生成的文案与素材内容高度匹配。

#### Scenario: 素材标签完整注入
- **WHEN** 场景列表包含完整的 `description` 和 `objects` 字段
- **THEN** 系统 SHALL 将这些信息作为上下文注入 LLM Prompt，引导生成与场景内容匹配的文案

#### Scenario: 素材包含语音识别结果
- **WHEN** 场景的 `transcription` 字段非空
- **THEN** 系统 SHALL 将语音识别结果作为额外上下文注入 Prompt，帮助生成与素材语音内容相关的文案

#### Scenario: 素材缺少部分标签
- **WHEN** 某些场景缺少 `transcription` 或 `objects` 字段
- **THEN** 系统 SHALL 仅使用可用字段注入 Prompt，不报错

---

### Requirement: 每句文案绑定 scene_id 并估算时长
系统 SHALL 在输出的每条文案记录中包含 `sentence_id`（全局唯一，格式：`t_0`、`t_1` …）、`scene_id`（对应输入场景）、`text`（文案文本）、`estimated_duration_s`（预估朗读时长，单位秒，精度 0.1s），基于平均语速（3.5 字/秒）估算。

#### Scenario: 输出结构完整
- **WHEN** LLM 成功返回文案内容
- **THEN** 每条记录 SHALL 包含 `sentence_id`、`scene_id`、`text`、`estimated_duration_s` 四个字段，缺少任意字段视为无效输出

#### Scenario: scene_id 引用合法
- **WHEN** 文案生成完成
- **THEN** 所有记录的 `scene_id` SHALL 存在于输入的场景列表中，不得出现未定义的 `scene_id`

---

### Requirement: LLM API 调用失败时重试
系统 SHALL 在 LLM API 返回超时（>30s）或 5xx 错误时，以指数退避策略最多重试 3 次。

#### Scenario: LLM API 临时不可用后恢复
- **WHEN** LLM API 前两次返回 503，第三次成功
- **THEN** 系统 SHALL 正常返回文案结果，不向调用方暴露重试过程

#### Scenario: LLM API 三次重试全部失败
- **WHEN** LLM API 连续 3 次返回错误
- **THEN** 系统 SHALL 返回错误 `"llm_api_unavailable"` 并终止本次生成
