"""Reference-style LASSO and SHAP figures from stored computed diagnostics."""
import numpy as np

def draw_optional(out,data,config,save,notes):
    from prediction_plots import plot_context
    import matplotlib.pyplot as plt
    if data.get('lasso') and config['plots']['lasso']['enabled']:
        r=data['lasso'];p=config['plots']['lasso'];s={**config['common'],**p['style']}
        with plot_context(s):
            fig,axes=plt.subplots(1,2,figsize=(p['width'],p['height']));fig.subplots_adjust(**{k:p[k] for k in ('left','right','top','bottom')},wspace=p['wspace'])
            x=np.log(r['lambdas']);coef=np.asarray(r['coefficients']);selected=r['selected_features'];palette=plt.get_cmap('tab20');labelled=set()
            styles=p['feature_styles']
            for j,(name,group) in enumerate(zip(r['encoded_names'],r['groups'])):
                keep=group in selected;st=styles.get(group,{});color=st.get('color',palette(r['original_names'].index(group)%20)) if keep else p['inactive_color'];label=(st.get('label') or group) if keep and group not in labelled and len(labelled)<p['legend_max'] else None
                axes[0].plot(x,coef[:,j],color=color,lw=p['path_line_width'] if keep else p['inactive_width'],label=label,zorder=3 if keep else 1);labelled.add(group) if keep else None
            if p['show_zero_line']:axes[0].axhline(0,color='#888888',lw=.6)
            axes[1].errorbar(x,r['cv_mean'],yerr=r['cv_se'],fmt=p['cv_marker'],ms=p['cv_marker_size'],color=p['cv_color'],ecolor=p['error_color'],elinewidth=p['error_width'],capsize=p['error_capsize'])
            rules=[('min','CV最小误差',p['minimum_color'],'--'),('1se','1个标准误规则',p['one_se_color'],':'),('count','数量约束',p['constraint_color'],'-.')]
            for i,ax in enumerate(axes):
                for key,label,color,style in rules:
                    index=r['index_'+key]
                    if index is not None and (key!='count' or r['rule']=='count'):ax.axvline(x[index],color=color,ls=style,lw=p['reference_width'])
                ax.set_xlabel(p['x_label'],fontsize=s['label_size']);ax.set_ylabel(p['path_y_label'] if i==0 else p['cv_y_label'],fontsize=s['label_size']);ax.set_xlim(x[0],x[-1]);ax.spines[['right','top']].set_visible(False);ax.tick_params(labelsize=s['tick_size']);ax.set_title(p['path_title'] if i==0 else p['cv_title'],fontsize=s['panel_title_size'],pad=44)
                if s['grid']:ax.grid(color=s['grid_color'],ls=s['grid_style'],lw=s['grid_width'],alpha=s['grid_alpha'])
                if p['panel_labels']:ax.text(-.10,1.20,'A' if i==0 else 'B',transform=ax.transAxes,fontweight='bold',fontsize=s['panel_title_size']+3)
                if p['show_top_counts']:
                    top=ax.twiny();top.set_xlim(ax.get_xlim());ix=np.unique(np.linspace(0,len(x)-1,int(p['top_ticks'])).astype(int));top.set_xticks(x[ix],[str(r['nonzero_counts'][j]) for j in ix]);top.set_xlabel(p['top_label'],fontsize=s['tick_size'],labelpad=8);top.tick_params(labelsize=s['tick_size']);top.spines[['left','right','bottom']].set_visible(False)
            if p['legend'] and labelled:axes[0].legend(loc='upper center',bbox_to_anchor=(p['legend_x'],p['legend_y']),frameon=p['legend_frame'],ncols=int(p['legend_columns']),fontsize=s['legend_size'],title=p['legend_title'],title_fontsize=s['legend_size'])
            yy=p['annotation_y']
            for key,label,color,_ in rules:
                index=r['index_'+key]
                if index is not None and (key!='count' or r['rule']=='count'):
                    fig.text(p['annotation_x'],yy,f"{label}：λ={r['lambdas'][index]:.6g}，{r['nonzero_counts'][index]} 项",color=color,fontsize=s['note_size']);yy-=p['annotation_gap']
            note=p['note'] or (f"训练集 {r['train_n']} 例；误差线为折间均值的标准误。顶部按原始指标计数，分类编码系数按原指标归组。\nLASSO 仅提供可选诊断与建议，不自动改变四模型的输入指标。" if p['auto_note'] else '')
            fig.suptitle(p['title'],x=p['title_x'],y=p['title_y'],fontsize=s['title_size']);fig.text(p['note_x'],p['note_y'],note,ha='center',fontsize=s['note_size']);save(fig,p['filename'],s)
            if r['convergence_warnings']:notes.append(f"LASSO 有 {r['convergence_warnings']} 次拟合未收敛，请增加最大迭代数或调整 λ 网格后再解释。")
    if data.get('shap') and config['plots']['shap']['enabled']:
        r=data['shap'];p=config['plots']['shap'];s={**config['common'],**p['style']};names=r['feature_names'];styles=p['feature_styles'];importance=np.array(r['importance']);values=np.asarray(r['sample_shap']);features=np.asarray(r['sample_color'],dtype=float);case=r['case'];unit='对数优势' if r['unit']=='log_odds' else '概率贡献'
        def label(j):return styles.get(names[j],{}).get('label') or names[j]
        ordered=list(np.argsort(-importance))
        if p['order']=='custom':ordered=[names.index(n) for n in p['feature_order'] if n in names]+[i for i in ordered if names[i] not in p['feature_order']]
        ordered=ordered[:int(p['max_display'])]
        with plot_context(s):
            from matplotlib.colors import LinearSegmentedColormap,Normalize
            from matplotlib.cm import ScalarMappable
            # Measure labels in physical units: DPI changes resolution, not row spacing.
            fig=plt.figure(figsize=(p['width'],p['height']))
            local_order=np.argsort(-np.abs(case['shap'])).tolist()
            local=[(label(j)+' = '+case['values'][j],case['shap'][j]) for j in local_order[:int(p['max_single'])]]
            rest=local_order[int(p['max_single']):]
            if rest:local.append((f'其他 {len(rest)} 项',float(np.sum(np.array(case['shap'])[rest]))))
            top_labels=[label(j) for j in ordered]
            local_labels=[v[0] for v in local]
            if p['auto_layout']:
                from matplotlib.font_manager import FontProperties
                fig.canvas.draw();renderer=fig.canvas.get_renderer();font=FontProperties(size=s['tick_size'],weight=p['feature_weight'])
                def measured(text):return renderer.get_text_width_height_descent(text,font,False)[0]/fig.dpi
                def wrapped(text):
                    lines=[]
                    for paragraph in str(text).split('\n'):
                        line=''
                        for char in paragraph:
                            if line and measured(line+char)>p['label_width']:lines.append(line);line=''
                            line+=char
                        lines.append(line)
                    return '\n'.join(lines)
                top_labels=[wrapped(v) for v in top_labels];local_labels=[wrapped(v) for v in local_labels]
                line_height=s['tick_size']/72*1.25
                row=max(p['row_height'],max(v.count('\n')+1 for v in top_labels)*line_height+.12)
                local_row=max(p['row_height'],max(v.count('\n')+1 for v in local_labels)*line_height+.12)
                summary=max(2.5,(len(ordered)+.7)*row)*p['summary_height']/1.5
                waterfall=max(2,(len(local)+.7)*local_row)*p['waterfall_height']
                force_height=max(1.5,s['tick_size']/72*8)*p['force_height']/.65
                gap=max(1.3,s['panel_title_size']/72*5.5)*(1+p['hspace'])/1.72
                header=max(1.5,s['title_size']/72*5)
                footer=max(1.3,s['note_size']/72*6)
                width=max(p['width'],12);height=header+summary+gap+waterfall+gap+force_height+footer
                fig.set_size_inches(width,height)
                gutter=max(measured(v) for v in top_labels+local_labels for v in v.split('\n'))+.18
                left=max(.5,gutter);right=width-.35
                middle=max(measured(v) for v in top_labels for v in v.split('\n'))+.7+( .35 if p['colorbar'] else 0)
                plot_width=(right-left-middle)/2
                def axes(x,y,w,h):return fig.add_axes([x/width,y/height,w/width,h/height])
                y=height-header-summary
                ax=axes(left,y,plot_width,summary);bar=axes(left+plot_width+middle,y,plot_width,summary)
                water=axes(left,footer+force_height+gap,right-left,waterfall)
                force=axes(left,footer,right-left,force_height)
                color_axes=axes(left+plot_width+.12,y,.12,summary) if p['colorbar'] else None
            else:
                grid=fig.add_gridspec(3,2,height_ratios=[p['summary_height'],p['waterfall_height'],p['force_height']],hspace=p['hspace'],wspace=p['wspace']);fig.subplots_adjust(**{k:p[k] for k in ('left','right','top','bottom')})
                ax=fig.add_subplot(grid[0,0]);bar=fig.add_subplot(grid[0,1]);water=fig.add_subplot(grid[1,:]);force=fig.add_subplot(grid[2,:]);color_axes=None
            cmap=LinearSegmentedColormap.from_list('clinical_values',[p['low_color'],p['neutral_color'],p['high_color']]);rng=np.random.default_rng(12)
            for row,j in enumerate(ordered):
                v=values[:,j];span=np.ptp(v);bins=np.floor((v-v.min())/span*30).astype(int) if span>1e-12 else np.zeros(len(v),dtype=int);offset=np.zeros(len(v))
                for group in np.unique(bins):
                    ix=np.flatnonzero(bins==group);rng.shuffle(ix);stack=np.array([0]+[(-1)**k*((k+1)//2) for k in range(1,len(ix))]);offset[ix]=stack/(max(abs(stack).max(),1))*p['jitter']
                color=features[:,j];finite=np.isfinite(color)
                ax.scatter(v[finite],row+offset[finite],c=color[finite],cmap=cmap,vmin=0,vmax=1,s=p['point_size'],alpha=p['point_alpha'],edgecolors='none')
                if (~finite).any():ax.scatter(v[~finite],row+offset[~finite],color=p['neutral_color'],s=p['point_size'],alpha=p['point_alpha'])
            ax.set_yticks(range(len(ordered)),top_labels);ax.set_ylim(len(ordered)-.3,-.7);ax.axvline(0,color='#aaaaaa',lw=.8);ax.set_xlabel('SHAP值（'+unit+'）',fontsize=s['label_size'])
            if p['colorbar']:
                cb=fig.colorbar(ScalarMappable(norm=Normalize(0,1),cmap=cmap),ax=ax,cax=color_axes,fraction=.035,pad=.03);cb.set_ticks([0,1],labels=['低','高']);cb.ax.set_title('特征值',fontsize=s['tick_size'],fontweight=p['label_weight']);cb.ax.tick_params(labelsize=s['tick_size'])
            bars=bar.barh(range(len(ordered)),importance[ordered],height=p['bar_height'],color=[styles.get(names[j],{}).get('color',p['bar_color']) for j in ordered]);bar.set_yticks(range(len(ordered)),top_labels);bar.set_ylim(len(ordered)-.3,-.7);bar.set_xlabel('平均绝对SHAP值（'+unit+'）',fontsize=s['label_size']);bar.set_xlim(0,max(float(importance.max())*1.22,1e-6))
            if p['show_values']:
                for b,j in zip(bars,ordered):bar.text(b.get_width()+max(float(importance.max())*.015,1e-8),b.get_y()+b.get_height()/2,f'{importance[j]:.{int(p["value_digits"])}f}',va='center',fontsize=s['tick_size'])
            cursor=case['base'];water.axvline(case['base'],color='#aaaaaa',ls='--',lw=.8);water.axvline(case['output'],color='#777777',lw=.8)
            for row,(name,value) in enumerate(local):
                water.barh(row,abs(value),left=min(cursor,cursor+value),color=p['positive_color'] if value>=0 else p['negative_color'],height=.62)
                if p['show_values']:water.text(cursor+value/2,row,f'{value:+.{int(p["value_digits"])}f}',ha='center',va='center',fontsize=max(6,s['tick_size']-2),color='white')
                cursor+=value
            water.set_yticks(range(len(local)),local_labels);water.set_ylim(len(local)-.3,-.7);water.set_xlabel('模型输出（'+unit+'）',fontsize=s['label_size']);water.text(.01,1.04,f"基线 {case['base']:.3f} → 输出 {case['output']:.3f}；预测概率 {case['probability']:.1%}",transform=water.transAxes,fontsize=s['tick_size'])
            from matplotlib.patches import Polygon
            positive=[v for v in local if v[1]>=0];negative=[v for v in local if v[1]<0];total_abs=sum(abs(v[1]) for v in local) or 1
            positive_start=case['output']-sum(v for _,v in positive);negative_start=case['output']-sum(v for _,v in negative)
            span=max(abs(negative_start-positive_start),.1)
            for entries,start,color in [(positive,positive_start,p['positive_color']),(negative,negative_start,p['negative_color'])]:
                cursor=start
                for name,value in entries:
                    if abs(value)<1e-14:continue
                    end=cursor+value;direction=1 if value>0 else -1;head=min(abs(value)*.35,span*.018)
                    polygon=Polygon([(cursor,-.07),(end-direction*head,-.07),(end,0),(end-direction*head,.07),(cursor,.07)],closed=True,facecolor=color,edgecolor='white',linewidth=.4)
                    force.add_patch(polygon)
                    if abs(value)/total_abs>=p['force_label_min']:force.text((cursor+end)/2,.12,(wrapped(name) if p['auto_layout'] else name)+'\n'+f'{value:+.{int(p["value_digits"])}f}',ha='center',fontsize=max(6,s['tick_size']-2))
                    cursor=end
            force.set_xlim(min(positive_start,case['base'],case['output'])-span*.06,max(negative_start,case['base'],case['output'])+span*.06);force.set_ylim(-.20,.55);force.set_yticks([]);force.set_xlabel('模型输出（'+unit+'）',fontsize=s['label_size']);force.axvline(case['base'],color='#aaaaaa',ls='--',lw=.8);force.axvline(case['output'],color='#777777',lw=.8)
            force.text(.01,.96,f"基线 {case['base']:.3f}",transform=force.transAxes,va='top',fontsize=s['tick_size']);force.text(.99,.96,f"模型输出 {case['output']:.3f}；预测概率 {case['probability']:.1%}",transform=force.transAxes,ha='right',va='top',fontsize=s['tick_size'])
            titles=[p['summary_title'],p['importance_title'],p['waterfall_title']+f"（编号 {case['id']}）",p['force_title']+f"（编号 {case['id']}）"]
            for letter,a,title in zip('ABCD',[ax,bar,water,force],titles):
                a.set_title((letter+'  ' if p['panel_labels'] else '')+title,fontsize=s['panel_title_size'],fontweight=p['title_weight'],pad=18);a.tick_params(labelsize=s['tick_size'],length=s['tick_length'],width=s['tick_width'],direction=s['tick_direction']);a.spines[['top','right']].set_visible(False)
                if p['show_grid']:a.grid(axis='y',color=s['grid_color'],linestyle=s['grid_style'],lw=s['grid_width'],alpha=s['grid_alpha']);a.set_axisbelow(True)
            for a in (ax,bar,water,force):a.xaxis.label.set_fontweight(p['label_weight'])
            for a in (ax,bar,water):
                for tick in a.get_yticklabels():tick.set_fontweight(p['feature_weight'])
            force.spines[['left']].set_visible(False)
            note=p['note'] or (f"A、B：{dict(train='训练集',validation='验证集',all='全量数据')[r['dataset']]}中实际解释 {len(r['sample_ids'])} 例；C、D：编号 {case['id']}，预测概率 {case['probability']:.1%}。\n颜色表示特征值高低；分类编码贡献按原始指标相加。SHAP 反映模型归因，不代表因果效应。" if p['auto_note'] else '')
            fig.suptitle(p['title'].replace('{model}',r['model']),x=p['title_x'],y=(1-.18/height if p['auto_layout'] else p['title_y']),va='top',fontsize=s['title_size'],fontweight=p['title_weight']);fig.text(p['note_x'],(.16/height if p['auto_layout'] else p['note_y']),note,ha='center',va='bottom',fontsize=s['note_size']);save(fig,p['filename'],s)
