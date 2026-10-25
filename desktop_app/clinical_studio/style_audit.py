"""核对实际绘图对象的字体、字号、线宽、尺寸和散点设置。"""
import numpy as np
import matplotlib as mpl
from matplotlib.text import Text
from matplotlib import font_manager


def audit_style(fig, ax, style, name):
    checks=[]
    def number(label,actual,expected):
        checks.append(dict(item=label,actual=float(actual),expected=float(expected),
                           passed=bool(np.isclose(actual,expected,rtol=0,atol=1e-8))))
    def equal(label,actual,expected):
        checks.append(dict(item=label,actual=actual,expected=expected,passed=actual==expected))
    expected_family=list(mpl.rcParams["font.family"])
    texts=[t for t in fig.findobj(match=Text) if t.get_visible() and t.get_text()]
    for i,text in enumerate(texts):
        equal(f"文字 {i+1} 字体族",list(text.get_fontfamily()),expected_family)
    # 保存字体文件名，区分配置的字体族与实际解析到的字体资源。
    resolved=[]
    for text in texts:
        file=str(font_manager.findfont(text.get_fontproperties(),fallback_to_default=True))
        if file not in resolved:resolved.append(file)
    checks.append(dict(item="实际解析的字体文件",actual=resolved,expected=expected_family,passed=bool(resolved)))
    title=fig._suptitle if name=="force" else ax.title
    if title and title.get_text():number("标题字号",title.get_fontsize(),style["title_size"])
    for label in (ax.xaxis.label,ax.yaxis.label):
        if label.get_text():number("坐标轴标题字号",label.get_fontsize(),style["label_size"])
    for label in [*ax.get_xticklabels(),*ax.get_yticklabels()]:
        if label.get_visible() and label.get_text():number("刻度字号",label.get_fontsize(),style["tick_size"])
    for text in ax.texts:
        if text.get_visible() and text.get_text():number("图内注释字号",text.get_fontsize(),style["font_size"])
    for spine in ax.spines.values():
        if spine.get_visible():number("坐标轴线宽",spine.get_linewidth(),style["axis_width"])
    for i,line in enumerate(ax.lines):
        x,y=np.asarray(line.get_xdata()),np.asarray(line.get_ydata())
        horizontal=len(y)>1 and np.all(y==y[0]) and len(x)>1 and np.any(x!=x[0])
        if name in ("summary","waterfall") and horizontal:
            expected=style["grid_width"]
        elif name=="summary" or name.startswith("dependence_"):
            expected=style["baseline_width"]
        elif name=="waterfall" and line.get_transform()==ax.get_xaxis_transform():
            expected=style["baseline_width"]
        else:expected=style["line_width"]
        number(f"线条 {i+1} 线宽",line.get_linewidth(),expected)
    for i,patch in enumerate(ax.patches):
        if patch.get_alpha()==0:continue
        if not patch.get_fill() and patch.get_edgecolor()[3]==0:continue
        separator=name=="force" and isinstance(patch,mpl.patches.Polygon) and not patch.get_fill()
        number(f"色块 {i+1} 边框/分隔线宽",patch.get_linewidth(),style["separator_width"] if separator else style["edge_width"])
    if name=="summary" or name.startswith("dependence_"):
        for collection in ax.collections:
            if isinstance(collection,mpl.collections.PathCollection) and len(collection.get_offsets()):
                for value in collection.get_sizes():number("散点面积",value,style["point_size"])
    for actual,expected,label in zip(fig.get_size_inches(),style["figsize"],["图片宽度（英寸）","图片高度（英寸）"]):
        number(label,actual,expected)
    return checks
