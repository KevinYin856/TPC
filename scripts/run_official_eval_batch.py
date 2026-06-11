#!/usr/bin/env python3
"""P0 官方评测一键脚本：生成结果 → eval_tpc.py → 输出 FPR 报告。

用法::

    # 首次：初始化 demo1_training_single 数据
    python scripts/setup_demo1_split.py

    # 生成 + 评测（推荐，含 hard_logic_py）
    python scripts/run_official_eval_batch.py --split demo1_training_single --limit 5 --lang en

    # 仅评测已有结果
    python scripts/run_official_eval_batch.py --split demo1_training_single --skip-gen --lang en

    # 公开 easy split（zh，HuggingFace 自动下载 query）
    python scripts/run_official_eval_batch.py --split easy --limit 3 --lang zh
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.eval_utils import (
    effective_method_name,
    generate_official_results,
    load_official_split,
    resolve_chinatravel_root,
    run_official_eval,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="官方评测批量：生成 + eval_tpc.py")
    parser.add_argument("--split", type=str, default="demo1_training_single")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--method", "-m", type=str, default="TPCAgent_TPCLLM")
    parser.add_argument("--timeout", "-t", type=int, default=300)
    parser.add_argument("--lang", choices=["zh", "en"], default="en")
    parser.add_argument("--resume", action="store_true", help="跳过已有结果")
    parser.add_argument("--skip-gen", action="store_true", help="跳过生成，仅跑 eval")
    parser.add_argument("--skip-eval", action="store_true", help="仅生成，不跑 eval")
    args = parser.parse_args()

    ct_root = resolve_chinatravel_root()
    if ct_root is None:
        print("FATAL: ChinaTravel 目录不可用（检查 config.yaml）")
        sys.exit(1)

    eff = effective_method_name(args.method, args.lang)
    print(f"split={args.split}, method={args.method} → results/{eff}/, lang={args.lang}")

    uids, query_data = load_official_split(
        args.split, args.limit, ct_root, lang=args.lang
    )
    if not uids:
        if args.split == "demo1_training_single":
            print("\n提示: 先运行 python scripts/setup_demo1_split.py")
        sys.exit(1)

    has_hard_logic = any(q.get("hard_logic_py") for q in query_data.values())
    if has_hard_logic:
        print(f"hard_logic_py: 可用 ({sum(1 for q in query_data.values() if q.get('hard_logic_py'))} 条)")
    else:
        print("⚠️  当前 split 无 hard_logic_py，C-LPR/FPR 可能为 0")

    if not args.skip_gen:
        stats = generate_official_results(
            split=args.split,
            limit=args.limit,
            method=args.method,
            timeout=args.timeout,
            lang=args.lang,
            resume=args.resume,
        )
        if stats["total"] == 0:
            print("无新结果生成。")
            if not args.skip_eval:
                print("尝试对已有结果跑 eval...")

    if args.skip_eval:
        return

    scores = run_official_eval(
        split=args.split,
        method=args.method,
        lang=args.lang,
    )

    print("\n" + "=" * 50)
    print("评测分数摘要")
    print("=" * 50)
    for key in ("MicEPR", "MacEPR", "C-LPR", "FPR", "overall"):
        if key in scores:
            print(f"  {key}: {scores[key]}")
    if scores.get("results_dir"):
        print(f"  results_dir: {scores['results_dir']}")

    report_path = PROJECT_ROOT / "data" / "outputs" / "eval_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "split": args.split,
        "method": args.method,
        "effective_method": eff,
        "lang": args.lang,
        "limit": args.limit,
        "uids": uids[: args.limit] if args.limit else uids,
        "has_hard_logic_py": has_hard_logic,
        "scores": scores,
    }
    def _json_default(obj):
        if hasattr(obj, "item"):
            return obj.item()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(f"\n报告已保存: {report_path}")

    if scores.get("exit_code", 0) != 0:
        sys.exit(scores["exit_code"])


if __name__ == "__main__":
    main()
