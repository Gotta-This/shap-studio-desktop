#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"
python prepare_assets.py
python -m PyInstaller --noconfirm --clean SHAPStudio.spec
echo "应用已生成：$(pwd)/dist/SHAP分析工作台.app"
