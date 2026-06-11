#!/usr/bin/env python3
"""将本地 results 同步到 ChinaTravel/results/（支持 --lang en → _en 目录）。

用法::

    python scripts/sync_results.py --method TPCAgent_TPCLLM --lang en
    python scripts/sync_results.py --method TPCAgent_TPCLLM --uid 20250324234255286741
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.eval_utils import effective_method_name, resolve_chinatravel_root


def main() -> None:
    parser = argparse.ArgumentParser(description="同步结果到 ChinaTravel/results/")
    parser.add_argument("--method", "-m", default="TPCAgent_TPCLLM")
    parser.add_argument("--lang", choices=["zh", "en"], default="zh")
    parser.add_argument("--uid", default=None, help="只同步指定 uid")
    parser.add_argument("--source-dir", default=None)
    args = parser.parse_args()

    ct_root = resolve_chinatravel_root()
    if ct_root is None:
        print("ERROR: ChinaTravel 不可用。")
        sys.exit(1)

    src_method = args.method
    dst_method = effective_method_name(args.method, args.lang)

    if args.source_dir:
        src_dir = Path(args.source_dir)
    else:
        src_dir = PROJECT_ROOT / "data" / "outputs" / "results" / src_method

    if not src_dir.exists():
        print(f"ERROR: 源目录不存在: {src_dir}")
        sys.exit(1)

    dst_dir = ct_root / "results" / dst_method
    dst_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    candidates = [Path(f"{args.uid}.json")] if args.uid else sorted(src_dir.glob("*.json"))

    for p in candidates:
        src_path = src_dir / p if args.uid else p
        if not src_path.exists():
            print(f"WARNING: 源文件不存在: {src_path}")
            continue
        dst_path = dst_dir / src_path.name
        shutil.copy2(src_path, dst_path)
        count += 1
        if count <= 5 or count % 100 == 0:
            print(f"  {src_path.name} → {dst_path}")

    print(f"\n同步完成: {count} 文件 → {dst_dir}")
    if dst_method != src_method:
        print(f"  (--lang {args.lang}: {src_method} → {dst_method})")


if __name__ == "__main__":
    main()
