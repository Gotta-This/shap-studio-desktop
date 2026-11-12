"""Editable prediction figures; style-only redraw uses frozen numerical snapshots."""
from pathlib import Path
from copy import deepcopy
from string import Formatter
import base64,contextlib,io,json,math,os,re,sys,uuid,zipfile
import numpy as np

MAX_RASTER_PIXELS=64_000_000
MAX_PREVIEW_PIXELS=8_000_000

def bounded_dpi(width,height,requested,limit):
    return min(int(requested),max(1,int(math.sqrt(limit/(width*height)))))

DEFAULT_PATH=Path(__file__).with_name('prediction_plot_defaults.json')
def defaults():return json.loads(DEFAULT_PATH.read_text(encoding='utf8'))

def merge(base,patch,path=''):
    if not isinstance(patch,dict):raise ValueError(path+' 必须为配置对象。')
    result=deepcopy(base)
    for key,value in patch.items():
        if key not in base:raise ValueError('不支持的图表设置：'+path+key)
        original=base[key]
        if key in ('style','series','features','category_labels','feature_styles'):
            if not isinstance(value,dict):raise ValueError(path+key+' 必须为配置对象。')
            result[key]=deepcopy(value)
        elif isinstance(original,dict):result[key]=merge(original,value,path+key+'.')
        elif isinstance(original,bool):
            if type(value) is not bool:raise ValueError(path+key+' 应为开关。')
            result[key]=value
        elif isinstance(original,(int,float)):
            if type(value) not in (int,float) or not math.isfinite(value):raise ValueError(path+key+' 应为有限数字。')
            result[key]=value
        elif isinstance(original,str):
            if not isinstance(value,str) or len(value)>2000:raise ValueError(path+key+' 应为不超过 2000 字的文本。')
            result[key]=value
        elif isinstance(original,list):
            if not isinstance(value,list) or len(value)>100:raise ValueError(path+key+' 应为列表，最多 100 项。')
            result[key]=deepcopy(value)
    return result

def upgrade_shap_style(value):
    """Upgrade the previous factory appearance without erasing custom settings.

    Stored result snapshots and profile presets predate the reference script.
    Only values matching a former default move to the adopted reference style;
    labels, feature selections, colours edited by the user and DPI survive.
    """
    patch=deepcopy(value);old=patch.get('plots',{}).get('shap')
    if not isinstance(old,dict) or 'reference_version' in old:return patch
    factory=defaults()['plots']['shap']
    former=dict(width=14.,height=11.8,left=.16,right=.97,top=.90,bottom=.10,
        title='{model}模型 SHAP 可解释性分析',title_y=.98,note_x=.5,note_y=.025,
        wspace=.44,hspace=.72,summary_height=1.5,waterfall_height=1.,force_height=.65,
        point_size=9,point_alpha=.65,jitter=.32,bar_height=.68,low_color='#3c79b1',
        high_color='#e93470',positive_color='#ec3471',negative_color='#397bb4',
        bar_color='#477eb2',show_grid=True,importance_title='平均绝对SHAP值 特征重要性',
        label_weight='bold',feature_weight='bold',row_height=.34,force_label_min=.12)
    for key,previous in former.items():
        if key in old and old[key]==previous:old[key]=deepcopy(factory[key])
    if not old.get('style'):old['style']=deepcopy(factory['style'])
    old['reference_version']=factory['reference_version']
    return patch

