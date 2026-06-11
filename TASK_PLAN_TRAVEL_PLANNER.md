# Demo1 Travel Planner Algorithm Task Plan

> 目标：把 `demo1` 从“可运行的精简规划器”继续推进为更符合 README / ChinaTravel 竞赛要求的旅行规划算法系统。重点不是只修字段，而是让自然语言理解、主动约束获取、候选生成、滚动规划、日内路线优化、预算控制、verifier repair 和多策略真正形成闭环。

## 0. 当前结论

当前实现已经具备较完整的算法骨架，但还不是最终版。

已完成或已有雏形：

- 本地规则/词典式自然语言解析，覆盖部分模糊表达、预算、酒店距离、禁止/偏好景点类型。
- Active query selector 会按风险选择关键查询，不再完全盲查。
- POI/酒店/餐厅候选排序已纳入预算、偏好、类型、距离等因素。
- 每日规划已从平均切分推进到按 policy 和剩余任务滚动分配。
- 日内路线有 greedy + 2-opt 优化，距离优先 WorldEnv，其次经纬度，再 fallback。
- budget controller 会替换低价餐厅/酒店、减少 taxi、必要时删非必去景点。
- typed repair 已按错误类型分派 FORMAT/TICKET/TRANSPORT/BUDGET/TIME/MEAL/MUST_VISIT/OPENING_HOURS。
- 正式 JSON 已避免 `_internal`、`metadata`、`budget_report` 等调试字段泄漏。

仍未完成或只是 fallback：

- NLP 不是小型离线模型，仍是规则/词典。
- Active SLAM 不是完整多轮约束获取闭环，只是风险驱动数据查询。
- MPC 不是严格 receding horizon 优化，还没有多候选轨迹预测、打分、回滚重规划。
- ACO 不是主规划器，当前主链路优先稳定 greedy + 2-opt。
- 预算/时间/交通/开闭馆不是全局约束优化，只是规则修复和局部调整。
- 多策略有差异，但缺少批量对照实验和指标证明。
- 缺少 README 要求到代码模块的逐项审计矩阵。
- 缺少覆盖多城市、多预算、多 forbidden type、多 must_visit 的回归集。

## 1. 官方 `agent_env` 可用性结论

官方链接：

- <https://github.com/LAMDA-NeSy/ChinaTravel/tree/main/agent_env>
- Raw README 已验证可访问：`https://raw.githubusercontent.com/LAMDA-NeSy/ChinaTravel/main/agent_env/README.md` 返回 HTTP 200。

本地项目中已有同源目录：

- `ChinaTravel/agent_env/README.md`
- `ChinaTravel/agent_env/SKILL.md`
- `ChinaTravel/agent_env/adapter.py`
- `ChinaTravel/agent_env/cli.py`
- `ChinaTravel/agent_env/mcp_stdio.py`
- `ChinaTravel/agent_env/http_server.py`
- `ChinaTravel/agent_env/scripts/solve_script_with_harness.py`

实测命令：

```bash
cd D:\IJCAI旅行规划挑战赛\demo1\ChinaTravel
python -m agent_env.cli tools
python -m agent_env.cli call china_travel_list_splits
```

实测结果：

- `tools` 返回 `success=true`，可用工具包括 `attractions_select`、`attractions_nearby`、`accommodations_nearby`、`restaurants_nearby`、`goto`、`intercity_transport_select`、`poi_lat_lon_search`、`china_travel_load_query` 等。
- `china_travel_list_splits` 返回 `success=true`，本地 split 包括 `easy`、`human`、`human1000`、`medium`、`preference_base50` 等。

判断：可以使用。它适合作为官方 WorldEnv 的结构化访问层、MCP/CLI 工具层、评测 harness 参考，以及未来旅行规划师 skill 的基础材料。它不应该替代官方 eval，也不应该让正式模式依赖外部 API。

## 2. 官方 `agent_env` 集成任务

### 2.1 建立可选后端

- [ ] 在 `src/data_layer/world_env_client.py` 增加 `agent_env` adapter 后端。
- [ ] 后端优先级建议：
  1. `agent_env.adapter.ChinaTravelEnvAdapter`
  2. direct `chinatravel.environment.world_env.WorldEnv`
  3. CSV bridge fallback
- [ ] 增加配置项：
  - `paths.chinatravel_root`
  - `world_env.backend = auto | agent_env | direct | csv`
  - `world_env.agent_env_cwd = ChinaTravel`
- [ ] 验收：
  - `goto`、`intercity_transport_select`、`attractions_nearby` 三类查询在 agent_env 后端和 direct 后端输出字段可被统一 normalize。

### 2.2 把 Active Query 接到结构化工具

- [ ] `active_query_selector` 输出 query plan 时明确工具名、参数、风险原因。
- [ ] 增加执行层，把 query plan 转为 agent_env structured tool call。
- [ ] 只查高风险项：
  - 酒店距离约束 -> `accommodations_nearby`
  - 景点类型/禁止类型 -> `attractions_types` / `attractions_select`
  - 餐饮偏好/预算 -> `restaurants_cuisine` / `restaurants_select`
  - 交通风险 -> `goto` / `intercity_transport_select`
  - 坐标/距离 fallback -> `poi_lat_lon_search`
