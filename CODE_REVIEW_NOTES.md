# CODE_REVIEW_NOTES

审计角色：评测 / schema / diff 对齐 agent。未修改核心 planner / optimizer / repair 代码。

审计对象：Claude Code 最新一轮改动摘要，包括 `run_tpc.py`、时间格式修复、`world_env_client.select_intercity()`、官方结果同步脚本和 smoke runner。

## 结论

最新改动把“能生成 schema 合法 JSON”和“能被官方 eval 读取”推进了一步，但不能等价为算法优化已经生效。当前分数主要被 commonsense gate 卡住：hard logic 在样例上 6/6 通过，但因为 commonsense 没全过，官方 conditional C-LPR、FPR 都是 0。

## Findings

### P1. `scripts/run_official_eval_smoke.py` 的官方 loader 分支有运行时错误

位置：`scripts/run_official_eval_smoke.py:101-104`

```python
class _Args:
    splits = split
    lang = lang
    oracle_translation = False
```

实际运行：

```text
官方 load_query 失败: name 'lang' is not defined, 回退到本地搜索...
```

影响：

- smoke runner 没有真正走官方 `load_query()` 主路径，只是 fallback 到本地搜索。
- `oracle_translation=False` 还会导致官方 loader 删除 `hard_logic_py`，这和 `eval_tpc.py` 本地 split 的行为不完全一致。

给 Claude Code 的修改建议：

- 用实例对象或 `types.SimpleNamespace(splits=split, lang=lang)` 构造 args。
- 本地 hard-logic smoke 不要默认设置 `oracle_translation=False`，否则会误报 “hard_logic_py 不存在”。

### P1. smoke runner 的 `--lang en` 输出目录和官方 eval 读取目录不一致

位置：`scripts/run_official_eval_smoke.py:202`

```python
results_dir = ct_root / "results" / args.method
```

官方 `eval_tpc.py` 行为：

```python
if args.lang == "en" and not args.method.endswith("_en"):
    args.method += "_en"
```

影响：

- smoke runner 写入 `ChinaTravel/results/TPCAgent_TPCLLM/`。
- 官方命令 `python eval_tpc.py --splits demo1_training_single --method TPCAgent_TPCLLM --lang en` 实际读取 `ChinaTravel/results/TPCAgent_TPCLLM_en/`。
- 如果没有手动复制，eval 读到的可能是旧结果或空结果。

给 Claude Code 的修改建议：

- 当 `args.lang == "en"` 且 method 未以 `_en` 结尾时，smoke runner 也写入 `{method}_en`。
- 打印命令时明确真实目录：`ChinaTravel/results/{effective_method}`。

### P1. “不伪造 intercity ID” 还没有在代码层闭合

虽然当前样例输出拿到了真实车次 `D353` / `D3058`，但代码仍保留伪造 fallback：

- `src/planner/plan_utils.py:130`：`f"FL_{start}_{end}"`
- `src/planner/plan_utils.py:132`：`f"TR_{start}_{end}"`
- `src/data_layer/world_env_client.py:272-275`：缺 ID 时生成 `TR_...` / `FL_...`
- `src/data_layer/world_env_client.py:614-615`：JSON fallback 缺 `TrainID` 时生成 `TR_{sc}_{ec}`
- `src/repair/typed_repair.py:75`、`79`：FORMAT repair 会补 `FL_...` / `TR_...`

影响：

- Claude summary 中“所有后端失败返回 None 不伪造 ID”只对部分路径成立。
- 一旦数据源缺字段或 repair 触发，官方 intercity commonsense 仍会失败。

给 Claude Code 的修改建议：

- 正式模式下缺少真实 `TrainID` / `FlightID` 应返回 `None` 或触发重选，不应生成 `TR_` / `FL_`。
- repair 层不能为了 schema 补假 ID；应调用 `select_intercity()` 重查或删除不可验证城际交通。

### P1. 时间修复是 schema 级截断，不是排程级修复

位置：`src/planner/plan_utils.py:28-45`

