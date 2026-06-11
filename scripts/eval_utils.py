"""官方评测共享工具：路径解析、method 名、query 加载、结果生成。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_python_executable() -> str:
    """优先使用项目 .venv，避免系统 Python 缺依赖。"""
    venv_py = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    venv_py_win = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py_win.exists():
        return str(venv_py_win)
    return sys.executable

DEMO1_TRAINING_UIDS = [
    "20250324234255286741",
    "20250323022513877762",
    "20250322205522416056",
    "20250323133346744540",
    "20250325023523969179",
]


def load_project_config() -> dict:
    config_path = PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}


def resolve_chinatravel_root() -> Path | None:
    config = load_project_config()
    raw = (config.get("paths") or {}).get("chinatravel_root")
    candidates: list[Path] = []
    if raw:
        p = Path(raw)
        candidates.append(p if p.is_absolute() else PROJECT_ROOT / p)
    candidates.extend([PROJECT_ROOT / "ChinaTravel", PROJECT_ROOT.parent / "ChinaTravel"])
    for path in candidates:
        if (path / "chinatravel").exists() or (path / "eval_tpc.py").exists():
            return path
    return None


def effective_method_name(method: str, lang: str) -> str:
    """对齐 eval_tpc.py：--lang en 时自动追加 _en 后缀。"""
    if lang == "en" and not method.endswith("_en"):
        return method + "_en"
    return method


def official_results_dir(ct_root: Path, method: str, lang: str) -> Path:
    return ct_root / "results" / effective_method_name(method, lang)


def _load_json_query(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _search_training_data(uid: str) -> dict | None:
    training_dir = PROJECT_ROOT / "data" / "training data"
    return _load_json_query(training_dir / f"{uid}.json")


def load_official_split(
    split: str,
    limit: int = 0,
    ct_root: Path | None = None,
    lang: str = "en",
    *,
    preserve_hard_logic: bool = True,
) -> tuple[list[str], dict[str, dict]]:
    """加载官方 split 的 uid 列表及 query 数据。

    优先级：
        1. ChinaTravel load_query（HuggingFace / 本地 data）
        2. ChinaTravel default_splits + data 目录搜索
        3. tpc_agent/data/splits + data/training data（demo1_training_single 等）
    """
    if ct_root is None:
        ct_root = resolve_chinatravel_root()
    if ct_root is None:
        print("ERROR: 找不到 ChinaTravel 目录。")
        return [], {}

    oracle_translation = preserve_hard_logic

    try:
        ct_str = str(ct_root)
        if ct_str not in sys.path:
            sys.path.insert(0, ct_str)
        from chinatravel.data.load_datasets import load_query

        fake_args = SimpleNamespace(
            splits=split,
            lang=lang,
            oracle_translation=oracle_translation,
        )
        uids, query_data = load_query(fake_args)
        if uids and query_data:
            query_ids = uids[:limit] if limit > 0 else uids
            query_data = {k: v for k, v in query_data.items() if k in query_ids}
            if query_data:
                print(
                    f"加载 split={split}, {len(query_ids)} uids "
                    f"(via chinatravel load_query, found={len(query_data)})"
                )
                return query_ids, query_data
    except Exception as exc:
        print(f"官方 load_query 失败: {exc}, 回退到本地搜索...")

    split_sources = [
        ct_root / "chinatravel" / "evaluation" / "default_splits" / f"{split}.txt",
        PROJECT_ROOT / "data" / "splits" / f"{split}.txt",
    ]
    split_file = next((p for p in split_sources if p.exists()), None)
    if split_file is None:
        print(f"ERROR: split 文件不存在: {split}")
        return [], {}

    uids = [
        line.strip()
        for line in split_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if limit > 0:
        uids = uids[:limit]
    print(f"加载 split={split}, {len(uids)} uids (本地 split 文件)")

    query_data: dict[str, dict] = {}
    for uid in uids:
        if uid in query_data:
            continue
        for data_sub in ("chinatravel/data/en", "chinatravel/data"):
            data_root = ct_root / data_sub
            if not data_root.exists():
                continue
            for json_path in data_root.rglob(f"{uid}.json"):
                query_data[uid] = json.loads(json_path.read_text(encoding="utf-8"))
                break
            if uid in query_data:
                break
        if uid not in query_data:
            local_q = _search_training_data(uid)
            if local_q:
                query_data[uid] = local_q

    print(f"  找到 {len(query_data)} 条 query 数据")
    missing = set(uids) - set(query_data.keys())
    if missing:
        print(f"  WARNING: {len(missing)} 条 query 数据缺失")

    return uids, query_data


def check_plan_schema(plan: dict) -> list[str]:
    import re

    time_re = re.compile(r"^\d{2}:\d{2}$")
    issues: list[str] = []

    for field in ("people_number", "start_city", "target_city", "itinerary"):
        if field not in plan:
            issues.append(f"missing top: {field}")

    for day in plan.get("itinerary", []):
        for act in day.get("activities", []):
            for tf in ("start_time", "end_time"):
                t = act.get(tf, "")
                if t and not time_re.match(str(t)):
                    issues.append(f"day{day.get('day')} {act.get('type')} {tf}={t!r}")
            for seg in act.get("transports", []):
                for tf in ("start_time", "end_time"):
                    t = seg.get(tf, "")
                    if t and not time_re.match(str(t)):
                        issues.append(f"day{day.get('day')} transport {tf}={t!r}")
    return issues


def generate_official_results(
    *,
    split: str,
    limit: int = 10,
    method: str = "TPCAgent_TPCLLM",
    timeout: int = 300,
    lang: str = "en",
    resume: bool = False,
) -> dict[str, int]:
    """生成 plan 并写入 ChinaTravel/results/{method}_en/。"""
    try:
        from func_timeout import func_timeout, FunctionTimedOut
    except ImportError:
        FunctionTimedOut = TimeoutError

        def func_timeout(timeout, func, args=None, kwargs=None):
            return func(*(args or ()), **(kwargs or {}))

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    ct_root = resolve_chinatravel_root()
    if ct_root is None:
        raise RuntimeError("ChinaTravel 目录不可用")

    eff_method = effective_method_name(method, lang)
    results_dir = official_results_dir(ct_root, method, lang)
    results_dir.mkdir(parents=True, exist_ok=True)

    uids, query_data = load_official_split(split, limit, ct_root, lang=lang)
    if not uids:
        return {"total": 0, "succ": 0, "schema_ok": 0}

    from tpc_agent import TPCAgent
    from tpc_llm import TPCLLM

    agent = TPCAgent(
        env=None,
        backbone_llm=TPCLLM(),
        log_dir=str(results_dir),
        cache_dir=str(results_dir),
        lang=lang,
    )

    succ_count = schema_ok = total = 0
    for i, uid in enumerate(uids):
        print(f"[{i + 1}/{len(uids)}] {uid}", end=" ")
        out_path = results_dir / f"{uid}.json"
        if resume and out_path.exists():
            print("→ skip (exists)")
            continue

        query = query_data.get(uid)
        if query is None:
            print("→ SKIP (no query data)")
            continue

        total += 1
        try:
            succ, plan = func_timeout(
                timeout,
                agent.run,
                args=(query,),
                kwargs={"prob_idx": uid, "oralce_translation": False},
            )
        except FunctionTimedOut:
            succ, plan = False, {
                "people_number": query.get("people_number", 1),
                "start_city": query.get("start_city", ""),
                "target_city": query.get("target_city", ""),
                "itinerary": [],
                "error": f"timeout after {timeout}s",
            }
        except Exception as exc:
            succ, plan = False, {
                "people_number": query.get("people_number", 1),
                "start_city": query.get("start_city", ""),
                "target_city": query.get("target_city", ""),
                "itinerary": [],
                "error": f"{type(exc).__name__}: {exc}",
            }

        if succ:
            succ_count += 1
        issues = check_plan_schema(plan)
        if not issues:
            schema_ok += 1

        out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        tag = "OK" if not issues else f"schema issues: {issues[:3]}"
        print(f"→ succ={succ} {tag}")

    print("=" * 50)
    print(f"生成: {total}, 成功: {succ_count}, schema pass: {schema_ok}/{total}")
    print(f"结果目录: {results_dir}")
    return {"total": total, "succ": succ_count, "schema_ok": schema_ok}


def run_official_eval(
    *,
    split: str,
    method: str = "TPCAgent_TPCLLM",
    lang: str = "en",
) -> dict:
    """调用 ChinaTravel eval_tpc.py 并解析分数。"""
    import subprocess

    ct_root = resolve_chinatravel_root()
    if ct_root is None:
        raise RuntimeError("ChinaTravel 目录不可用")

    cmd = [
        resolve_python_executable(),
        str(ct_root / "eval_tpc.py"),
        "--splits",
        split,
        "--method",
        method,
        "--lang",
        lang,
    ]
    print(f"\n运行官方 eval:\n  {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        cwd=str(ct_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)

    scores: dict = {}
    score_file = ct_root / "your_tpc_scores.json"
    if score_file.exists():
        raw = score_file.read_text(encoding="utf-8").strip()
        # eval_tpc 以 append 模式写入，可能有多段 JSON 拼接
        for chunk in reversed(raw.replace("}{", "}\n{").splitlines()):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                scores = json.loads(chunk)
                break
            except json.JSONDecodeError:
                import ast
                try:
                    scores = ast.literal_eval(chunk)
                    break
                except (SyntaxError, ValueError):
                    continue

    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Mic.EPR"):
            scores.setdefault("MicEPR", float(line.split()[-1]))
        elif line.startswith("Mac.EPR:"):
            scores.setdefault("MacEPR", float(line.split()[-1]))
        elif line.startswith("C-LPR:"):
            scores.setdefault("C-LPR", float(line.split()[-1]))
        elif line.startswith("FPR:"):
            scores.setdefault("FPR", float(line.split()[-1]))
        elif line.startswith("Overall Score:"):
            scores.setdefault("overall", float(line.split()[-1]))

    scores["exit_code"] = proc.returncode
    scores["results_dir"] = str(official_results_dir(ct_root, method, lang))
    return scores
