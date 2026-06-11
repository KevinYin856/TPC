# README Requirement Audit Matrix

> 对照 README.md 总体流程与 TASK_PLAN_TRAVEL_PLANNER.md 细节要求，逐项审计。
> Status: **done** / **partial** / **fallback** / **missing**。
> 决不夸大；已是 fallback 的标注 fallback。
>
> **审计层次**（自 Phase 1 review 引入）:
> - *结构存在* — dataclass / 函数 / 模块已定义，但不一定被下游消费
> - *下游消费* — 结果被 planner / candidate / repair 实际使用
> - *eval 验证* — 官方 eval_tpc.py 端到端评分通过
>
> 标注"done"需要三层全部满足；仅结构存在标"partial"。

## 0. 总流程对齐

README 定义的总流程:

```
用户自然语言需求
  → 约束卡片抽取
  → 主动约束获取（风险驱动）
  → 语义落地与偏好权重
  → 候选池构建
  → [多策略] 多日任务分配 → 滚动逐日规划 → 日内路线优化
  → 时间表生成 → 预算控制 → 本地检查
  → 官方格式 → 官方 verifier → 类型化修复
  → 多候选择优 → 最终输出
```

| Step | Requirement | Status | Module | Evidence | Test coverage | Next action |
|------|-------------|--------|--------|----------|---------------|-------------|
| 1 | 用户自然语言需求 → Query 标准化 | done | `src/data_layer/loaders.py` | `query_from_dict()` 兼容 uid/nature_language 等多种字段 | `test_data_layer.py` 有泛型+真实 data 测试 | — |
| 2 | 约束卡片抽取 | partial | `src/constraints/` | `constraint_parser.py` + `nl_parser.py` + `hard_logic_parser.py` 三路解析。NL 词典已扩展但覆盖不完整 | `test_constraints.py` 依赖 training data | 扩展词典到 lexicons/ 目录，补 ≥30 条 NL unit test |
| 3 | 主动约束获取（风险驱动） | **partial** | `src/active/` | Phase 1: `active_constraint_mapping.py` 新增 belief/action/info_gain/query_cost/selection/explanation/update 7 步框架。`active_query_selector.py` 已委托到 ACM。action_results 部分消费：酒店可用，POI/餐厅仍 fallback。*结构存在，下游部分消费* | `test_active.py` 3/3 通过 | 将 action_results 全面写入 fetched_data；candidates 优先消费 action 结果 |
| 4 | 语义落地与偏好权重 | partial | `src/semantic/semantic_grounder.py` | 将约束卡片转为 `GroundedPreferences`，含 poi_weights/cuisine_weights/pace_weight | 无独立测试 | 需要针对多组约束卡片验证权重映射正确性 |
| 5 | 候选池构建 | partial | `src/candidates/` | `candidate_generator.py` + poi/hotel/restaurant ranker 已引入 forbidden type 硬过滤和 must_visit 置顶 | `test_candidates.py` 有 | 酒店排序的 rooms×nights 计算需验证与官方 verifier 一致 |
| 6 | 多策略多日任务分配 | fallback | `src/planner/poi_task_assignment.py` | 按 policy 分配每日 capacity（safe=2, preference=4），must_visit 前置。但分配是一次性的，不是逐日滚动 | 无独立测试 | 需改为逐日 state-aware 分配 |
| 7 | 滚动逐日规划 | fallback | `src/planner/rolling_day_planner.py` + `plan_builder.py` | `rolling_horizon_plan()` 创建 PlanState 但 `build_full_plan_dict()` 预先分配所有天 POI，不是真正的滚动重决策 | 无独立测试 | 改为真正的 MPC loop：每天构建后更新 state，从剩余候选池选 POI |
| 8 | 日内路线优化 | fallback | `src/optimizer/day_route_optimizer.py` | Greedy + 2-opt 优化 attraction 顺序。距离优先 WorldEnv → Haversine → 3km fallback。不考虑开放时间/疲劳 | 无独立测试 | **Phase 1 Task 4**：定义 GA-TSP 接口；后续引入 opening_hours/fatigue penalty |
| 9 | 时间表生成 | partial | `src/planner/plan_builder.py` | `build_day_activities()` 依次排餐食/景点/住宿/城际交通，满足时间单调性。meal 固定 slot（7:30/11:30/17:30） | 集成于 pipeline 测试 | meal slot 过于刚性，需要可配置 |
| 10 | 预算控制 | fallback | `src/scheduler/budget_controller.py` | 替换低价餐厅/酒店、taxi→metro、删非必去景点。但有预算超标时只删最后一天的景点，不够智能 | 无独立测试 | 改为按优先级逐级降成本 |
| 11 | 本地轻量检查 | partial | `src/verifier/local_checker.py` | 检查 FORMAT/TIME/TICKET/MEAL/MUST_VISIT/BUDGET。缺少 OPENING_HOURS/TRANSPORT 完整性/重复 POI | 无独立测试 | 补 OPENING_HOURS/TRANSPORT contiguity/duplicate 检查 |
| 12 | 官方格式 | done | `src/submission/submission_writer.py` + `src/adapter/plan_formatter.py` | `render_to_official_format()` + `format_official_plan()` 输出含 people_number/start_city/target_city/itinerary。已剥离 _internal 调试字段 | `test_adapter.py` 有空/列表两种格式测试 | — |
| 13-14 | 官方 verifier + 类型化修复 | fallback | `src/verifier/` + `src/repair/typed_repair.py` | 有 error_parser 和 typed_repair 分派 FORMAT/TICKET/TRANSPORT/BUDGET/TIME/MEAL/MUST_VISIT/OPENING_HOURS。但 repair 是纯字段补全，不查询 WorldEnv | 无独立测试 | 注入 SandboxClient 做基于数据的 repair；每类错误至少一个红绿测试 |
| 15 | 多候选择优 | partial | `main.py` | 跑 5 个 policy，取 verifier score 最高者 | 集成于 pipeline | 需多策略批量对照实验 |

