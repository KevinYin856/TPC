#!/usr/bin/env bash
# 在项目内创建 .venv 并安装依赖（避免系统 Python 权限/缺包问题）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d .venv ]; then
  echo "创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi

PY="$ROOT/.venv/bin/python"
PIP="$ROOT/.venv/bin/pip"

"$PIP" install --upgrade pip
"$PIP" install --resume-retries 5 -r requirements.txt

echo ""
echo "安装完成。激活环境："
echo "  source $ROOT/.venv/bin/activate"
echo ""
echo "验证："
"$PY" -c "import datasets, tqdm, jsonschema; print('deps OK')"
"$PY" -c "from src.data_layer.world_env_client import get_chinatravel_status; print(get_chinatravel_status())"