- [ ] 验收：
  - 给定一条含 hotel within 5 km + do not visit museum + dining budget 的 query，只执行相关工具，不全量扫所有表。

### 2.3 用 `agent_env` 做 verifier repair 的事实查询

- [ ] `typed_repair.OPENING_HOURS` 用 `attractions_id_is_open` / `restaurants_id_is_open` 查询开放状态。
- [ ] `typed_repair.TRANSPORT` 用 `goto` 修复缺失或不可达交通段。
- [ ] `typed_repair.MEAL` 用 `restaurants_nearby` 补附近餐厅。
- [ ] `typed_repair.BUDGET` 用 `restaurants_select` / `accommodations_select` 找低价替代。
- [ ] 验收：
  - repair 不再只改字段，而是基于 WorldEnv/agent_env 查询结果替换对象或重建交通。

## 3. README / Prompt 符合度审计任务

- [ ] 生成 `README_REQUIREMENT_MATRIX.md`。
- [ ] 每条要求至少包含：
  - Requirement
  - Current status: done / partial / fallback / missing
  - Module
  - Evidence
  - Test coverage
  - Next action
- [ ] 审计范围：
  - NLP / constraint_parser / hard_logic formal stripping
  - Active SLAM / uncertainty / query selector
  - semantic_grounder
  - candidate_generator + rankers
  - poi_task_assignment
  - rolling_day_planner / plan_builder
  - day_route_optimizer / 2-opt / ACO
  - budget_controller
  - local_checker / official_verifier_runner
  - typed_repair
  - submission_writer / plan_formatter
- [ ] 验收：
  - 每个 prompt 要求都能定位到代码或明确标为未完成。

## 4. NLP 升级任务

### 4.1 扩展规则词典

- [ ] 建立 `src/constraints/lexicons/`。
- [ ] 拆分词典：
  - pace phrases
  - budget phrases
  - forbidden attraction types
  - must visit type phrases
  - accommodation distance phrases
  - dining/cuisine phrases
  - transport phrases
- [ ] 增加中英文同义词和 ChinaTravel 数据字段对齐。

### 4.2 小型离线模型预留

- [ ] 设计 `LocalIntentParser` 接口。
- [ ] 默认使用 rule parser。
- [ ] 可选接入本地小模型或 sentence-transformers 时，必须离线运行，不调用外部 API。
- [ ] 输出仍统一为 `ConstraintCard`。

### 4.3 模糊约束精确定义

- [ ] `not too tired` -> 每天 POI 上限、交通上限、buffer minutes。
- [ ] `as many as possible` -> 提高 POI 容量，但不破坏时间/预算硬约束。
- [ ] `do not visit X` -> forbidden type / forbidden POI。
- [ ] `want to visit X` -> must type / must POI / preference。
- [ ] `hotel within N km of X` -> accommodation spatial hard constraint。
- [ ] `dining budget below N` -> meal total or per-meal budget，需识别语义。
- [ ] 验收：
  - 新增不少于 30 条 NLP unit tests。

## 5. Active SLAM 升级任务

- [ ] 把当前风险分数升级为 belief state：
  - unknown constraints
  - missing data
  - high repair risk
  - verifier historical failures
- [ ] 查询动作要有 cost：
  - 数据查询时间
  - 结果规模
  - 对规划影响
- [ ] 查询选择目标函数：
  - maximize expected constraint clarification
  - minimize unnecessary data access
- [ ] 查询结果回写 `ConstraintProfile` 或 candidate metadata。
- [ ] 验收：
  - 对同一 query，query plan 能解释“为什么查这个，不查那个”。

## 6. MPC 滚动逐日规划升级任务

- [ ] 引入 `PlanningState`：
  - day index
  - current position
  - current hotel
  - remaining budget
  - remaining time
  - remaining must visits
  - energy / pace budget
  - policy
- [ ] 每日生成多个 candidate day plans。
- [ ] 用 horizon score 评估：
  - must visit completion
  - remaining feasibility
  - budget/time slack
  - transport cost
  - preference gain
- [ ] 选择当天 action 后更新 state，再规划下一天。
- [ ] 验收：
  - 不同 policy 在相同 query 上产生可解释差异。
  - 删除某个景点后能重算后续天，而不是只删不补。

## 7. 日内路线优化升级任务

- [ ] 保持结构锚点：
  - intercity transport
  - breakfast/lunch/dinner
  - accommodation
- [ ] 只重排 attraction 段。
- [ ] 目标函数：
  - transport time
  - transport cost
  - walking/metro/taxi penalty
  - opening hours penalty
  - fatigue penalty
- [ ] 2-opt 作为稳定默认。
- [ ] ACO 作为可选增强：
  - pheromone = 高质量路线记忆
  - heuristic = 近距离/低成本/开放时间适配
  - constraints = forbidden/closed/unreachable
