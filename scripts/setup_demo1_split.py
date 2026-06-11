#!/usr/bin/env python3
"""初始化 demo1_training_single split：供官方 eval 读取 hard_logic_py query。

将 tpc_agent/data/training data/ 中的样本复制到 ChinaTravel 官方 data 目录，
并创建 default_splits/demo1_training_single.txt。

用法::

    python scripts/setup_demo1_split.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.eval_utils import DEMO1_TRAINING_UIDS, resolve_chinatravel_root


def main() -> None:
    ct_root = resolve_chinatravel_root()
    if ct_root is None:
        print("ERROR: ChinaTravel 不可用，请检查 config.yaml paths.chinatravel_root")
        sys.exit(1)

    training_dir = PROJECT_ROOT / "data" / "training data"
    if not training_dir.exists():
        print(f"ERROR: 本地 training data 不存在: {training_dir}")
        sys.exit(1)

    split_dir = ct_root / "chinatravel" / "evaluation" / "default_splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    split_file = split_dir / "demo1_training_single.txt"
    split_file.write_text("\n".join(DEMO1_TRAINING_UIDS) + "\n", encoding="utf-8")
    print(f"写入 split: {split_file}")

    local_split = PROJECT_ROOT / "data" / "splits"
    local_split.mkdir(parents=True, exist_ok=True)
    (local_split / "demo1_training_single.txt").write_text(
        split_file.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print(f"写入本地 split: {local_split / 'demo1_training_single.txt'}")

    dst_dir = ct_root / "chinatravel" / "data" / "en" / "demo1_training"
    dst_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for uid in DEMO1_TRAINING_UIDS:
        src = training_dir / f"{uid}.json"
        if not src.exists():
            print(f"WARNING: 缺失 {src}")
            continue
        shutil.copy2(src, dst_dir / f"{uid}.json")
        copied += 1
        print(f"  {uid}.json → {dst_dir / f'{uid}.json'}")

    print(f"\n完成: {copied}/{len(DEMO1_TRAINING_UIDS)} 条 query 已同步到 ChinaTravel")
    print(
        "\n下一步:\n"
        "  python scripts/run_official_eval_batch.py "
        "--split demo1_training_single --limit 5 --lang en"
    )


if __name__ == "__main__":
    main()
