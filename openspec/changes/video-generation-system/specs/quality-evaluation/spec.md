## ADDED Requirements

### Requirement: 检测音画时间轴同步误差
系统 SHALL 读取 `timeline.json`，对每个非跳过的场景段计算音频时长与视频段时长的差值绝对值，若任意场景段的误差超过 200ms，则在诊断报告中标记为 `sync_error`。

#### Scenario: 所有场景同步误差在阈值内
- **WHEN** 所有场景段的音视频时长差值均 ≤ 200ms
- **THEN** 诊断报告中 `sync_errors` 字段 SHALL 为空数组

#### Scenario: 存在超阈值同步误差
- **WHEN** 某场景段音视频时长差值 > 200ms
- **THEN** 诊断报告 SHALL 在 `sync_errors` 中记录该 `scene_id`、`audio_duration_ms`、`video_duration_ms` 和 `delta_ms`

---

### Requirement: 检测黑屏和模糊帧
系统 SHALL 对生成的 MP4 视频按每秒 1 帧采样，使用亮度阈值（黑屏：平均亮度 < 10）和拉普拉斯方差阈值（模糊：方差 < 100）检测异常帧，将连续超过 500ms 的异常帧段记录为问题片段。

#### Scenario: 无异常帧
- **WHEN** 视频所有采样帧均通过亮度和清晰度检测
- **THEN** 诊断报告中 `visual_issues` 字段 SHALL 为空数组

#### Scenario: 检测到黑屏片段
- **WHEN** 视频中存在连续超过 500ms 的低亮度帧
- **THEN** 诊断报告 SHALL 在 `visual_issues` 中记录 `type: "black_screen"`、`start_ms`、`end_ms`

#### Scenario: 检测到模糊帧片段
- **WHEN** 视频中存在连续超过 500ms 的低方差帧
- **THEN** 诊断报告 SHALL 在 `visual_issues` 中记录 `type: "blur"`、`start_ms`、`end_ms`

---

### Requirement: 扫描文案违禁词
系统 SHALL 读取所有场景的 `subtitle_text`，对照内置违禁词词典（从配置文件加载），标记包含违禁词的句子。

#### Scenario: 文案无违禁词
- **WHEN** 所有场景字幕文本均未匹配违禁词词典
- **THEN** 诊断报告中 `prohibited_words` 字段 SHALL 为空数组

#### Scenario: 发现违禁词
- **WHEN** 某句字幕文本包含词典中的词汇
- **THEN** 诊断报告 SHALL 记录 `sentence_id`、`matched_words`（字符串数组）和 `text`

---

### Requirement: 输出结构化 diagnosis.json
系统 SHALL 将三项检测结果合并为 `diagnosis.json`，包含顶层字段：`overall_score`（0–100 整数，扣分规则：每个 sync_error -10 分，每个 visual_issue -15 分，每个 prohibited_word -20 分，下限为 0）、`sync_errors`、`visual_issues`、`prohibited_words`、`generated_at`（ISO8601 时间戳）。

#### Scenario: 诊断报告结构完整
- **WHEN** 三项检测均执行完毕
- **THEN** `diagnosis.json` SHALL 包含上述所有顶层字段，且 `overall_score` 在 0–100 范围内

#### Scenario: 评估输入文件不存在
- **WHEN** 指定的 `timeline.json` 或 MP4 文件在 MinIO 中不存在
- **THEN** 系统 SHALL 返回错误 `"input_not_found"` 并注明缺失的 MinIO 对象键