---

## 1. NLP / Constraint Parser

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| 规则/词典式 NL 解析 | partial | `src/constraints/nl_parser.py` | 覆盖 budget/pace/forbidden type/must visit type/hotel distance/dining 等短语 | `test_constraints.py` 依赖真实 query | 抽取词典到 `lexicons/`，补 unit test |
| hard_logic DSL 解析 | partial | `src/constraints/hard_logic_parser.py` | 支持 budget/distance/hotel type/attraction type name/total_cost 等 snippet | 无独立测试（正式模式禁止用 hard_logic_py） | debug 模式下验证解析正确性 |
| 模糊约束精确定义 | fallback | `nl_parser.py` | "not too tired"→pace relaxed，"as many as possible"→capacity boost，"do not visit X"→forbidden type | 无 | 建立 mapping 词典并补测试 |
| 中英文同义词 | fallback | `nl_parser.py` 内联 ATTRACTION_TYPE_TERMS / CUISINE_TERMS | 仅覆盖常见类型 | 无 | 拆分词典文件 |
| 小型离线模型预留 | missing | — | 无 LocalIntentParser 接口，无 sentence-transformers 接入 | 无 | 设计接口，默认仍走 rule parser |

---

## 2. Active Constraint Mapping (Active SLAM)

> Phase 1 新增 `src/active/active_constraint_mapping.py`，7 步框架结构存在。
> `active_query_selector.py` 已委托到 ACM。**但 selected action 结果尚未被 candidates 优先消费；全量数据拉取仍无条件执行。** 标为 partial。

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| 风险评估 | partial | `src/active/constraint_risk_estimator.py` | 风险 = 不确定性 × 严重程度 + 硬约束加成 | `test_active.py` | 加入历史 verifier failure 维度 |
| 不确定性分析 | partial | `src/active/uncertainty_analyzer.py` | 按类别评估信息不完整度 | `test_active.py` | — |
| Belief state | **partial** | `active_constraint_mapping.py:init_beliefs()` | `ConstraintBelief` 含 resolved/confidence/missing_data/risk_level | `test_active.py` smoke | candidates 应读取 belief state 决定查什么 |
| Active action 生成 | **partial** | `active_constraint_mapping.py:generate_candidate_actions()` | 生成 `ActiveAction`，含 tool_name/params/target_category | `test_active.py` smoke | `_execute_action` 应应用 params 过滤而非调用无过滤的 list_* |
| Information gain | **partial** | `active_constraint_mapping.py:estimate_info_gain()` | uncertainty × severity × coverage | 无独立测试 | 与 eval 结果对比校准 |
| Query cost | **partial** | `active_constraint_mapping.py:estimate_query_cost()` | 基础查询时间 + topk 惩罚 | 无独立测试 | 实测各 tool 延迟，校准 cost 表 |
| Action selection | **partial** | `active_constraint_mapping.py:select_actions()` | priority = info_gain / (cost + ε)，阈值 0.03 | `test_active.py` 3/3 通过 | 验收不应只看 action 数量，需看实际数据访问量 |
| Query explanation | **partial** | `active_constraint_mapping.py:explain_selection()` | 生成选中/拒绝/未覆盖维度的解释文本 | 无独立测试 | — |
| Belief update | **partial** | `active_constraint_mapping.py:update_beliefs()` | 查询后提 confidence、清 missing_data、标记 resolved | 无独立测试 | — |
| 结构化工具调用 | **partial** | `active_query_selector.py:_execute_action()` | 映射到 agent_env tool（goto/intercity/accommodations_nearby 等）。**select 类工具当前未应用 key/op/value 过滤** | 无独立测试 | 应用 params 过滤；CSV fallback 也转成过滤条件 |

