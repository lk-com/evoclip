## ADDED Requirements

### Requirement: 读取诊断报告并检索相似历史经验
系统 SHALL 读取 `quality-evaluation` 输出的 `diagnosis.json`，提取问题类型（`sync_error`、`visual_issue`、`prohibited_word`）和受影响的 Skill，使用嵌入模型将问题描述向量化，在向量数据库（ChromaDB）中检索最多 3 条语义相似的历史优化记录。

#### Scenario: 检索到相似历史经验
- **WHEN** 向量数据库中存在至少 1 条相似记录（余弦相似度 ≥ 0.75）
- **THEN** 系统 SHALL 将检索结果作为上下文传入优化 LLM，不重复生成已尝试过的优化方案

#### Scenario: 向量数据库为空（冷启动）
- **WHEN** ChromaDB 中无任何历史记录
- **THEN** 系统 SHALL 不做检索，直接使用内置默认 Prompt 模板生成优化建议

---

### Requirement: 生成针对问题 Skill 的优化建议
系统 SHALL 根据诊断报告和检索结果，调用 LLM 生成针对每个问题 Skill 的具体优化建议，建议内容包含：目标 Skill 名称、优化类型（`prompt_update` / `param_update`）、修改的参数键路径、新值或新 Prompt 片段、预期改善效果描述。

#### Scenario: sync_error 触发 VoiceSkill 优化
- **WHEN** `diagnosis.json` 中 `sync_errors` 非空
- **THEN** 系统 SHALL 生成至少一条针对 `voice-synthesis` 的优化建议，类型为 `param_update`（如调整语速参数）

#### Scenario: prohibited_word 触发 CopySkill 优化
- **WHEN** `diagnosis.json` 中 `prohibited_words` 非空
- **THEN** 系统 SHALL 生成至少一条针对 `copy-generation` 的优化建议，类型为 `prompt_update`（在 Prompt 中加入禁词规避指令）

#### Scenario: overall_score 满分时不生成优化建议
- **WHEN** `diagnosis.json` 中 `overall_score` 为 100
- **THEN** 系统 SHALL 返回空的优化建议列表，不调用 LLM

---

### Requirement: 更新 Skill 版本配置并写入 Memory Store
系统 SHALL 将通过人工确认（或自动应用模式下直接应用）的优化建议写入 PostgreSQL 版本表（记录 Skill 名称、参数/Prompt 变更内容、来源诊断报告 ID、应用时间戳），并将本次诊断问题和优化结果以向量形式写入 ChromaDB，供未来检索。

#### Scenario: 优化建议应用成功
- **WHEN** 用户确认或系统自动应用某条优化建议
- **THEN** PostgreSQL 版本表 SHALL 新增一条记录，ChromaDB 中 SHALL 新增对应的向量文档

#### Scenario: 应用优化建议失败时回滚
- **WHEN** 将优化建议写入 Skill 配置文件过程中发生 I/O 错误
- **THEN** 系统 SHALL 回滚到上一版本配置（从 PostgreSQL 版本表中读取），不留下中间状态

#### Scenario: 自动应用模式下 overall_score 低于阈值
- **WHEN** 自动应用模式开启且 `overall_score` < 60
- **THEN** 系统 SHALL 自动应用所有优化建议，无需人工确认
