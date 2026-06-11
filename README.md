# TPC Agent — IJCAI 2026 旅行规划挑战赛

基于约束驱动 + 多策略滚动规划的旅行行程自动生成 Agent。

**仓库**: [KevinYin856/TPC](https://github.com/KevinYin856/TPC)

## 总流程

```
用户自然语言需求
  → 约束卡片抽取 (hard_logic DSL + NL parser)
  → 主动约束获取（风险驱动 Active SLAM）
  → 语义落地与偏好权重
  → 候选池构建 (POI/酒店/餐厅/交通)
  → [多策略] 多日任务分配 → 滚动逐日规划 → 日内路线优化
  → 时间表生成 → 预算控制 → 本地检查
  → 官方格式 → 官方 verifier → 类型化修复
  → 多候选择优 → 最终输出
```

## 快速开始

```bash
cd /path/to/tpc_agent

# 推荐：项目内虚拟环境（避免系统 Python 权限/缺包问题）
bash scripts/install_deps.sh
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 或使用已有 conda 环境
# conda activate dl_env
```

### 跑单条 query (本地 training 模式)

```bash
python run_tpc.py --splits training --index 20250324234255286741 --timeout 300
```

输出: `data/outputs/results/TPCAgent_TPCLLM/{uid}.json`

### 跑官方 split（直接可 eval）

```bash
python run_tpc.py --splits easy --limit 10 --official-results --lang en
```

输出: `ChinaTravel/results/TPCAgent_TPCLLM_en/{uid}.json`

### P0 官方评测（一键）

```bash
# 1) 初始化 demo1 split（含 hard_logic_py，从本地 training data 同步）
python scripts/setup_demo1_split.py

# 2) 生成结果 + 跑 eval_tpc.py + 输出 FPR 报告（建议用 .venv）
.venv/bin/python scripts/run_official_eval_batch.py --split demo1_training_single --limit 5 --lang en

# 或分步：
python scripts/run_official_eval_smoke.py --split demo1_training_single --limit 5 --lang en
cd ../ChinaTravel && python eval_tpc.py --splits demo1_training_single --method TPCAgent_TPCLLM --lang en
```

报告保存在 `data/outputs/eval_report.json`。

有效分数（英文）：

```
Mic.EPR = 80.0
C-LPR   = 0.0 (被 commonsense gate 阻塞)
FPR     = 0.0
Overall = 16.0
```

## 验收命令

**以下命令必须在 `tpc_agent` 目录下执行**（先 `cd` 到本仓库根目录）：

```bash
cd /path/to/tpc_agent

pip install -r requirements.txt

python -m compileall .
python src/constraints/test_constraints.py
python src/data_layer/test_data_layer.py
python src/candidates/test_candidates.py
python src/active/test_active.py
python src/adapter/test_adapter.py
```

官方 smoke / 公开 split（`datasets` 用于 HuggingFace 下载 zh query）：

```bash
python scripts/run_official_eval_smoke.py --split demo1_training_single --limit 5 --lang en
python scripts/run_official_eval_batch.py --split easy --limit 3 --lang zh
```

本地单条快速验证（不依赖 ChinaTravel 官方 data）：

```bash
python run_tpc.py --splits training --index 20250324234255286741 --lang en
```

## 目录结构

```
demo1/
  main.py                      # solve_one_query() 总入口
  run_tpc.py                   # 批量运行（对齐官方 run_tpc.py）
  config.yaml                  # 全局配置
  tpc_agent.py / tpc_llm.py    # 官方 Agent/LLM 适配器
  eval_local.py                # 本地评估脚本
  src/
    data_layer/                # schema / 数据加载 / WorldEnv 客户端 / Chinatravel 桥接
    constraints/               # 约束卡片抽取（hard_logic DSL + NL regex）
    active/                    # 主动约束获取 (Active SLAM: belief/action/info_gain)
    semantic/                  # 语义落地（菜系/节奏/偏好权重）
    candidates/                # 候选池构建（MMR 多样化 + 预算/类型过滤）
    planner/                   # 多日任务分配 + 滚动逐日规划 (plan_builder)
    optimizer/                 # 日内路线优化 (NN + 2-opt + ACO)
    scheduler/                 # 时间表 + 预算控制
    repair/                    # 类型化修复 (typed_repair: 8 类错误分派)
    skills/                    # 旅行规划师技能库 (stub, 待实现)
    search/                    # 多候选搜索 (stub, 待实现)
    verifier/                  # 本地检查 + eval bridge
    submission/                # 官方格式输出 + schema 校验
    experiments/               # 实验日志
  scripts/
    setup_demo1_split.py       # 初始化 demo1_training_single + 同步 query
    run_official_eval_batch.py # P0：生成 + eval + FPR 报告
    run_official_eval_smoke.py # 官方 split smoke runner
    sync_results.py            # 同步本地结果到 ChinaTravel/results/（--lang en）
    eval_utils.py              # 评测共享工具
  EVAL_ALIGNMENT_REPORT.md     # 评测对齐审计报告
  CODE_REVIEW_NOTES.md         # 代码审查笔记
  TEST_RESULTS.md              # 测试结果记录
  README_REQUIREMENT_MATRIX.md # 需求矩阵审计
```

## ChinaTravel 环境

1. Clone 官方仓库: `git clone https://github.com/LAMDA-NeSy/ChinaTravel.git` 到 `demo1/ChinaTravel/`
2. 下载数据库到 `chinatravel/environment/database_en/`
3. 安装依赖: `pip install datasets tqdm pandas numpy jsonschema geopy pyyaml`
4. 验证: `python -c "from src.data_layer.world_env_client import get_chinatravel_status; print(get_chinatravel_status())"`

## 已知阻塞

| 阻塞项 | 说明 |
|--------|------|
| Commonsense gate | hard logic 实际通过但 commonsense 未全过 → conditional C-LPR/FPR 为 0 |
| public easy/medium/human | 缺 `hard_logic_py` 字段，无法完整跑官方 hard constraints |
| 时间溢出 | `add_minutes` 溢出抛 RuntimeError，planner 跳过溢出 POI，部分活动仍被跳过 |
| 餐厅/酒店数据 | WorldEnv 不可用时使用占位符，导致 commonsense 校验失败 |
| skills/ 目录 | 7 个技能函数全为 stub |
| search/ 目录 | multi_candidate_search / plan_selector / policy_generator 全为 stub |

## 同步到 GitHub

```bash
git add -A
git commit -m "描述改动"
git push origin main
```
