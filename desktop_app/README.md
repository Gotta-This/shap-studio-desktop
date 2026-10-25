# SHAP 分析工作台

离线桌面应用，完整保留原 Notebook 的模拟数据生成、逻辑回归、模型评估、单样本预测和六类 SHAP 图。

## 使用

1. 打开 `dist/SHAP分析工作台.app`（当前构建为 Apple 芯片 Mac 版本，内置 Python，无需另行安装环境）。
2. 在“数据参数”中配置所有特征。连续变量的阳性组和阴性组均有独立的均值、标准差、上下限；可设置向零取整、四舍五入和保留小数位数。二分类变量可设置编码及两组概率。
3. 在“模型与解释”中配置划分比例、种子、逻辑回归、决策阈值和 SHAP 背景样本数。
4. 在“图表样式”中调整公共样式。选择某张图，勾选“单独设置”可覆盖该图的每一项颜色、字体、字号、线宽、散点、尺寸等参数。“本图参数”中可开关图表、修改标题和文件名、选择依赖图展示或交互着色特征。
5. 选择保存目录并点击“生成数据并分析”。每次运行保存到独立的时间戳目录，不覆盖旧结果。
6. 查看图表大图、完整数据、模型评估、系数和逐行预测。可另存单张图片或完整结果。

只修改图表样式时，可在概览页“使用已有模型重新绘图”，无需重新训练。更改数据或模型参数后需要完整运行。

## 所有数据设置

- 样本量、阳性比例、数据种子。
- 特征的数量、顺序、名称与类型；可添加或删除连续/二分类特征，并通过上移、下移调整顺序。
- 每个连续特征阳性/阴性组各自的均值、标准差、clip 下限、clip 上限。
- 每个连续特征的数值处理方式和小数位数。
- 每个二分类特征的两个数值编码及阳性/阴性组取第二个编码的概率。
- 结局列名、阴性/阳性显示名称；结局固定编码 0/1。
- ID 列名、前缀、补零位数、起始编号。

阳性人数按 `int(样本量 × 阳性比例)` 计算。分布是正态抽样后限幅，不是截断正态分布。向零取整与四舍五入有区别。默认数据值、训练集划分和模型与原 Notebook 保持一致。

## 保存内容

- `parameters.json`：全部参数快照，可重新载入。
- `data.csv` 与 `clinical_prediction_dataset_with_protective.xlsx`：全部模拟数据。
- `analysis_results.xlsx`：数据、系数、测试集预测、分类报告、混淆矩阵。
- `coefficients.csv`、`test_predictions.csv`、`shap_values.csv`、`feature_importance.csv`。
- `figures/`：PNG 预览及选择的 SVG/PDF。每张图可单独开关。
- `metrics.json`、`运行报告.txt`、`color_verification.json`、`versions.json`。

颜色核对比较绘图对象与配置；PNG 同时记录像素证据。透明度、抗锯齿、重叠或不可见元素会影响像素是否命中，不把缺少单个纯色像素直接等同于对象配色错误。

## 开发与构建

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python prepare_assets.py
python main.py
python -m unittest discover -s tests -v
python -m PyInstaller --noconfirm SHAPStudio.spec
```

打包环境自检：

```sh
dist/SHAP分析工作台.app/Contents/MacOS/SHAP分析工作台 --self-test ./packaged-verification
```

Windows 需要在 Windows 环境独立构建与验证。当前 Mac 包为本地构建、临时签名，没有 Apple 开发者证书签名或公证；没有宣称可直接通过其他电脑的 Gatekeeper 检查。

Windows x64 的 GitHub Actions、便携版和安装程序流程见 [WINDOWS.md](WINDOWS.md)。构建过程会下载并核验固定 SHA256 的开源字体，成品运行时无需联网。

完整安装包界面回归：`QT_QPA_PLATFORM=offscreen dist/SHAP分析工作台.app/Contents/MacOS/SHAP分析工作台 --ui-verify ./ui-evidence`。该流程在后台操作 Qt 控件和保存对话框，不控制用户桌面；核对所有数据、六张图的独立颜色/字体/字号/线宽，以及另存配置、单图与完整结果。

中文字体使用系统中可用的字体，并随包附带 Noto Sans CJK SC 作为后备（许可证见 assets/FONT-LICENSE.txt）。不需联网下载字体。

## 分析含义

默认使用模拟数据、一次分层留出划分、L2 正则化逻辑回归、独立背景的 Linear SHAP。SHAP 解释的是 log-odds。默认年龄分布沿用原代码，因此可能出现年龄负系数。模型系数绝对值受量纲影响；本应用没有执行系数显著性检验或置信区间估计。

## 数据工具集

左侧“数据工具集”提供两个独立工具，无需运行模型：

- **自定义类别数列**：增删数字及其数量，固定各类数量后随机打乱；可选种子，与 HTML 第一个工具使用相同算法，具体排列不与 R 的种子算法兼容。默认 28 个 1、93 个 0，共 121 个。
- **均数 / 标准差模拟数据**：按均数、样本标准差、例数、小数位和可选上下限近似生成，或在完整上下限内均匀随机生成。显示实际统计值与偏差；不保证正态分布。

结果可按每行一个、逗号、空格或 R 向量格式一键复制。参数与结果在工具切换及载入 SHAP 配置时保留。工具参数独立于 SHAP 分析配置，分析配置文件不保存这些工具的参数和结果。数值生成在后台运行，未完成时不允许关闭应用。
