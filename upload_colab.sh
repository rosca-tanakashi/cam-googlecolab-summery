#!/usr/bin/env bash
# Colabのアップロード
# 使い方:
#   bash upload_colab.sh
#   bash upload_colab.sh notebooks/延長確認シート作成_ver.3.0.ipynb
#   bash upload_colab.sh 延長確認シート作成_ver.3.0.ipynb
#   bash upload_colab.sh notebooks/上・下延長確認メール送付＆Salesforce取込_ver.1.0.ipynb
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "使い方: bash upload_colab.sh [ノートブック.ipynb]"
  echo "引数なしでは登録済みの全件をアップロードします。"
  exit 0
fi

if [[ $# -gt 1 ]]; then
  echo "指定できるノートブックは1件です。"
  echo "使い方: bash upload_colab.sh [ノートブック.ipynb]"
  exit 1
fi

PY=".venv/Scripts/python"
if [[ ! -f "$PY" && ! -f "$PY.exe" ]]; then
  echo "仮想環境が見つかりません。python -m venv .venv のあと、依存パッケージを入れてください。"
  exit 1
fi

if [[ $# -eq 1 ]]; then
  "$PY" colab_sync.py upload --file "$1"
else
  "$PY" colab_sync.py upload
fi