---

## 3. Semantic Grounder

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| POI 偏好权重 | done | `src/semantic/semantic_grounder.py` | 从 constraints + active_info 构建 poi_weights | 无独立测试 | 补测试 |
| Cuisine 权重 | done | `semantic_grounder.py` | cuisine_weights 从 dietary/cuisine 卡片推导 | 无 | 补测试 |
| Pace/transport/budget 权重 | partial | `semantic_grounder.py` | pace_weight/transport_weight/budget_weight 从 constraints 推导 | 无 | 校准默认权重 |

---

## 4. Candidate Pool Construction

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| POI 候选排序 | partial | `src/candidates/poi_ranker.py` | 偏好权重 + MMR 多样性 + forbidden type 硬过滤 + must_visit 置顶 | `test_candidates.py` | 验证 forbidden type 匹配覆盖所有 ChinaTravel 景点类型标签 |
| 酒店候选排序 | partial | `src/candidates/hotel_ranker.py` | rooms×nights 总价 + anchor 距离 + required type 过滤 | `test_candidates.py` | 验证 featureHotelType 标签匹配覆盖 CSV 字段 |
| 餐厅候选排序 | partial | `src/candidates/restaurant_ranker.py` | cuisine 偏好 + per-meal 预算 + required/forbidden cuisine 过滤 | `test_candidates.py` | 验证 cuisine 标签匹配覆盖中英文 |
| 候选池构建 | done | `src/candidates/candidate_generator.py` | 汇总 POI/酒店/餐厅/交通候选 | — | — |

---

## 5. Planner

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| 多日 POI 分配 | fallback | `src/planner/poi_task_assignment.py` | policy-aware capacity，must_visit 优先，budget 模式 prefer 低价 | 无独立测试 | 改为 state-aware 逐日分配 |
| 滚动逐日规划 | fallback | `src/planner/rolling_day_planner.py` + `plan_builder.py` | 有 PlanState schema，但不逐日重决策 | 无 | MPC loop 重构 |
| 城际交通 | partial | `plan_builder.py` | `select_intercity()` 查 WorldEnv/fallback | 无 | fallback 交通 ID 格式需验证通过官方 verifier |
| 市内交通 (goto) | partial | `plan_builder.py` + `world_env_client.py` | `SandboxClient.goto()` → WorldEnv transport.goto → walk fallback | 无 | annotate_transports 需验证 tickets/cars 字段 |
| 餐食插入 | partial | `plan_builder.py` | 每天 breakfast/lunch/dinner 固定 slot；首日可能 skip breakfast | 无 | slot 可配置化 |

---

