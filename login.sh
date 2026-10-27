#!/usr/bin/env bash
# 認証・ログイン
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

PY=".venv/Scripts/python"
if [[ ! -f "$PY" && ! -f "$PY.exe" ]]; then
  echo "仮想環境が見つかりません。python -m venv .venv のあと、依存パッケージを入れてください。"
  exit 1
fi

"$PY" colab_sync.py auth