def validated(value=None,feature_names=None):
    c=merge(defaults(),upgrade_shap_style(value or {}));common=c['common']
    from matplotlib.colors import is_color_like
    def color(v,label):
        if not isinstance(v,str) or not is_color_like(v):raise ValueError(label+' 颜色无效。')
    def number(v,lo,hi,label,integer=False):
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi or (integer and int(v)!=v):raise ValueError(f'{label} 应在 {lo}～{hi} 之间'+('且为整数。' if integer else '。'))
    def choice(v,choices,label):
        if v not in choices:raise ValueError(label+' 选项无效。')
    def numeric_list(values,label,lo=None,hi=None):
        if not values or len(values)>60 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values) or values!=sorted(set(values)):raise ValueError(label+' 应为递增且不重复的数字列表。')
        if lo is not None and any(not lo<=v<=hi for v in values):raise ValueError(label+f' 需在 {lo}～{hi} 之间。')
    def style(s):
        for k in ('background','text_color','grid_color'):color(s[k],k)
        for k in ('font_size','title_size','panel_title_size','label_size','tick_size','legend_size','note_size'):number(s[k],4,60,k)
        for k in ('axis_width','tick_width','grid_width'):number(s[k],.1,10,k)
        number(s['tick_length'],0,20,'刻度长度');number(s['grid_alpha'],0,1,'网格透明度')
        choice(s['tick_direction'],('in','out','inout'),'刻度方向');choice(s['grid_style'],('-','--','-.',':'),'网格线型');choice(s['title_weight'],('normal','bold'),'标题字重')
        number(s['dpi'],50,1200,'DPI',True);number(s['preview_dpi'],50,180,'预览 DPI',True)
        if not s['formats'] or len(set(s['formats']))!=len(s['formats']) or any(v not in ('png','pdf','svg') for v in s['formats']):raise ValueError('至少选择一种输出格式：PNG / PDF / SVG。')
    def series(s,label):
        allowed={'label':'','color':'#111111','line_width':2,'line_style':'-','marker':'o','marker_size':4.5,'alpha':1,'visible':True}
        merged=merge(allowed,s,label+'.');color(merged['color'],label)
        number(merged['line_width'],.1,10,'曲线线宽');number(merged['marker_size'],0,20,'标记尺寸');number(merged['alpha'],0,1,'曲线透明度')
        choice(merged['line_style'],('-','--','-.',':'),'曲线线型');choice(merged['marker'],('o','s','^','v','D','+','x','*','.',''),'标记形状')
        return merged
    style(common)
    if c['version']!=1:raise ValueError('图表配置版本无效。')
    if sorted(c['model_order'])!=['LR','RF','SVM','XGB']:raise ValueError('模型顺序必须完整包含 LR、RF、XGB、SVM，且不重复。')
    for name,s in c['models'].items():series(s,name)
    filenames=[]
    for name,p in c['plots'].items():
        s=merge(common,p['style'],name+'.style.');style(s)
        if p['style']:p['style']=s
        number(p['width'],4,24,'画布宽度');number(p['height'],3,40,'画布高度')
        if not p['filename'].strip() or p['filename'] in ('.','..') or len(p['filename'])>100 or re.search(r'[<>:"/\\|?*\x00-\x1f]',p['filename']):raise ValueError('图件文件名不能为空、不能含路径或文件系统特殊字符。')
        filenames.append(p['filename'])
        for edge in ('left','right','top','bottom'):number(p[edge],0,1,'边距 '+edge)
        if p['left']>=p['right'] or p['bottom']>=p['top']:raise ValueError('左边距需小于右边距，下边距需小于上边距。')
        for pos in ('title_x','title_y','note_x','note_y'):number(p[pos],-.5,1.5,pos)
        if name=='nomogram':
            choice(p['variable_tick_mode'],('nice','even'),'指标刻度方式');choice(p['total_tick_mode'],('nice','count'),'总积分刻度方式')
            number(p['row_height'],.3,2,'指标行高');number(p['base_height'],1,10,'自动基础高度');number(p['points_max'],10,1000,'顶部积分上限')
            for k in ('points_ticks','total_ticks','variable_ticks'):number(p[k],2,15,k,True)
            for k in ('risk_digits','total_digits'):number(p[k],0,8,k,True)
            number(p['variable_digits'],1,8,'指标有效数字',True)
            numeric_list(p['risk_ticks'],'风险概率刻度',.000001,.999999)
            for k in ('line_color','points_color','total_color','risk_color'):color(p[k],k)
            choice(p['line_style'],('-','--','-.',':'),'列线图线型')
            for k,lo,hi in [('line_width',.1,8),('tick_width',.1,8),('tick_length',.01,.3),('tick_offset',.05,.4),('label_offset',.005,.3),('label_size',4,40),('tick_size',4,40),('label_rotation',-180,180),('tick_rotation',-180,180)]:number(p[k],lo,hi,k)
            order=p['feature_order']
            if len(order)!=len(set(order)) or any(not isinstance(v,str) for v in order):raise ValueError('指标顺序存在重复或无效名称。')
            feature_default=dict(label='',color=p['line_color'],ticks=[],category_labels={})
            for feature,v in p['features'].items():
                if not isinstance(feature,str):raise ValueError('指标名称无效。')
                f=merge(feature_default,v,'指标 '+feature+'.');color(f['color'],feature)
                if f['ticks']:numeric_list(f['ticks'],feature+' 刻度')
                p['features'][feature]=f
                if not isinstance(v.get('category_labels',{}),dict) or any(not isinstance(x,str) or len(x)>100 for x in v.get('category_labels',{}).values()):raise ValueError(feature+' 分类显示名称无效。')
            height=max(5,p['base_height']+p['row_height']*len(feature_names or order or [0]*6)) if p['auto_height'] else p['height']
        elif name in ('lasso','shap'):
            height=p['height']
            if name=='lasso':
                for k in ('inactive_color','cv_color','error_color','minimum_color','one_se_color','constraint_color'):color(p[k],k)
                for k in ('path_line_width','inactive_width','error_width','reference_width'):number(p[k],.1,8,k)
                number(p['legend_max'],1,60,'最多图例数',True);number(p['wspace'],0,2,'面板间距');number(p['annotation_x'],0,1,'说明 X');number(p['annotation_y'],0,1,'说明 Y');number(p['annotation_gap'],.02,.15,'说明行距');number(p['top_ticks'],2,12,'顶部刻度数',True);number(p['cv_marker_size'],1,15,'CV 点尺寸');number(p['error_capsize'],0,10,'误差线端帽');number(p['legend_columns'],1,4,'图例列数',True)
                number(p['legend_x'],-2,3,'图例 X');number(p['legend_y'],-2,3,'图例 Y');choice(p['cv_marker'],('o','s','^','D','.','x'),'CV 点形状')
            else:
                for k in ('low_color','high_color','neutral_color','positive_color','negative_color','bar_color'):color(p[k],k)
                for k in ('max_display','max_single'):number(p[k],1,60,k,True)
                number(p['wspace'],0,2,'面板水平间距');number(p['hspace'],0,2,'面板垂直间距');
                number(p['reference_version'],1,1,'SHAP 参考版式版本',True);number(p['horizontal_jitter'],0,.05,'SHAP 水平显示抖动');number(p['scatter_seed'],0,2147483647,'SHAP 显示随机种子',True)
                for k in ('title_weight','label_weight','feature_weight'):choice(p[k],('normal','bold'),k)
                number(p['row_height'],.22,1,'SHAP 自动行高');number(p['label_width'],1,4,'SHAP 标签宽度')
                for k in ('summary_height','waterfall_height','force_height'):number(p[k],.2,4,k)
                number(p['point_size'],1,100,'SHAP 散点大小');number(p['point_alpha'],0,1,'SHAP 散点透明度');number(p['jitter'],0,.45,'蜂群抖动宽度');number(p['bar_height'],.1,.9,'条形高度');number(p['value_digits'],0,6,'SHAP 小数位',True);number(p['force_label_min'],0,1,'力图标注阈值');choice(p['order'],('importance','custom'),'SHAP 指标排序')
                if len(p['feature_order'])!=len(set(p['feature_order'])) or any(not isinstance(v,str) for v in p['feature_order']):raise ValueError('SHAP 指标顺序无效。')
                if set(field for _,field,_,_ in Formatter().parse(p['title']) if field is not None)-{'model'}:raise ValueError('SHAP 标题仅支持 {model} 占位符。')
            for feature,st in p['feature_styles'].items():
                normalized=merge(dict(label='',color='#477eb2'),st,'指标 '+feature+'.');color(normalized['color'],feature);p['feature_styles'][feature]=normalized
        else:
            height=p['height'];choice(p['layout'],('horizontal','vertical','separate'),'面板布局');choice(p['aspect'],('equal','auto'),'轴比例')
            for key in ('x_ticks','y_ticks'):numeric_list(p[key],key)
            for axis in ('x','y'):
                if not p[axis+'_min']<p[axis+'_max']:raise ValueError(axis+'轴最小值需小于最大值。')
                number(p[axis+'_rotation'],-180,180,'刻度旋转角度')
            for k in ('wspace','hspace'):number(p[k],0,2,k)
            for k in ('label_pad','tick_pad','title_pad'):number(p[k],0,50,k)
            for k in ('tick_digits','auc_digits','stat_digits','brier_digits'):number(p[k],0,8,k,True)
            number(p['p_digits'],1,8,'P 值小数位',True)
            number(p['legend_columns'],1,4,'图例列数',True);number(p['legend_alpha'],0,1,'图例透明度')
            for k in ('legend_labelspacing','legend_columnspacing','legend_handlelength'):number(p[k],0,10,k)
            for k in ('legend_x','legend_y','panel_x','panel_y'):number(p[k],-2,3,k)
            number(p['panel_size'],4,50,'面板编号字号');number(p['reference_width'],.1,10,'参考线宽')
            for k in ('legend_face','legend_edge','reference_color'):color(p[k],k)
            choice(p['legend_location'],('best','upper left','upper right','lower left','lower right','upper center','lower center','center left','center right','center'),'图例位置')
            choice(p['reference_style'],('-','--','-.',':'),'参考线型');choice(p['drawstyle'],('default','steps-pre','steps-mid','steps-post'),'绘线方式')
            allowed={'label','model','auc','ci_low','ci_high','chi2','p','brier','n'}
            for text in (p['legend_template'],p['train_title'],p['validation_title']):
                try:
                    for _,field,spec,conversion in Formatter().parse(text):
                        if field is not None and (field not in allowed or spec or conversion):raise ValueError('图例／面板模板仅支持指定占位符，不支持表达式或格式代码。')
                except (ValueError,KeyError) as e:raise ValueError('图例／面板模板无效：'+str(e))
            for model,v in p['series'].items():
                if model not in c['models']:raise ValueError('曲线覆盖的模型名无效。')
                p['series'][model]=series({**c['models'][model],**v},model)
        # Raster limits are applied to the actual output figure, not to a
        # hypothetical nomogram (which may not exist when LR is unselected).
    if len(set(filenames))!=len(filenames):raise ValueError('各图的文件名不能重复。')
    output_names=[]
    for name,p in c['plots'].items():
        if p['enabled']:
            output_names.extend([p['filename']+'_训练集',p['filename']+'_验证集'] if name in ('roc','calibration') and p['layout']=='separate' else [p['filename']])
    if not output_names:raise ValueError('至少启用一张图，当前没有可生成的图。')
    if len(output_names)!=len(set(output_names)):raise ValueError('分面导出后的文件名存在重复，请修改图件文件名。')
    return c