`add_minutes()` 现在会把超过当天的时间截断到 `23:59`。这修掉了三位数小时 schema 问题，但实际样例仍出现大量 warning：

```text
add_minutes: 时间溢出 '23:07' + 60min = 24:07，截断到 23:59
add_minutes: 时间溢出 '18:40' + 871min = 33:11，截断到 23:59
```

样例 JSON 检查：

```text
invalid_times_count = 0
clipped_2359_count = 8
```

影响：

- schema 通过，但 official commonsense 的 chronological order、meal time、restaurant opening time、intercity duration 仍失败。
- Day 1 有多个活动 start/end 都是 `23:59`，这会造成“活动无耗时”和“到达晚于开始”。

给 Claude Code 的修改建议：

- 不要在底层时间函数吞掉跨日不可行状态。
- 在 day planner 中限制可安排候选：当天剩余时间不足时删除非必去 POI 或换更早城际交通。
- 返程 train 的真实 `EndTime` 跨日时，不应截断到 `23:59` 后继续声称同日完成。

### P2. `run_tpc.py` 官方输出对齐有进步，但还需区分语言和 split 类型

正向：

- `run_tpc.py` 已支持 `--official-results` / `--resume` / `--limit`。
- `--index 20250324234255286741` 能生成 `succ=True` 且 schema OK。
- 默认输出仍可写 `data/outputs/results/{method}/`，可用 `scripts/sync_results.py` 同步到官方目录。

风险：

- 英文数据必须用 `--lang en`，且结果目录必须是官方实际读取的 `{method}_en`。
- public `easy/medium/human` 的 hard logic 字段问题仍要单独说明，不能和本地 `demo1_training_single` 混为一谈。

### P2. 样例分数下降的直接原因不是 hard logic，而是 commonsense gate

官方英文评测结果：

```text
Schema: 100.0
Mic.EPR: 73.07692307692308
Mac.EPR: 0.0
Hard logic: 100.0 micro / 100.0 macro
C-LPR: 0.0
FPR: 0.0
Overall: 14.615384615384617
```

commonsense 失败列包括：

```text
Incorrect Information of Intercity Transport on price or duration
Visiting Restruants in their closed time
Repeated Restruants Choices
Inappropriate Meal Times
Incorrect cost information of Inner-City Transport
Does not follow Chronological Order
Invalid Transport information across positions
```

核心解释：

- hard logic 过了，但 official `C-LPR` 是 conditional，只有 commonsense pass 的样本才计入。
- 当前样例 `commonsense_pass_id=[]`，所以 `C-LPR=0`、`FPR=0`。

### P2. `--lang zh` 评测英文样例会得到异常/NaN，不应作为正式分数

官方默认 `--lang zh` 跑 `demo1_training_single`：

```text
Mic.EPR nan
Mac.EPR: 0.0
C-LPR: 0.0
FPR: 0.0
Overall Score: nan
```

定位：

- query 和 plan 是英文城市名 `Suzhou` / `Chengdu`。
- `zh` 工具表用中文 key，commonsense 内部触发 `KeyError('Suzhou','Chengdu')` / `KeyError('Chengdu')`。
- 官方代码吞掉异常，导致 commonsense 统计列为空，micro accuracy 除以 0。

给 Claude Code 的修改建议：

- 本地英文 split 统一用 `--lang en`。
- 中文 split 才用默认 `zh`。
- 报告中禁止把 `zh` 的 `nan`、`en` 的真实分数、public HF split 的 KeyError 混成一个结论。

## 给 Claude Code 的下一步约束

1. 先修评测链路：smoke runner 的 `lang`、`oracle_translation`、`_en` 输出目录。
2. 再修输出真实性：删除正式路径中的 `FL_` / `TR_` 伪造 fallback。
3. 再修排程：不要用 `23:59` 截断掩盖跨日和不可行时间。
4. 再修 commonsense：餐厅不重复、餐点时段、同城交通 `cost=price*tickets/cars`、活动前到达、返程交通和前一活动之间空间衔接。
5. 算法层优化要以 official commonsense pass 为第一目标，否则 hard logic 再高也不会进入 C-LPR/FPR。
