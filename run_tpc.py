"""本地批量运行脚本，接口对齐 ChinaTravel run_tpc.py。

用法::

    python run_tpc.py --splits training --agent TPCAgent --llm TPCLLM
    python run_tpc.py --splits training --index 20250324234255286741

结果写入：data/outputs/results/TPCAgent_TPCLLM/{uid}.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 项目根目录加入 path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from func_timeout import func_timeout, FunctionTimedOut
except ImportError:
    # 无 func_timeout 时用简易 fallback
    FunctionTimedOut = TimeoutError

    def func_timeout(timeout, func, args=None, kwargs=None):
        return func(*(args or ()), **(kwargs or {}))


from tpc_agent import TPCAgent
from tpc_llm import TPCLLM


def _load_config() -> dict:
    config_path = PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}


def load_split_queries(splits: str, single_uid: str | None = None) -> tuple[list[str], dict[str, dict]]:
    """加载 split 对应的 query 列表。

    查找顺序：
        1. data/splits/{splits}.txt  （每行一个 uid；空文件则扫描 training data）
        2. data/training data/       （当 splits=training 时扫描全部 json）
        3. chinatravel 官方路径（若存在）
    """
    query_data: dict[str, dict] = {}
    query_ids: list[str] = []
    training_dir = PROJECT_ROOT / "data" / "training data"

    # 单条 uid 模式：直接加载对应文件
    if single_uid:
        query_ids = [single_uid]
        for base in (training_dir,):
            path = base / f"{single_uid}.json"
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    query_data[single_uid] = json.load(f)
                return query_ids, query_data
        # 尝试 chinatravel 官方 data 目录
        ct_data = PROJECT_ROOT.parent / "ChinaTravel" / "chinatravel" / "data"
        if ct_data.exists():
            for sub in ct_data.iterdir():
                candidate = sub / f"{single_uid}.json"
                if candidate.exists():
                    with open(candidate, encoding="utf-8") as f:
                        query_data[single_uid] = json.load(f)
                    return query_ids, query_data
        return query_ids, query_data

    split_file = PROJECT_ROOT / "data" / "splits" / f"{splits}.txt"

    if split_file.exists():
        with open(split_file, encoding="utf-8") as f:
            query_ids = [line.strip() for line in f if line.strip()]

    if not query_ids and splits == "training" and training_dir.exists():
        query_ids = sorted(p.stem for p in training_dir.glob("*.json"))
    elif not query_ids:
        # 尝试 chinatravel 官方 split
        ct_split = PROJECT_ROOT.parent / "ChinaTravel" / "chinatravel" / "evaluation" / "default_splits" / f"{splits}.txt"
        ct_data = PROJECT_ROOT.parent / "ChinaTravel" / "chinatravel" / "data"
        if ct_split.exists():
            with open(ct_split, encoding="utf-8") as f:
                query_ids = [line.strip() for line in f if line.strip()]
            for uid in query_ids:
                for sub in ct_data.iterdir():
                    candidate = sub / f"{uid}.json"
                    if candidate.exists():
                        with open(candidate, encoding="utf-8") as f:
                            query_data[uid] = json.load(f)
                        break
            return query_ids, query_data

    # 从 training data 加载
    for uid in query_ids:
        path = training_dir / f"{uid}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                query_data[uid] = json.load(f)

    return query_ids, query_data


def save_json(data: dict, path: Path) -> None:
    """保存 JSON 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="TPC Agent 批量运行（对齐官方 run_tpc.py）")
    parser.add_argument("--splits", "-s", type=str, default="training", help="split 名称")
    parser.add_argument("--index", "-id", type=str, default=None, help="只跑指定 uid")
    parser.add_argument("--skip", "-sk", type=int, default=0, help="1=跳过已有结果")
    parser.add_argument("--agent", "-a", type=str, default="TPCAgent")
    parser.add_argument("--llm", "-l", type=str, default="TPCLLM")
    parser.add_argument("--timeout", "-t", type=int, default=300, help="单条 query 超时秒数")
    parser.add_argument("--lang", choices=["zh", "en"], default="zh")
    parser.add_argument("--oracle_translation", action="store_true", help="本地 debug：保留 hard_logic_py")
    args = parser.parse_args()

    config = _load_config()
    timeout = args.timeout or config.get("adapter", {}).get("timeout_sec", 300)

    query_ids, query_data = load_split_queries(args.splits, single_uid=args.index)
    if args.index:
        query_ids = [args.index]
        if args.index not in query_data:
            # 再次尝试加载指定 uid
            ids, data = load_split_queries(args.splits, single_uid=args.index)
            query_data.update(data)

    print(f"加载 {len(query_ids)} 条 query (split={args.splits})")

    method = f"{args.agent}_{args.llm}"
    if args.oracle_translation:
        method += "_oracletranslation"

    results_dir = PROJECT_ROOT / "data" / "outputs" / "results" / method
    log_dir = PROJECT_ROOT / "data" / "outputs" / "cache" / method
    results_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    print(f"results_dir: {results_dir}")
    print(f"log_dir:     {log_dir}")

    agent = TPCAgent(
        env=None,
        backbone_llm=TPCLLM(),
        log_dir=str(log_dir),
        cache_dir=str(log_dir),
        lang=args.lang,
    )

    succ_count, eval_count = 0, 0

    for i, uid in enumerate(query_ids):
        print("-" * 40)
        print(f"Process [{i + 1}/{len(query_ids)}], Success [{succ_count}/{eval_count}]")
        print(f"uid: {uid}")

        out_path = results_dir / f"{uid}.json"
        if args.skip and out_path.exists():
            print("skip (exists)")
            continue

        if uid not in query_data:
            print(f"WARNING: query 数据缺失，跳过 {uid}")
            continue

        eval_count += 1
        query_i = query_data[uid]

        try:
            succ, plan = func_timeout(
                timeout,
                agent.run,
                args=(query_i,),
                kwargs={"prob_idx": uid, "oralce_translation": args.oracle_translation},
            )
        except FunctionTimedOut:
            succ, plan = False, {
                "people_number": query_i.get("people_number", 1),
                "start_city": query_i.get("start_city", ""),
                "target_city": query_i.get("target_city", ""),
                "itinerary": [],
                "error": f"timeout after {timeout}s",
            }
        except Exception as exc:
            succ, plan = False, {
                "people_number": query_i.get("people_number", 1),
                "start_city": query_i.get("start_city", ""),
                "target_city": query_i.get("target_city", ""),
                "itinerary": [],
                "error": str(exc),
            }

        if succ:
            succ_count += 1

        save_json(plan, out_path)
        print(f"succ={succ}, saved -> {out_path}")

    print("=" * 40)
    print(f"完成: {succ_count}/{eval_count} 成功")


if __name__ == "__main__":
    main()
