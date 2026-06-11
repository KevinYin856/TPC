# TEST_RESULTS

审计日期：2026-06-11

角色：eval / audit agent。未修改核心 planner / optimizer / repair。

## 1. Commands Run

### Compile

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1
python -m compileall .
```

结果：

```text
PASS
```

### Unit Tests

```powershell
python src/constraints/test_constraints.py
python src/data_layer/test_data_layer.py
python src/candidates/test_candidates.py
python src/active/test_active.py
python src/adapter/test_adapter.py
```

结果：

```text
constraints: PASS, 5/5
data_layer:  PASS, 8/8
candidates:  PASS, 3/3
active:      PASS, 3/3
adapter:     PASS, 5/5
```

备注：`adapter` 和 `run_tpc` 过程中出现大量 `add_minutes` overflow warning，说明当前时间合法化主要靠 `23:59` 截断。

## 2. run_tpc Smoke

命令：

```powershell
python run_tpc.py --splits training --index 20250324234255286741 --timeout 300
```

结果：

```text
succ=True
schema OK
saved -> data/outputs/results/TPCAgent_TPCLLM/20250324234255286741.json
```

JSON 检查：

```text
top_keys = ['people_number', 'start_city', 'target_city', 'itinerary', 'elapsed_time(sec)']
forbidden debug leaks = 0
invalid_times_count = 0
clipped_2359_count = 8
intercity_count = 2
fake_id_count in generated plan = 0
```

城际交通：

```text
Day 1 train: Suzhou Station -> Chengdu East Railway Station, TrainID=D353, 06:49-20:34
Day 3 train: Chengdu East Railway Station -> Suzhou Station, TrainID=D3058, 18:40-23:59
```

注意：生成结果里没有 fake ID，但代码路径仍存在 `TR_` / `FL_` fallback。

## 3. Sync To Official Results

命令：

```powershell
python scripts/sync_results.py --method TPCAgent_TPCLLM --uid 20250324234255286741
```

结果：

```text
1 file copied to ChinaTravel/results/TPCAgent_TPCLLM/
```

## 4. Official eval_tpc: Default zh

命令：

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1\ChinaTravel
python eval_tpc.py --splits demo1_training_single --method TPCAgent_TPCLLM
```

结果：

```text
Mic.EPR: nan
Mac.EPR: 0.0
C-LPR: 0.0
FPR: 0.0
Overall Score: nan
```

解释：

- `demo1_training_single` 的 query/plan 是英文城市名。
- 默认 `zh` 工具表找不到 `Suzhou` / `Chengdu`，commonsense 内部触发 KeyError 后被官方代码吞掉。
- 这不是有效正式分数。

## 5. Official eval_tpc: English

准备：

```powershell
cd D:\IJCAI旅行规划挑战赛\demo1\ChinaTravel
New-Item -ItemType Directory -Force -Path results\TPCAgent_TPCLLM_en
Copy-Item -Force results\TPCAgent_TPCLLM\20250324234255286741.json results\TPCAgent_TPCLLM_en\20250324234255286741.json
```

命令：

```powershell
python eval_tpc.py --splits demo1_training_single --method TPCAgent_TPCLLM --lang en
```

结果：

```text
Method: TPCAgent_TPCLLM_en
Mic.EPR: 73.07692307692308
Mac.EPR: 0.0
C-LPR: 0.0
FPR: 0.0
DAV: 0.0
ATT: 0.0
DDR: 0.0
Overall Score: 14.615384615384617
```

Manual isolation：

```text
schema = 100.0
hard logic = 100.0 micro / 100.0 macro
commonsense_pass_id = []
hard_logic_pass_id = ['20250324234255286741']
```

结论：

- 样例 hard constraints 实际全部通过。
- 官方 C-LPR 和 FPR 为 0，是因为 commonsense 没全过，conditional gate 没放行。

## 6. Commonsense Failure Columns

英文评测下，该样例 commonsense 失败项：

```text
Incorrect Information of Intercity Transport on price or duration
Visiting Restruants in their closed time
Repeated Restruants Choices
Inappropriate Meal Times
Incorrect cost information of Inner-City Transport
Does not follow Chronological Order
Invalid Transport information across positions
```

主要可观察原因：

```text
Day 1 lunch/dinner/accommodation 被推到 23:59
多个 transport 子段仍有 24:xx 时间
metro/taxi cost 没有按 people/cars 汇总
餐厅重复使用
返程 train 前缺少从上一活动到车站的衔接 transport
D3058 真实跨日到达被截断为 23:59，duration/price 校验失败
```

## 7. Smoke Runner Test

命令：

```powershell
python scripts/run_official_eval_smoke.py --split demo1_training_single --limit 1 --method TPCAgent_TPCLLM --timeout 300 --lang en
```

结果：

```text
official load_query failed: name 'lang' is not defined
fallback local search
generated: 1
success: 1
schema pass: 1/1
```

问题：

- smoke runner 没有真正走官方 loader。
- 它写入 `results/TPCAgent_TPCLLM/`，但官方 `--lang en` 会读取 `results/TPCAgent_TPCLLM_en/`。

## 8. Current Score Summary

有效英文官方 smoke 分数：

```text
Mic.EPR = 73.07692307692308
Mac.EPR = 0.0
C-LPR   = 0.0
FPR     = 0.0
Overall = 14.615384615384617
```

无效或不可比结果：

```text
zh default on English local split: nan
public easy/medium/human without hard_logic_py: cannot fully compute C-LPR/FPR/Overall in this local setup
```

## 9. Remaining Test Risk

- 未重新跑完整 public `easy` 300 条；之前已有结果目录中存在未完成和旧 schema fail 文件，不能代表最新代码。
- `compileall` 和单测通过不代表 official commonsense 通过。
- `23:59` 截断会让 schema pass 上升，但 commonsense/time 质量下降。
