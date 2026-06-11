# Phase 1 Codex Handoff Report

> 日期: 2026-06-11
> 开发者: Main Dev Agent
> 审阅者: Codex (audit & eval agent)

---

## 1. 修改了哪些文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `README_REQUIREMENT_MATRIX.md` | **新建** | 50 项需求的逐条审计矩阵 (done/partial/fallback/missing) |
| `config.yaml` | 修改 | 新增 `world_env` 段: `backend: auto`, `agent_env_cwd: ChinaTravel` |
| `src/data_layer/world_env_client.py` | **重写** | 新增 `AgentEnvBackend` 类; `SandboxClient` 支持 agent_env → direct → csv 三层后端; 新增 normalize 函数; 新增 `restaurants_nearby()`、`poi_lat_lon()` 方法; `get_chinatravel_status()` 增加 agent_env 状态字段 |
| `src/data_layer/schema.py` | 新增 | 4 个新 dataclass: `ConstraintBelief`, `ActiveAction`, `ActionSelectionResult`, 及相关类型 |
| `src/active/active_constraint_mapping.py` | **新建** | 完整 Active Constraint Mapping 框架: belief state → action generation → info_gain → query_cost → selection → explanation → belief update (7 步) |
| `src/active/active_query_selector.py` | **重写** | 委托到 `active_constraint_mapping()`; 保留 `ActiveInfo` 返回类型和 `get_last_active_info()` 缓存接口; `fetched_data` 新增 `acm_beliefs`, `acm_explanations`, `selected_actions` 字段 |
| `src/optimizer/ga_tsp_interface.py` | **新建** | GA-TSP 输入/输出 dataclass 定义 + 接口文档 + 辅助函数规格 |
| `src/optimizer/day_route_optimizer.py` | 修改 | docstring 增加 GA-TSP 集成点说明 |

**未修改但依赖新接口的文件** (Phase 2 需要关注):
- `main.py` — `solve_one_query()` 中调用 `active_query_selector()` 和 `_repair_loop()`, 接口不变
- `src/planner/plan_builder.py` — 使用 `SandboxClient`, 后端自动切换, 无需修改
- `src/repair/typed_repair.py` — 仍为 fallback 字段修补

---

## 2. 新增了哪些接口

### 2.1 AgentEnvBackend (src/data_layer/world_env_client.py)

```python
class AgentEnvBackend:
    def __init__(self, agent_env_cwd: str | None = None)
    @property
    def available(self) -> bool
    # Normalized tools (same shape as direct WorldEnv):
    def goto(city, start, end, start_time, mode) -> list[dict]
    def intercity_transport_select(start_city, end_city, mode, earliest) -> list[dict]
    def attractions_nearby(city, point, topk, max_dist_km) -> list[dict]
    def accommodations_nearby(city, anchor, topk, max_dist_km) -> list[dict]
    def restaurants_nearby(city, point, topk, max_dist_km) -> list[dict]
    def poi_lat_lon(city, name) -> dict | None
    def select_attractions(city, key, op, value) -> list[dict]
    def select_accommodations(city, key, op, value) -> list[dict]
    def select_restaurants(city, key, op, value) -> list[dict]
    def is_attraction_open(city, poi_id, time_str) -> bool
    def is_restaurant_open(city, poi_id, time_str) -> bool
```

### 2.2 SandboxClient 新增方法

```python
class SandboxClient:
    @property
    def backend_name(self) -> str          # "agent_env" | "direct" | "csv"
    def restaurants_nearby(city, point, topk, max_dist_km) -> list[dict]   # NEW
    def poi_lat_lon(city, name) -> dict | None                             # NEW
```

### 2.3 Active Constraint Mapping (src/active/active_constraint_mapping.py)

```python
def active_constraint_mapping(constraints, risk_profile, max_actions=6) -> ActionSelectionResult
def init_beliefs(constraints, risk_profile) -> dict[str, ConstraintBelief]
def generate_candidate_actions(beliefs, constraints) -> list[ActiveAction]
def estimate_info_gain(action, beliefs) -> float
def estimate_query_cost(action) -> float
def select_actions(actions, beliefs, max_actions) -> tuple[list, list]
def explain_selection(selected, rejected, beliefs) -> list[str]
def update_beliefs(beliefs, executed_actions, query_results) -> dict[str, ConstraintBelief]
```

### 2.4 GA-TSP Interface (src/optimizer/ga_tsp_interface.py)

