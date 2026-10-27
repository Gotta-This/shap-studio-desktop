#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"
python prepare_assets.py
python -m PyInstaller --noconfirm --clean SHAPStudio.spec
echo "应用已生成：$(pwd)/dist/科研数据工具集.app"
