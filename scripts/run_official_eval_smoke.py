"""Official eval smoke runner — 用 ChinaTravel 官方 split 生成结果并检查 schema。

用法::

    python scripts/setup_demo1_split.py   # 首次初始化 demo1 split
    python scripts/run_official_eval_smoke.py --split demo1_training_single --limit 5 --lang en
    python scripts/run_official_eval_smoke.py --split easy --limit 3 --lang zh
"""

from __future__ import annotations

import argparse
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
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Official eval smoke runner")
    parser.add_argument("--split", type=str, default="demo1_training_single")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--method", "-m", type=str, default="TPCAgent_TPCLLM")
    parser.add_argument("--timeout", "-t", type=int, default=300)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--lang", choices=["zh", "en"], default="en")
    args = parser.parse_args()

    ct_root = resolve_chinatravel_root()
    if ct_root is None:
        print("FATAL: ChinaTravel 目录不可用。")
        sys.exit(1)

    uids, query_data = load_official_split(args.split, args.limit, ct_root, lang=args.lang)
    if not uids:
        if args.split == "demo1_training_single":
            print("提示: 先运行 python scripts/setup_demo1_split.py")
        return

    has_hard_logic = any(q.get("hard_logic_py") for q in query_data.values())
    if not has_hard_logic:
        print(
            "\n⚠️  当前 split 无 hard_logic_py，C-LPR/FPR 将无法完整计算。\n"
            "   推荐使用 demo1_training_single（先 setup_demo1_split.py）。\n"
        )

    generate_official_results(
        split=args.split,
        limit=args.limit,
        method=args.method,
        timeout=args.timeout,
        lang=args.lang,
        resume=args.resume,
    )

    eff = effective_method_name(args.method, args.lang)
    eval_cmd = (
        f"cd {ct_root} && python eval_tpc.py "
        f"--splits {args.split} --method {args.method} --lang {args.lang}"
    )
    print(f"\n官方 eval 命令:\n  {eval_cmd}")
    if eff != args.method:
        print(f"  实际读取目录: ChinaTravel/results/{eff}/")
    print(
        "\n或一键生成+评测:\n"
        f"  python scripts/run_official_eval_batch.py "
        f"--split {args.split} --limit {args.limit} --lang {args.lang}"
    )


if __name__ == "__main__":
    main()
