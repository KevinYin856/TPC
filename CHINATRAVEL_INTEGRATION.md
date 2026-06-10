# 复制到 ChinaTravel 官方仓库

将本目录 **全部内容** 复制到::

    ChinaTravel/chinatravel/agent/tpc_agent/

确保包含::

    tpc_agent.py      # TPCAgent 类（官方 run_tpc.py 调用）
    tpc_llm.py        # TPCLLM 类
    src/              # 你的算法实现
    config.yaml
    requirements.txt

## 官方运行命令

在 ChinaTravel 根目录::

    python run_tpc.py --splits tpc_aic_phase1 --agent TPCAgent --llm TPCLLM

## 本地独立运行（不依赖 ChinaTravel）

在本目录::

    python run_tpc.py --splits training --agent TPCAgent --llm TPCLLM
    python run_tpc.py --splits training --index 20250324234255286741

结果::

    data/outputs/results/TPCAgent_TPCLLM/{uid}.json

## 接口约定

TPCAgent.run(query, prob_idx, oralce_translation) -> (succ, plan_dict)

plan_dict 顶层字段::

    people_number, start_city, target_city, itinerary, elapsed_time(sec)

与 chinatravel/evaluation/output_schema.json 一致。