- [ ] 验收：
  - 给定同一天 3+ 个景点，优化后交通代价不高于初始 greedy 路线。

## 8. 预算/体力/时间控制升级任务

- [ ] 建立统一 `ResourceState`：
  - total budget
  - dining budget
  - accommodation budget
  - daily remaining time
  - fatigue score
- [ ] budget repair 顺序：
  1. 换低价餐厅
  2. 换低价酒店
  3. taxi -> metro/walk
  4. 调整 POI 顺序减少交通
  5. 删除非必去景点
  6. 若仍失败，输出 typed failure reason
- [ ] 每次变更后重算：
  - activity cost
  - transport cost
  - total_cost
  - affected start/end times
- [ ] 验收：
  - 不允许只打标记不修改 plan。

## 9. Typed Repair 闭环任务

- [ ] repair pipeline 改为迭代：
  1. local checker
  2. official verifier / eval bridge
  3. error parser
  4. typed repair
  5. re-check
  6. stop when success or max rounds
- [ ] 每类错误建立专门测试：
  - FORMAT
  - TICKET
  - TRANSPORT
  - BUDGET
  - TIME
  - MEAL
  - MUST_VISIT
  - OPENING_HOURS
- [ ] 验收：
  - 每类错误至少一个红绿测试。

## 10. 多策略实验任务

- [ ] 定义 policy objective weights：
  - safe: fewer POIs, larger buffer, lower repair risk
  - budget: low price, low taxi, cheap hotel/restaurant
  - preference: high NL preference satisfaction
  - low_transport: low intra-day distance/time
  - must_visit_first: maximize early must-visit completion
- [ ] 对同一批 query 跑策略对照。
- [ ] 输出指标：
  - success rate
  - verifier score
  - total cost
  - transport time
  - must visit hit rate
  - preference hit rate
  - average activities/day
- [ ] 验收：
  - 每个 policy 的指标和路线差异可解释。

## 11. 回归测试任务

- [ ] 建立 `tests/fixtures/queries/`。
- [ ] 至少覆盖：
  - hotel within N km
  - dining budget
  - total budget
  - forbidden type
  - must visit type
  - not too tired
  - as many as possible
  - train/airplane preference
  - no museum / no memorial hall
  - local cuisine / recommended food
- [ ] 批量命令：

```bash
python -m compileall .
python src/constraints/test_constraints.py
python src/data_layer/test_data_layer.py
python src/candidates/test_candidates.py
python src/active/test_active.py
python src/adapter/test_adapter.py
python run_tpc.py --splits training --index 20250324234255286741 --timeout 300
```

- [ ] 新增批量 smoke：

```bash
python run_tpc.py --splits training --limit 20 --timeout 300
python run_tpc.py --splits easy --limit 20 --timeout 300
```

## 12. 未来旅行规划师 Skill 制作任务

后续可以基于官方 `ChinaTravel/agent_env/SKILL.md` 制作一个更贴合本项目的 Codex skill。

建议 skill 名：

- `chinatravel-planner`
- 或 `travel-planner-chinatravel`

Skill 目标：

- 指导 Codex 在 ChinaTravel 任务中优先使用结构化 WorldEnv/agent_env 查询。
- 规范正式模式不得使用 `hard_logic_py`。
- 固化 NLP -> constraints -> active query -> candidates -> MPC planning -> route optimization -> repair -> submission 的流程。
- 固化输出 JSON schema 和禁止调试字段泄漏。
- 固化常用测试命令和验收标准。

Skill 文件应包含：

- 何时使用
- 禁止事项
- 标准工作流
- agent_env CLI 常用命令
- 输出 schema 摘要
- repair checklist
- 测试 checklist

验收：

- 新开 Codex 会话只读 skill，也能按本项目流程完成一次 query 修复或规划。

## 13. 推荐执行顺序

1. 先做 `README_REQUIREMENT_MATRIX.md`，把需求逐条钉住。
2. 接入 `agent_env` 可选后端，并完成 CLI/adapter smoke tests。
3. 补 NLP/constraint 单测，不急着加复杂算法。
4. 做 MPC state 和候选 day plan 打分。
5. 做 repair 迭代闭环。
6. 做多策略实验和批量回归。
7. 最后抽象成 `chinatravel-planner` skill。

## 14. 当前风险

- `demo1/tpc_agent/src` 仍有旧代码副本，虽然当前官方入口已改为导入根目录 `src`，但错误工作目录仍可能触发旧逻辑。
- `agent_env` 命令需要从 `ChinaTravel` 根目录运行，或显式设置 Python path。
- NLP 规则继续扩展时要防止误解析，例如 `dining budget` 不应被当成 `total budget`。
- WorldEnv、agent_env、CSV fallback 的字段命名需要统一 normalize，否则 repair 和 ranker 会出现隐蔽字段错配。
- 批量评测前不要再只依赖单条 `succ=True`，需要看 schema、时间轴、成本、must/preference 命中率。
