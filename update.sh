#!/bin/bash
# myou-data-research 更新脚本（给已安装的使用者）
# 用法：
#   1. 自然语言：对 AI Agent 说「帮我更新 myou-data-research 数据调研工具」
#   2. 手动：在 skill 安装目录下执行 `bash update.sh`
#
# 原理：从 GitHub 拉取最新版本，覆盖当前安装（保留本地 reports/ 生成物）
# 注意：本脚本设计用于「安装目录」（无 .git 的复制品）。开发者仓库请用 git pull。
set -e

REPO="https://github.com/modayishujia/myou-data-research.git"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "==> 拉取最新版本..."
if ! git clone --depth 1 --quiet "$REPO" "$TMP_DIR"; then
  echo "✗ 拉取失败，请检查网络后重试"
  exit 1
fi

echo "==> 更新文件..."
# 删除旧内容，但保留：本地调研产物 reports/、隐藏的 .git、以及正在运行的 update.sh
find . -maxdepth 1 -mindepth 1 \
  \( -name 'reports' -o -name '.git' -o -name 'update.sh' \) -prune -o \
  -exec rm -rf {} +

# 复制新版本（不含 .git），update.sh 会被新版覆盖
rm -rf "$TMP_DIR/.git"
cp -r "$TMP_DIR/." .

echo "==> 安装依赖..."
pip3 install -q -r requirements.txt 2>/dev/null || echo "  (依赖已就绪或跳过)"

echo ""
echo "✅ myou-data-research 已更新到最新版本"
echo "   验证：SKILL.md 的 name 应为 myou-data-research"