## 6. Day Route Optimizer

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| Greedy initial route | done | `src/optimizer/nearest_neighbor.py` | 最近邻构建初始路线 | 无独立测试 | — |
| 2-opt local search | done | `src/optimizer/two_opt.py` | 2-opt 迭代优化 | 无独立测试 | — |
| Route scoring | done | `src/optimizer/route_score.py` | 路线总成本/时间计算 | 无 | — |
| ACO 蚁群算法 | fallback | `src/optimizer/ant_colony.py` | ACO 实现存在于代码中，但 <10 POI 自动退化为 NN+2-opt，不作为主优化器 | 无 | 验证 ACO 在 10+ POI 场景下的收敛质量 |
| 开放时间约束 | missing | — | 优化不考虑景点开放时间 | 无 | **Phase 1 Task 4** 预留接口 |
| 疲劳惩罚 | missing | — | 优化不考虑疲劳累积 | 无 | **Phase 1 Task 4** 预留接口 |
| GA-TSP 接口 | missing | — | 无遗传算法接口 | 无 | **Phase 1 Task 4** 定义接口 |

---

## 7. Scheduler / Budget Controller

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| 预算控制 | fallback | `src/scheduler/budget_controller.py` | 替换低价餐厅→酒店→taxi→metro→删非必去景点 | 无 | 改为分级降成本策略 |
| 时间表生成 | partial | `plan_builder.py` | 逐 activity 排时间，保证单调递增 | 无 | — |
| ResourceState 统一 | missing | — | 无统一 ResourceState（budget/dining/accommodation/fatigue） | 无 | 设计 ResourceState dataclass |

---

## 8. Verifier / Repair

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| 本地检查 | partial | `src/verifier/local_checker.py` | 7 类检查，缺 OPENING_HOURS/TRANSPORT contiguity/duplicate | 无 | 补缺失检查项 |
| 错误解析 | partial | `src/verifier/error_parser.py` | 按关键字分类错误类型 | 无 | 验证与官方 verifier 输出格式完全匹配 |
| 类型化修复 | fallback | `src/repair/typed_repair.py` | 8 类错误分派，但都是字段填充/覆盖，不查询 WorldEnv | 无 | 注入 SandboxClient 做基于数据的 repair |
| Repair 迭代闭环 | fallback | `main.py:_repair_loop()` | 循环调用 verifier→repair，但 repair 幂等时无收敛检测 | 无 | 增加收敛检测 + 最多 N 轮 |
| 每类错误红绿测试 | missing | — | 无 | 无 | 建立 typed repair 独立测试 |

---

## 9. Official Format / Submission

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| 输出 schema 合规 | done | `src/submission/format_checker.py` + `submission_writer.py` | 校验顶层字段/activity 字段/transports 字段 | `test_adapter.py` | — |
| 调试字段不泄漏 | done | `plan_formatter.py` | 已移除 `_internal_score`/`_internal_query_id`/`_traceback` | observed in diff | — |
| 空 plan 兜底 | done | `runner.py` | 异常时返回含 error 字段但 schema 完整的空 plan | `test_adapter.py` | — |

---

## 10. Multi-Strategy / Experiment

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| 5 种 policy | partial | `main.py` | safe/budget/preference/low_transport/must_visit_first | 集成测试 | policy 间的差异度尚不显著 |
| 批量对照实验 | missing | — | 无批量指标输出（success rate/verifier score/cost/transport time 等） | 无 | 建立实验框架 |
| 实验日志 | partial | `src/experiments/experiment_logger.py` | `save_logs()` 写入 query/constraints/best_plan/score/all_results | 无 | 增加指标维度 |

---

## 11. Data Layer

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| Query 加载 | done | `src/data_layer/loaders.py` | JSON/CSV 双格式，兼容多种字段名 | `test_data_layer.py` | — |
| POI 数据库 | partial | `src/data_layer/database.py` | TravelDatabase: JSON sandbox + CSV bridge | `test_data_layer.py` | 字段 normalize 统一 |
| WorldEnv 客户端 | partial | `src/data_layer/world_env_client.py` | SandboxClient: WorldEnv → CSV → JSON fallback | 无独立测试 | **Phase 1 Task 2**：加 agent_env 后端 |
| 交通矩阵 | fallback | `database.py:get_transport_matrix()` | 无预计算矩阵时用 Haversine 估算，25km/h 假设 | `test_data_layer.py` | 用 WorldEnv goto 替代估算 |
| 字段 normalize | missing | — | price/lat/lng/type 字段名在各模块各自 fuzzy lookup | 无 | 建立统一 normalize 函数 |

