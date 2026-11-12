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
        from prediction_shap_plot import draw_shap
        draw_shap(data['shap'],config,save)