```python
@dataclass DayAttraction       # 每天待排序景点
@dataclass TransportSegment    # 单段交通
@dataclass TransportMatrix     # pairwise 矩阵
@dataclass GATSPConfig         # GA 超参数
@dataclass GATSPResult         # GA 优化结果
def extract_ga_tsp_inputs(...) # 从当前数据提取 GA-TSP 输入
def build_transport_matrix_spec(...) # 预计算稠密矩阵
```

### 2.5 新增 Schema 类型 (src/data_layer/schema.py)

```python
@dataclass ConstraintBelief        # 单维度 belief: resolved, confidence, missing_data, risk_level
@dataclass ActiveAction            # 结构化查询动作: tool_name, params, info_gain, query_cost, priority_score
@dataclass ActionSelectionResult   # ACM 完整结果: beliefs, selected/rejected actions, explanations
```

---

## 3. 哪些地方仍是 fallback

| 模块 | Fallback 说明 | 优先级 |
|------|--------------|--------|
| `typed_repair` | 仍是纯字段修补，不查询 WorldEnv/agent_env | P1 — 下阶段 |
| `budget_controller` | 删景点时只从最后一天反向删，不够智能 | P1 |
| `rolling_day_planner` + `plan_builder` | MPC 不是真正的逐日 receding horizon | P1 |
| `nl_parser` | 仍是规则/词典，无离线模型 | P2 |
| `day_route_optimizer` | 仍是 greedy + 2-opt，无 GA-TSP | P2 (接口已就绪) |
| `ACO ant_colony` | 代码存在但默认退化到 2-opt | P2 |
| `local_checker` | 缺 OPENING_HOURS/TRANSPORT contiguity/duplicate POI 检查 | P1 |
| agent_env backend | `auto` 模式下可用，但 `restaurants_nearby` 等新方法在 direct/csv 后端退化到 list_all | P2 |

---

## 4. 需要 Codex 用官方 eval_tpc.py 验证哪些点

1. **输出 schema 合规**: 验证 `data/outputs/results/TPCAgent_TPCLLM/{uid}.json` 的顶层字段 (`people_number`, `start_city`, `target_city`, `itinerary`) 和 activity 字段 (`type`, `start_time`, `end_time`, `cost`, `transports`) 通过官方 `output_schema.json` 校验。

2. **agent_env 后端对 plan 质量的影响**: 对比 `world_env.backend=auto` (当前 agent_env) 和 `world_env.backend=csv` (纯 CSV) 跑同一条 query 的 verifier score。

3. **Active Constraint Mapping 的查询数量**: 确认每条 query 的 `priority_queries` 不超过 `max_actions` (默认 6)，且每条查询有对应的 `tool_name` 和 `selection_reason`。

4. **repair 后的 verifier 收敛**: 跑 `run_tpc.py --splits training --limit 10 --timeout 300`，检查 `_repair_loop` 是否在 3 轮内收敛 (errors 不再变化)。

5. **禁止字段泄漏**: 确认输出的 plan JSON 不含 `_internal_score`, `_internal_query_id`, `_traceback`, `_planning_constraints`, `budget_report` 等调试字段。

6. **oracle_translation=false 模式下 hard_logic_py 彻底剥离**: 验证 `query_adapter.py` 的 `ORACLE_FIELDS` 列表完整（当前: `hard_logic_py`, `hard_logic_nl`, `hard_logic`）。

---

## 5. 是否可能影响 run_tpc.py 输出目录或 output_schema

**不影响**。具体分析:

- `run_tpc.py` 输出目录: `data/outputs/results/{method}/{uid}.json` — 本次改动未修改 `run_tpc.py`、`tpc_agent.py`、`plan_formatter.py`、`submission_writer.py` 中的任何路径逻辑。
- `output_schema`: 官方 schema 要求的顶层字段 (`people_number`, `start_city`, `target_city`, `itinerary`) 在 `format_official_plan()` 和 `render_to_official_format()` 中保持不变。
- `fetch_data` 中新增的 `acm_beliefs`, `acm_explanations`, `selected_actions` 字段属于 `ActiveInfo.fetched_data`，不进入官方输出（`plan_formatter.py` 过滤 `_` 前缀字段）。
- `world_env.backend` 配置变更只切换数据源后端，不影响输出格式。

---

## 测试结果

```
python -m compileall .                     → OK (no errors)
python src/data_layer/test_data_layer.py   → 8/8 PASSED
python src/active/test_active.py           → 3/3 PASSED
python src/adapter/test_adapter.py         → 5/5 PASSED (succ=True, itinerary_len=3)
```

`test_adapter.py` 中 `TPCAgent.run` 现在返回 `succ=True` 且 `itinerary_len=3`，说明 pipeline 已产出有效行程。