---

## 12. Agent Env Integration

> Phase 1: `world_env_client.py` 新增 `AgentEnvBackend`；`SandboxClient` 支持 agent_env→direct→csv 三层后端；`config.yaml` 新增 `world_env.backend` / `agent_env_cwd`。
> `auto` 模式正确解析到 `agent_env`；direct/csv 基础 fallback smoke 通过。
> **但还缺**：官方 eval 端到端验证；`poi_lat_lon` 在 direct/csv 后端的坐标 fallback。

| Requirement | Status | Module | Evidence | Test coverage | Next action |
|-------------|--------|--------|----------|---------------|-------------|
| agent_env 后端 | **partial** | `src/data_layer/world_env_client.py` | `AgentEnvBackend` 封装 12 个 structured tools + normalize；`SandboxClient` 后端优先级 `auto→agent_env→direct→csv`；smoke 通过但缺完整 eval。public easy 被 hard_logic_py 阻塞；local smoke split 可完整跑但分数低 | 手动 smoke 通过；缺异常路径测试 | 官方 eval 端到端验证；补 poi_lat_lon direct/csv fallback |
| CLI/adapter smoke test | partial | TASK_PLAN §0 | `agent_env.cli tools` 和 `china_travel_list_splits` 已验证可调用 | 手动 | 自动化 smoke test |
| Tool output normalize | **partial** | `world_env_client.py` | `_normalize_goto_segments` / `_normalize_dataframe_rows` / `_normalize_intercity_row`；agent_env→direct→CSV 三条路径字段对齐 | 手动 smoke | 覆盖更多边界字段（restaurants 的 cuisine/hotel 的 featureHotelType） |

---

## 13. Readiness for Codex Audit

| Requirement | Status | Evidence |
|-------------|--------|----------|
| 可被 eval_tpc.py 读取 | **done** | `run_tpc.py --official-results` 直接写入 `ChinaTravel/results/{method}/`；`scripts/sync_results.py` 可同步历史结果。Phase 2 smoke runner 已验证 schema 对齐 |
| 正式模式禁止 hard_logic_py | done | `query_adapter.py` 剥离 ORACLE_FIELDS |
| 调试字段不进入提交 | done | `plan_formatter.py` + `submission_writer.py` 过滤 `_` 前缀字段；Phase 1 输出 JSON 检查无 `_internal`/`metadata`/`budget_report` 泄漏 |
| 输出目录可配置 | **done** | `run_tpc.py` 读取 `config.yaml` 的 `adapter.results_dir`（相对路径按 PROJECT_ROOT 解析），`--official-results` 直接写入 `ChinaTravel/results/{method}/` |

---

## Summary

| Total requirements | done | partial | fallback | missing |
|--------------------|------|---------|----------|---------|
| ~55 | 10 | 18 | 13 | ~6 |

**关键差距**（Phase 1 部分解决，**粗体** 为 Phase 1 引入但仍需后续完善）:

1. **agent_env 后端已接入但缺 eval 端到端验证** → Phase 1 Task 2 done，Phase 2 需要官方 split runner + eval
2. **Active Constraint Mapping 结构存在，但 action 结果未完全驱动 candidates** → Phase 1 Task 3 partial
3. **日内路线优化 GA-TSP 接口已定义，但 solver 仍为 greedy + 2-opt** → Phase 1 Task 4 (接口准备完成)
4. MPC 不是真正的 receding horizon
5. repair 不查询 WorldEnv / agent_env
6. NLP 仍为规则引擎，无离线模型
7. 无系统的回归测试集
8. 无批量多策略对照实验
9. eval_tpc.py public split 缺 hard_logic_py 字段阻塞完整评分；local split 可跑完整流程但分数低
10. **新增** `scripts/run_official_eval_smoke.py` 官方 smoke runner（limit/resume/schema 检查）
11. **新增** `scripts/sync_results.py` 结果同步脚本
12. **修复** 多日规划时间累积溢出导致三位数小时的 bug（plan_builder + plan_utils + format_checker 三层防护）