def snapshot(X,numeric,categorical,lr,y,tr,va,predictions,reports):
    from sklearn.metrics import roc_curve
    panels=[]
    for label,ix in [('训练集',tr),('验证集',va)]:
        curves={}
        for model,sets in predictions.items():
            x,z,_=roc_curve(y[ix],sets[label]);r=next(r for r in reports if r['model']==model and r['dataset']==label)
            curves[model]=dict(roc_x=x.tolist(),roc_y=z.tolist(),report=r)
        panels.append(dict(dataset=label,n=len(ix),curves=curves))
    axes=[];intercept=0.
    if lr is not None:
        prep=lr.named_steps['prepare'];coef=lr.named_steps['model'].coef_[0];intercept=float(lr.named_steps['model'].intercept_[0]);offset=0
        if numeric:
            scaler=prep.named_transformers_['num'].named_steps['scale']
            for i,name in enumerate(numeric):
                beta=float(coef[i]/scaler.scale_[i]);intercept-=beta*float(scaler.mean_[i])
                axes.append(dict(name=name,kind='continuous',beta=beta,minimum=float(X[name].min()),maximum=float(X[name].max())))
            offset=len(numeric)
        if categorical:
            enc=prep.named_transformers_['cat'].named_steps['encode']
            for i,name in enumerate(categorical):
                weights=[]
                for j in range(len(enc.categories_[i])):
                    if j==enc.drop_idx_[i]:weights.append(0.)
                    else:weights.append(float(coef[offset]));offset+=1
                axes.append(dict(name=name,kind='categorical',values=list(map(str,enc.categories_[i])),weights=weights))
    return dict(panels=panels,feature_order=list(X.columns),nomogram=dict(intercept=intercept,axes=axes))

