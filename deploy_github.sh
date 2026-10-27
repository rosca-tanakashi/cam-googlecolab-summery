#!/bin/bash

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
  git branch -M $BRANCH_NAME
fi

# 1.5. リモートoriginの設定
if git remote | grep origin > /dev/null; then
  git remote set-url origin $REMOTE_URL
else
  git remote add origin $REMOTE_URL
fi

# 2. すべてのファイルを追加
git add .

# 3. コミット（コミットメッセージは日付付きで自動生成）
git commit -m "Auto commit: $(date '+%Y-%m-%d %H:%M:%S')" || echo "コミットする変更がありません"

# 4. push（初回は--set-upstreamが必要な場合あり）
if git ls-remote --exit-code origin $BRANCH_NAME > /dev/null 2>&1; then
  git push origin $BRANCH_NAME
else
  git push -u origin $BRANCH_NAME
fi

echo "✅ GitHubへのアップロードが完了しました！"
