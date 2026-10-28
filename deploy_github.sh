#!/bin/bash
set -euo pipefail

# ユーザーが編集する部分
GITHUB_USER="rosca-tanakashi"
REPO_NAME="cam-googlecolab-summery"
BRANCH_NAME="master"  # 必要に応じて変更
REMOTE_URL="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

cd "$(dirname "$0")"

# 1. git初期化（.gitがなければ）
if [ ! -d .git ]; then
  echo "🔧 gitリポジトリを初期化します..."
  git init
  git branch -M "$BRANCH_NAME"
fi

# 1.5. リモートoriginの設定
if git remote | grep -q '^origin$'; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

# 2. すべてのファイルを追加
git add .

# 3. コミット（コミットメッセージは日付付きで自動生成）
if git diff --cached --quiet; then
  echo "コミットする変更がありません"
else
  git commit -m "Auto commit: $(date '+%Y-%m-%d %H:%M:%S')"
fi

# 4. リモートの先行コミットを取り込んでから push する
git fetch origin
if git ls-remote --exit-code origin "$BRANCH_NAME" > /dev/null 2>&1; then
  git pull --rebase origin "$BRANCH_NAME"
  git push origin "$BRANCH_NAME"
else
  git push -u origin "$BRANCH_NAME"
fi

echo "✅ GitHubへのアップロードが完了しました！"
