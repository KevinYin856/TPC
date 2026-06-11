# Eval Alignment Report

## 2026-06-11 最新补充

本轮复核后，官方评测对齐需要额外注意三点：

1. `eval_tpc.py --lang en` 会自动把 `--method TPCAgent_TPCLLM` 改为 `TPCAgent_TPCLLM_en`，因此实际读取目录是 `ChinaTravel/results/TPCAgent_TPCLLM_en/`。如果生成脚本仍写入 `ChinaTravel/results/TPCAgent_TPCLLM/`，英文评测会读不到刚生成的文件。
2. `scripts/run_official_eval_smoke.py` 当前官方 loader 分支存在 `name 'lang' is not defined`，实际运行会 fallback 到本地搜索；它还会用 `oracle_translation=False` 删除 `hard_logic_py`，这与 `eval_tpc.py` 对本地 split 的行为不完全一致。
3. 对英文 query/plan 使用默认 `--lang zh` 会触发 commonsense 的城市 key mismatch，样例表现为 `Mic.EPR nan` / `Overall nan`。本地英文 split 应使用 `--lang en` 并同步到 `{method}_en` 目录。

有效 smoke 评测命令应类似：

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1\ChinaTravel
New-Item -ItemType Directory -Force -Path results\TPCAgent_TPCLLM_en
Copy-Item -Force results\TPCAgent_TPCLLM\20250324234255286741.json results\TPCAgent_TPCLLM_en\20250324234255286741.json
python eval_tpc.py --splits demo1_training_single --method TPCAgent_TPCLLM --lang en
```

本轮有效英文 smoke 分数：

```text
Mic.EPR = 73.07692307692308
Mac.EPR = 0.0
C-LPR   = 0.0
FPR     = 0.0
Overall = 14.615384615384617
```

审计角色：评测与对齐 agent。本文只记录官方评测输入输出、当前项目输出目录、schema 风险和给主开发 agent 的约束；不修改核心 planner / optimizer / repair 代码。

## 一、官方 `eval_tpc.py` 的输入输出要求

### 1. 命令参数

官方评测入口位于：

```text
ChinaTravel/eval_tpc.py
```

核心参数：

```bash
python eval_tpc.py --splits <split_name> --method <method_name> [--lang zh|en] [--preference]
```

读取逻辑：

- `--splits` 传给 `chinatravel.data.load_datasets.load_query(args)`，用于确定 query id 列表和 query 数据。
- `--method` 用于定位结果目录：`results/{method}`。
- `--lang en` 时，如果 method 不以 `_en` 结尾，官方脚本会自动把 method 改成 `{method}_en`。
- `--preference` 会额外执行 preference evaluator。

官方本地 split 文件目录：

```text
ChinaTravel/chinatravel/evaluation/default_splits/
```

本地存在的 split 文件包括：

```text
easy
human
human1000
medium
p0base50
p1base50
p2base50
p3base50
p4base50
p5base50
preference_base50
```

注意：`load_datasets.py` 对中文 `easy`、`medium`、`human`、`preference_base50` 等 split 可能走 HuggingFace dataset；`human1000`、`p0base50` 等未列入 HuggingFace 分支的 split 会走本地 `default_splits/{split}.txt`。

### 2. 官方结果读取路径

`eval_tpc.py` 中固定：

```python
results_dir = os.path.join("results", args.method)
```

随后对每个 query id 读取：

```text
results/{method}/{query_id}.json
```

结论：官方 `eval_tpc.py` 默认从 `ChinaTravel/results/{method}/{query_id}.json` 读取输出，前提是当前工作目录是 `D:\IJCAI旅行规划挑战赛\demo1\ChinaTravel`。

### 3. 官方评分项

`eval_tpc.py` 会计算：

- Schema constraints  
  使用 `ChinaTravel/chinatravel/evaluation/output_schema.json` 和 `jsonschema.validate`。

- Commonsense constraints  
  调用 `evaluate_commonsense_constraints(...)`，输出：
  - `Mic.EPR`
  - `Mac.EPR`

- Hard constraints  
  调用 `evaluate_hard_constraints_v2(...)`，输出：
  - `C-LPR`

- FPR  
  取 schema pass、commonsense pass、hard constraints pass 的交集：

  ```python
  all_pass_id = list(set(schema_pass_id) & set(commonsense_pass_id) & set(logi_pass_id))
  FPR = len(all_pass_id) / len(query_index) * 100
  ```

- Default preference-like route/activity scores  
  `cal_default_pr_score(...)` 计算：
  - `DAV`
  - `ATT`
  - `DDR`

- Overall Score  
  官方脚本公式：

  ```python
  final_score = (
      0.1 * micro_comm
      + 0.1 * micro_comm
      + 0.25 * conditional_micro_logi
      + 0.05 * DAV
      + 0.05 * ATT
      + 0.05 * DDR
      + 0.4 * FPR
  )
  ```

结果会打印到 stdout，并 append 写入：

```text
ChinaTravel/your_tpc_scores.json
```

## 二、本项目当前输出目录对齐情况

本项目运行入口：

```text
run_tpc.py
```

当前输出目录：

```python
results_dir = PROJECT_ROOT / "data" / "outputs" / "results" / method
```

默认 method：

```text
TPCAgent_TPCLLM
```

因此当前生成路径是：

```text
D:\IJCAI旅行规划挑战赛\demo1\data\outputs\results\TPCAgent_TPCLLM\{uid}.json
```

官方 `eval_tpc.py` 期望路径是：

```text
D:\IJCAI旅行规划挑战赛\demo1\ChinaTravel\results\TPCAgent_TPCLLM\{uid}.json
```

结论：当前 `run_tpc.py` 输出目录不能被官方 `eval_tpc.py` 直接读取。文件名 `{uid}.json` 和 method 名可以对齐，但根目录不一致。

另一个 split 对齐风险：

- 本项目 `run_tpc.py --splits training` 使用 `data/training data/` 或 `data/splits/training.txt`。
- 官方 `ChinaTravel/eval_tpc.py --splits training` 会查 `ChinaTravel/chinatravel/evaluation/default_splits/training.txt`，当前官方目录没有该 split。
- 因此，用官方 eval 时应使用官方实际存在的 split，例如 `human1000`、`p0base50`、`easy`、`medium`、`human`、`preference_base50`。其中 `human1000` / `p0base50` 更适合本地无网络评测路径。

## 三、最小适配方案

优先不破坏现有 `run_tpc.py`。推荐顺序如下。

### 方案 A：同步/复制结果，推荐

保留当前项目输出目录，新增一个非核心同步脚本或手工命令，把：

```text
data/outputs/results/{method}/*.json
```

复制到：

```text
ChinaTravel/results/{method}/*.json
```

优点：

- 不改 planner / optimizer / repair。
- 不改变现有本地实验目录结构。
- 完全符合官方 `eval_tpc.py` 读取约定。
- 适合审计 agent 和 Claude Code 分工。

PowerShell 示例：

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1
$method = "TPCAgent_TPCLLM"
New-Item -ItemType Directory -Force "ChinaTravel\results\$method" | Out-Null
Copy-Item "data\outputs\results\$method\*.json" "ChinaTravel\results\$method\" -Force
```

### 方案 B：目录软链接/联接，可选

在 `ChinaTravel/results/{method}` 创建到 `data/outputs/results/{method}` 的目录联接。

PowerShell 示例：

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1
$method = "TPCAgent_TPCLLM"
New-Item -ItemType Directory -Force "ChinaTravel\results" | Out-Null
cmd /c mklink /J "ChinaTravel\results\%method%" "data\outputs\results\%method%"
```

风险：

- Windows 权限、已有目录、相对路径和 CI 环境可能让软链接更脆。
- 不如复制脚本直观。

### 方案 C：修改 `run_tpc.py` 输出路径，暂不推荐

可以让 `run_tpc.py` 直接写到 `ChinaTravel/results/{method}`，但这会改变现有实验产物位置，并可能影响本项目已有 cache/results 管理。

除非后续明确决定“官方 eval 是唯一输出目标”，否则不要先改。

## 四、schema 风险点

官方 schema 文件：

```text
ChinaTravel/chinatravel/evaluation/output_schema.json
```

### 1. 顶层字段

必需：

```json
people_number
start_city
target_city
itinerary
```

当前 `plan_formatter.py` 会输出这些字段。当前样例额外输出：

```json
elapsed_time(sec)
```

官方 schema 没有设置 `additionalProperties: false`，所以额外顶层字段不会导致 JSON schema validate 失败。但是正式提交最好保持克制；`elapsed_time(sec)` 不是 `_internal` / `metadata` / `debug`，但它也不是 schema 必需字段。

失败空计划路径中 `build_empty_plan(..., error=...)` 会额外写：

```json
error
```

这也不会被当前 schema 禁止，但会导致 `is_plan_success` false，commonsense/hard/FPR 基本无法通过。正式评测产物中应尽量避免 `error`。

### 2. itinerary/day 字段

每个 day 必需：

```json
day
activities
```

### 3. activity 字段

每个 activity 必需：

```json
type
start_time
end_time
cost
price
transports
```

`type` 只能是：

```json
airplane
train
attraction
breakfast
lunch
dinner
accommodation
```

时间格式必须匹配：

```text
^\d{2}:\d{2}$
```

注意：schema 只检查格式，不检查 `24:35` 这类跨日时间是否合理；这类问题会落到 commonsense constraints。

### 4. airplane/train 条件字段

如果 activity type 是 `airplane` 或 `train`，必须有：

```json
start
end
```

如果 type 是 `airplane`，必须有：

```json
FlightID
```

如果 type 是 `train`，必须有：

```json
TrainID
```

Schema 没有强制 `tickets`，但 commonsense/hard constraints 很可能依赖票数合理性。开发侧仍应保留 intercity `tickets`。

### 5. transports 字段

每个 transport segment 必需：

```json
start
end
mode
start_time
end_time
price
cost
distance
```

`mode` 只能是：

```json
walk
metro
taxi
```

`tickets` 不是 schema 必需字段，但 metro 票数通常应有。`cars` 不在 schema properties 中，但当前 schema 不禁止额外字段；如果使用 taxi cars，仍需确认 commonsense evaluator 是否接受。

### 6. formatter / writer 风险

`src/adapter/plan_formatter.py`：

- `run_tpc.py` 实际走这个路径。
- 如果 `pipeline_result["itinerary"]` 是完整 official dict，`format_official_plan` 会 `dict(itinerary_payload)` 并补顶层字段。
- 当前代码不会递归剥离 nested debug 字段。
- 当前代码会添加 `elapsed_time(sec)`。

`src/submission/submission_writer.py`：

- `main.solve_one_query` 内部先用 `render_to_official_format(plan)`，再由 adapter formatter 包一层输出。
- `render_to_official_format` 会去掉 official plan 顶层以 `_` 开头的字段，例如 `_planning_constraints`。
- 它同样不会递归剥离 activity / transport 内部 debug 字段。
- `write_submission` 只写 `plan.itinerary`，不做 schema validate。

当前已检查样例：

```text
data/outputs/results/TPCAgent_TPCLLM/20250324234255286741.json
```

未发现以下字段泄漏：

```text
_internal
metadata
budget_report
debug
local_check_issues
time_issues
```

但这只是单条样例，后续应把“递归字段泄漏检查”加入固定测试。

## 五、给 Claude Code 的开发约束

Claude Code 做主开发时必须遵守：

### 禁止出现在正式 JSON 的字段

任何层级都不要输出：

```text
_internal
_internal_score
_internal_query_id
_planning_constraints
metadata
budget_report
local_check_issues
time_issues
debug
traceback
_traceback
raw_candidates
candidate_pool
repair_log
verifier_errors
```

### 顶层必须存在

```text
people_number: integer
start_city: string
target_city: string
itinerary: array
```

### day 必须存在

```text
day: integer
activities: array
```

### activity 必须存在

```text
type: enum
start_time: HH:MM
end_time: HH:MM
cost: number
price: number
transports: array
```

### intercity activity 必须存在

`airplane`：

```text
start
end
FlightID
```

`train`：

```text
start
end
TrainID
```

开发侧还应保留：

```text
tickets
```

### attraction / meal / accommodation 建议字段

Attraction：

```text
position
tickets
```

Meal：

```text
position
```

Accommodation：

```text
position
room_type
rooms
```

这些不是全部被 schema 强制，但很可能影响 commonsense/hard constraints。

### transport segment 必须存在

```text
start
end
mode
start_time
end_time
price
cost
distance
```

metro 建议保留：

```text
tickets
```

taxi 如保留 `cars`，必须确认官方 commonsense evaluator 不会误判；schema 本身不禁止额外字段。

### 目录约束

不要让核心 planner 直接依赖 `ChinaTravel/results`。规划器只产出官方 dict；评测同步由外层脚本完成。

## 六、验证命令

### 1. 运行本项目生成结果

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1
python run_tpc.py --splits training --index 20250324234255286741 --timeout 300
```

输出位置：

```text
D:\IJCAI旅行规划挑战赛\demo1\data\outputs\results\TPCAgent_TPCLLM\20250324234255286741.json
```

注意：该 `training` split 是本项目本地 split，不是官方 `ChinaTravel/eval_tpc.py` 当前默认 split。

### 2. 同步结果到官方 eval 目录

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1
$method = "TPCAgent_TPCLLM"
New-Item -ItemType Directory -Force "ChinaTravel\results\$method" | Out-Null
Copy-Item "data\outputs\results\$method\*.json" "ChinaTravel\results\$method\" -Force
```

### 3. 运行官方 eval

如果使用官方本地 split，推荐先用 `human1000` 或 `p0base50`：

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1\ChinaTravel
python eval_tpc.py --splits human1000 --method TPCAgent_TPCLLM
```

或：

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1\ChinaTravel
python eval_tpc.py --splits p0base50 --method TPCAgent_TPCLLM
```

如果环境能访问 HuggingFace dataset，可评估：

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1\ChinaTravel
python eval_tpc.py --splits easy --method TPCAgent_TPCLLM
python eval_tpc.py --splits medium --method TPCAgent_TPCLLM
python eval_tpc.py --splits human --method TPCAgent_TPCLLM
python eval_tpc.py --splits preference_base50 --method TPCAgent_TPCLLM --preference
```

### 4. 单文件 schema / 泄漏检查建议

后续可以固定一个审计脚本做两件事：

1. 用 `ChinaTravel/chinatravel/evaluation/output_schema.json` validate JSON。
2. 递归扫描 forbidden keys。

禁止 key 示例：

```text
_internal
metadata
budget_report
debug
local_check_issues
time_issues
traceback
```

## 七、当前审计结论

1. 官方 `eval_tpc.py` 默认从 `results/{method}/{query_id}.json` 读取输出。确认。
2. 官方 `eval_tpc.py` 会计算 schema constraints、commonsense constraints、hard constraints、FPR、Overall Score。确认。
3. 本项目 `run_tpc.py` 当前输出目录不能直接被官方 `eval_tpc.py` 读取。需要同步到 `ChinaTravel/results/{method}`。
4. 最小适配建议：使用复制/同步脚本，不改核心 planner，不优先改 `run_tpc.py` 输出路径。
5. 当前单条样例正式 JSON 未发现 `_internal`、`metadata`、`budget_report`、`debug` 泄漏；但 `elapsed_time(sec)` 是额外顶层字段，schema 允许，但正式评测可考虑保留或在同步脚本中剥离。
6. `plan_formatter` 和 `submission_writer` 基本符合 output_schema 的顶层结构，但都不做递归 debug 字段清理，也不主动 schema validate；这是后续审计/同步脚本应补的位置。