@contextlib.contextmanager
def plot_context(style):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import font_manager
    assets=Path(__file__).resolve().parents[2]/'desktop_app/clinical_studio/assets'
    if getattr(sys,'frozen',False):assets=Path(sys._MEIPASS)/'clinical_studio/assets'
    candidates=list(assets.glob('NotoSansCJKsc-*.otf'))+[Path('/System/Library/Fonts/Supplemental/Songti.ttc'),Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'),Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/simsun.ttc',Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msyh.ttc',Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
    registered={f.fname for f in font_manager.fontManager.ttflist}
    for f in candidates:
        if f.is_file() and str(f) not in registered:font_manager.fontManager.addfont(str(f))
    for f in [Path('/System/Library/Fonts/Supplemental')/name for name in ('Times New Roman.ttf','Times New Roman Bold.ttf','Times New Roman Italic.ttf','Times New Roman Bold Italic.ttf')]+[Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name for name in ('times.ttf','timesbd.ttf','timesi.ttf','timesbi.ttf')]:
        if f.is_file() and str(f) not in registered:font_manager.fontManager.addfont(str(f))
    # Matplotlib addresses TTC files by path, so different faces can resolve
    # to the first (Black) face. Register standalone SC faces for real weights.
    songti=Path('/System/Library/Fonts/Supplemental/Songti.ttc')
    if songti.is_file() and not getattr(font_manager.fontManager,'_research_songti_faces',False):
        from fontTools.ttLib import TTCollection
        cache=Path(matplotlib.get_cachedir())/'research-fonts';cache.mkdir(parents=True,exist_ok=True)
        collection=TTCollection(str(songti))
        try:
            faces=[]
            for face in collection.fonts:
                if face['name'].getDebugName(1)!='Songti SC':continue
                target=cache/f"SongtiSC-{face['OS/2'].usWeightClass}.ttf"
                if not target.is_file():face.save(str(target))
                faces.append(target)
            font_manager.fontManager.ttflist[:]=[f for f in font_manager.fontManager.ttflist if f.fname!=str(songti) or f.name!='Songti SC']
            for target in faces:font_manager.fontManager.addfont(str(target))
            font_manager.fontManager._findfont_cached.cache_clear()
            font_manager.fontManager._research_songti_faces=True
        finally:collection.close()
    fonts={f.name for f in font_manager.fontManager.ttflist};chinese=style['font_family']
    if chinese=='auto':chinese=next((f for f in ('SimSun','Songti SC','Microsoft YaHei','Arial Unicode MS','Noto Sans CJK SC','Noto Sans CJK JP','Noto Sans CJK TC','WenQuanYi Zen Hei') if f in fonts),None)
    if not chinese or chinese not in fonts:raise ValueError('未找到所选中文字体，请使用自动字体或安装该字体后重试。')
    previous=os.environ.pop('MPL_IGNORE_SYSTEM_FONTS',None)
    try:
        latin=style['latin_font']
        if latin=='auto':latin='Times New Roman' if 'Times New Roman' in fonts else 'DejaVu Serif'
        if latin not in fonts:raise ValueError('未找到西文字体 '+latin+'，请改为自动字体或已安装字体。')
        with matplotlib.rc_context({'font.family':[latin,chinese,'DejaVu Sans'],'axes.unicode_minus':False,'pdf.fonttype':42,'svg.fonttype':'none','font.size':style['font_size'],'text.color':style['text_color'],'axes.labelcolor':style['text_color'],'xtick.color':style['text_color'],'ytick.color':style['text_color']}):yield
    finally:
        if previous is not None:os.environ['MPL_IGNORE_SYSTEM_FONTS']=previous


def max_span(axes):
    return max((abs(a['beta']*(a['maximum']-a['minimum'])) if a['kind']=='continuous' else max(a['weights'])-min(a['weights']) for a in axes),default=0.)

def nice_ticks(lo,hi,count,endpoints_only=False):
    if np.isclose(lo,hi):return np.array([lo])
    if endpoints_only:return np.array([lo,hi])
    from matplotlib.ticker import MaxNLocator
    ticks=MaxNLocator(nbins=max(2,count),steps=[1,2,2.5,5,10],integer=np.isclose(lo,round(lo)) and np.isclose(hi,round(hi))).tick_values(lo,hi)
    gap=(hi-lo)/12
    ticks=ticks[(ticks-lo>=gap)&(hi-ticks>=gap)]
    return np.unique(np.r_[lo,ticks,hi])

def render(out,data,config):
    c=validated(config,[a['name'] for a in data['nomogram']['axes']]);images=[];notes=[]
    import matplotlib.pyplot as plt
    def save(fig,name,s):
        width,height=fig.get_size_inches();requested=int(s['dpi'])
        dpi=bounded_dpi(width,height,requested,MAX_RASTER_PIXELS) if 'png' in s['formats'] else requested
        preview_dpi=bounded_dpi(width,height,s['preview_dpi'],MAX_PREVIEW_PIXELS)
        if dpi<requested:notes.append(f'{name}：画布 {width:g} × {height:g} 英寸，PNG 已由 {requested} DPI 自动调整为 {dpi} DPI；PDF / SVG 保持矢量输出，指标与模型结果不变。')
        try:
            for ext in s['formats']:fig.savefig(out/(name+'.'+ext),dpi=dpi if ext=='png' else requested,facecolor=s['background'],transparent=s['transparent'])
            buf=io.BytesIO();fig.savefig(buf,format='png',dpi=preview_dpi,facecolor=s['background'],transparent=s['transparent']);images.append(dict(name=name,url='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode(),dpi=dpi,requested_dpi=requested,preview_dpi=preview_dpi,width_inches=float(width),height_inches=float(height),formats=s['formats'],png_pixels=[int(width*dpi),int(height*dpi)] if 'png' in s['formats'] else None))
        finally:plt.close(fig)
    def fmt(v,digits):return '—' if v is None else f'{v:.{int(digits)}f}'
    for key in ('roc','calibration'):
        p=c['plots'][key]
        if not p['enabled']:continue
        s={**c['common'],**p['style']}
        with plot_context(s):
            groups=[[panel] for panel in data['panels']] if p['layout']=='separate' else [data['panels']]
            for panels in groups:
                rows,cols=(len(panels),1) if p['layout']=='vertical' else (1,len(panels))
                fig,axes=plt.subplots(rows,cols,figsize=(p['width'],p['height']),squeeze=False)
                fig.subplots_adjust(**{k:p[k] for k in ('left','right','bottom','top','wspace','hspace')})
                for ax,panel in zip(axes.flat,panels):
                    ax.set_facecolor(s['background'])
                    for model in c['model_order']:
                        if model not in panel['curves']:continue
                        st={**c['models'][model],**p['series'].get(model,{})}
                        if not st.get('visible',True):continue
                        r=panel['curves'][model]['report'];h=r['hl']
                        pv='不可计算' if h['p'] is None else ('<'+f'{10**(-p["p_digits"]):.{int(p["p_digits"])}f}' if h['p']<10**(-p['p_digits']) else '='+fmt(h['p'],p['p_digits']))
                        context=dict(label=st['label'],model=model,n=panel['n'],auc=fmt(r['auc'],p['auc_digits']),ci_low=fmt(r['ci_low'],p['auc_digits']),ci_high=fmt(r['ci_high'],p['auc_digits']),chi2=fmt(h['chi2'],p['stat_digits']),p=pv,brier=fmt(r['brier'],p['brier_digits']))
                        if key=='roc':x=panel['curves'][model]['roc_x'];y=panel['curves'][model]['roc_y']
                        else:x=[r['predicted'] for r in h['rows']];y=[r['actual'] for r in h['rows']]
                        ax.plot(x,y,color=st['color'],linewidth=st['line_width'],linestyle=st['line_style'] if p['connect'] else 'None',marker=st['marker'] if p['markers'] else None,markersize=st['marker_size'],alpha=st['alpha'],label=p['legend_template'].format_map(context),drawstyle=p['drawstyle'])
                    if p['reference']:ax.plot([0,1],[0,1],color=p['reference_color'],linestyle=p['reference_style'],linewidth=p['reference_width'],zorder=0)
                    ax.set_xticks(p['x_ticks']);ax.set_yticks(p['y_ticks'])
                    ax.set(xlim=(p['x_min'],p['x_max']),ylim=(p['y_min'],p['y_max']))
                    from matplotlib.ticker import FormatStrFormatter
                    ax.xaxis.set_major_formatter(FormatStrFormatter('%.'+str(int(p['tick_digits']))+'f'));ax.yaxis.set_major_formatter(FormatStrFormatter('%.'+str(int(p['tick_digits']))+'f'))
                    ax.set_xlabel(p['x_label'],fontsize=s['label_size'],labelpad=p['label_pad']);ax.set_ylabel(p['y_label'],fontsize=s['label_size'],labelpad=p['label_pad'])
                    title=p['train_title'] if panel['dataset']=='训练集' else p['validation_title'];ax.set_title(title.format_map(dict(n=panel['n'],label=panel['dataset'],model='',auc='',ci_low='',ci_high='',chi2='',p='',brier='')),fontsize=s['panel_title_size'],fontweight=s['title_weight'],pad=p['title_pad'])
                    ax.set_aspect(p['aspect']);ax.tick_params(labelsize=s['tick_size'],length=s['tick_length'],width=s['tick_width'],direction=s['tick_direction'],pad=p['tick_pad']);ax.tick_params(axis='x',labelrotation=p['x_rotation']);ax.tick_params(axis='y',labelrotation=p['y_rotation'])
                    for edge in ('left','bottom','top','right'):ax.spines[edge].set_visible(p['spine_'+edge]);ax.spines[edge].set_linewidth(s['axis_width']);ax.spines[edge].set_color(s['text_color'])
                    if s['grid']:ax.grid(True,color=s['grid_color'],linestyle=s['grid_style'],linewidth=s['grid_width'],alpha=s['grid_alpha'])
                    if p['panel_labels']:ax.text(p['panel_x'],p['panel_y'],p['panel_a'] if panel['dataset']=='训练集' else p['panel_b'],transform=ax.transAxes,fontsize=p['panel_size'],fontweight='bold')
                    if p['legend']:
                        args=dict(loc=p['legend_location'],frameon=p['legend_frame'],fontsize=s['legend_size'],ncols=int(p['legend_columns']),title=p['legend_title'],title_fontsize=s['legend_size'],framealpha=p['legend_alpha'],facecolor=p['legend_face'],edgecolor=p['legend_edge'],labelspacing=p['legend_labelspacing'],columnspacing=p['legend_columnspacing'],handlelength=p['legend_handlelength'])
                        if p['legend_anchor']:args['bbox_to_anchor']=(p['legend_x'],p['legend_y'])
                        ax.legend(**args)
                fig.suptitle(p['title'],x=p['title_x'],y=p['title_y'],fontsize=s['title_size'],fontweight=s['title_weight']);fig.text(p['note_x'],p['note_y'],p['note'],ha='center',fontsize=s['note_size'])
                filename=p['filename']+('_'+panels[0]['dataset'] if p['layout']=='separate' else '')
                save(fig,filename,s)
    p=c['plots']['nomogram'];raw=data['nomogram']['axes']
    if p['enabled'] and raw:
        s={**c['common'],**p['style']};lookup={a['name']:a for a in raw};preferred=p['feature_order'] or data.get('feature_order',[]);order=[n for n in preferred if n in lookup]+[a['name'] for a in raw if a['name'] not in preferred];axes_data=[]
        for name in order:
            a=lookup[name];style=p['features'].get(name,{});label=style.get('label') or name
            if a['kind']=='continuous':
                if style.get('ticks'):values=np.array(style['ticks'])
                elif p['variable_tick_mode']=='nice':values=nice_ticks(a['minimum'],a['maximum'],int(p['variable_ticks']),endpoints_only=abs((a['maximum']-a['minimum'])*a['beta']) < max_span(data['nomogram']['axes'])*.25)
                else:values=np.array([a['minimum']] if a['minimum']==a['maximum'] else np.linspace(a['minimum'],a['maximum'],int(p['variable_ticks'])))
                if any(values<a['minimum']-1e-9) or any(values>a['maximum']+1e-9):raise ValueError(name+' 的自定义刻度需在训练集范围内。')
                contribution=values*a['beta'];lo=min(a['minimum']*a['beta'],a['maximum']*a['beta']);hi=max(a['minimum']*a['beta'],a['maximum']*a['beta']);labels=[f'{v:.{int(p["variable_digits"])}g}' for v in values]
            else:
                contribution=np.array(a['weights']);lo=float(contribution.min());hi=float(contribution.max());aliases=style.get('category_labels',{});labels=[aliases.get(v,v) for v in a['values']]
            axes_data.append(dict(name=name,label=label,values=contribution,labels=labels,lo=lo,hi=hi,color=style.get('color',p['line_color'])))
        spread=max(a['hi']-a['lo'] for a in axes_data)
        if spread<1e-10:notes.append('LR 系数贡献无有效变化，未生成列线图。')
        else:
            unit=spread/p['points_max'];total=sum((a['hi']-a['lo'])/unit for a in axes_data);base=data['nomogram']['intercept']+sum(a['lo'] for a in axes_data);height=max(5,p['base_height']+p['row_height']*len(raw)) if p['auto_height'] else p['height']
            with plot_context(s):
                fig,ax=plt.subplots(figsize=(p['width'],height));fig.subplots_adjust(**{k:p[k] for k in ('left','right','top','bottom')});ax.set(xlim=(-.02,1.02),ylim=(-.65,len(raw)+3.1));ax.axis('off')
                def axis(label,yy,ticks,labels,start,end,color,gid):
                    line=ax.hlines(yy,start,end,color=color,linewidth=p['line_width'],linestyle=p['line_style']);line.set_gid(gid)
                    ax.text(-p['label_offset'],yy,label,ha='right',va='center',fontsize=p['label_size'],rotation=p['label_rotation'],color=color)
                    for x,text in sorted(zip(ticks,labels)):
                        ax.vlines(x,yy-p['tick_length'],yy+p['tick_length'],color=color,linewidth=p['tick_width']);ax.text(x,yy-p['tick_offset'],text,ha='center',va='top',fontsize=p['tick_size'],rotation=p['tick_rotation'],color=color)
                ticks=np.linspace(0,p['points_max'],int(p['points_ticks']));axis(p['points_label'],len(raw)+2.6,ticks/p['points_max'],[f'{v:g}' for v in ticks],0,1,p['points_color'],'nomogram-points')
                for i,a in enumerate(axes_data):axis(a['label'],len(raw)+1.5-i,(a['values']-a['lo'])/spread,a['labels'],0,(a['hi']-a['lo'])/spread,a['color'],'nomogram-feature-'+str(i))
                ticks=nice_ticks(0,total,int(p['total_ticks'])) if p['total_tick_mode']=='nice' else np.linspace(0,total,int(p['total_ticks']))
                labels=[fmt(v,p['total_digits']) if np.isclose(v,total) or not np.isclose(v,round(v)) else str(int(round(v))) for v in ticks]
                axis(p['total_label'],1.25,ticks/total,labels,0,1,p['total_color'],'nomogram-total')
                probs=np.array(p['risk_ticks']);points=(np.log(probs/(1-probs))-base)/unit;valid=(points>=0)&(points<=total)
                if valid.sum()<3 and p['auto_risk_ticks']:
                    from scipy.special import expit
                    points=np.linspace(0,total,5);probs=expit(base+points*unit);valid=np.full(len(points),True)
                risk_positions=points[valid]/total
                if len(risk_positions):axis(p['risk_label'],.05,risk_positions,[fmt(v,p['risk_digits']) for v in probs[valid]],float(risk_positions.min()),float(risk_positions.max()),p['risk_color'],'nomogram-risk')
                else:notes.append('配置的风险概率刻度均超出本次模型可表示范围，未绘制风险轴。')
                fig.suptitle(p['title'],x=p['title_x'],y=p['title_y'],fontsize=s['title_size'],fontweight=s['title_weight']);fig.text(p['note_x'],p['note_y'],p['note'],ha='center',fontsize=s['note_size']);save(fig,p['filename'],s)
    from prediction_extra_plots import draw_optional
    draw_optional(out,data,c,save,notes)
    if not images:raise ValueError('没有可生成的图，请启用 ROC、校准图或有效的 LR 列线图。')
    return images,notes,c


def archive(out):
    with zipfile.ZipFile(out/'完整分析结果.zip','w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(out.iterdir()):
            if file.suffix in ('.xlsx','.json','.txt','.pdf','.png','.svg') and file.name not in ('result.json',) and not file.name.startswith('preview-'):z.write(file,file.name)

def redraw(profile,p,progress):
    from prediction import location
    source=location(profile,p['id']);snap=source/'plot-data.json'
    if not snap.is_file():raise ValueError('这份旧结果没有绘图快照，请先重新运行一次分析。')
    data=json.loads(snap.read_text(encoding='utf8'));data.setdefault('feature_order',[f['name'] for f in json.loads((source/'analysis.json').read_text(encoding='utf8')).get('features',[])]);config=validated(p.get('plot_config'),[a['name'] for a in data['nomogram']['axes']])
    out=profile/'prediction'/uuid.uuid4().hex;out.mkdir(parents=True)
    import shutil
    for name in ('模型分析结果.xlsx','说明.txt','plot-data.json'):shutil.copy2(source/name,out/name)
    progress('使用已保存的预测结果重新绘图，不重新训练模型…');images,notes,config=render(out,data,config)
    progress('正在保存新版图件及导出包…')
    analysis=json.loads((source/'analysis.json').read_text(encoding='utf8'));analysis['plot_config']=config;analysis['figure_exports']=[{k:v for k,v in image.items() if k!='url'} for image in images];(out/'analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'图表设置.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf8')
    result=json.loads((source/'result.json').read_text(encoding='utf8'));result.update(id=out.name,images=images,plot_config=config,warnings=list(dict.fromkeys([w for w in result.get('warnings',[]) if 'PNG 已由' not in w]+notes)))
    explanation=[line for line in (out/'说明.txt').read_text(encoding='utf8').splitlines() if 'PNG 已由' not in line]
    (out/'说明.txt').write_text('\n'.join(dict.fromkeys(explanation+notes)),encoding='utf8')
    archive(out);(out/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf8');return result
