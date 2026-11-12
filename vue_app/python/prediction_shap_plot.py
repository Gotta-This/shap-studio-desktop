"""SHAP renderer adapted from the adopted shap_reference_style.py.

The stored SHAP snapshot is read only. Reference geometry is retained for the
six-variable figure; longer labels and larger feature sets get extra space.
"""
import math
import numpy as np


def draw_shap(r, config, save):
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.cm import ScalarMappable
    from matplotlib.font_manager import FontProperties
    from matplotlib.patches import Polygon, Rectangle
    from prediction_plots import plot_context

    p = config['plots']['shap']
    s = {**config['common'], **p['style']}
    names = r['feature_names']
    styles = p['feature_styles']
    values = np.asarray(r['sample_shap'])
    colors = np.asarray(r['sample_color'], dtype=float)
    importance = np.asarray(r['importance'])
    case = r['case']
    unit = '对数优势' if r['unit'] == 'log_odds' else '概率贡献'
    dataset = dict(train='训练集', validation='验证集', all='全量数据')[r['dataset']]
    label = lambda j: styles.get(names[j], {}).get('label') or names[j]
    ordered = np.argsort(-importance, kind='stable').tolist()
    if p['order'] == 'custom':
        ordered = [names.index(n) for n in p['feature_order'] if n in names] + [j for j in ordered if names[j] not in p['feature_order']]
    ordered = ordered[:int(p['max_display'])]
    order = np.argsort(-np.abs(case['shap']), kind='stable').tolist()
    local = [(label(j) + ' = ' + str(case['values'][j]), float(case['shap'][j]), label(j)) for j in order[:int(p['max_single'])]]
    rest = order[int(p['max_single']):]
    if rest:
        local.append((f'其他 {len(rest)} 项', float(np.asarray(case['shap'])[rest].sum()), f'其他 {len(rest)} 项'))

    with plot_context(s):
        # Chinese labels use the Chinese face, as in the reference's explicit
        # FontProperties. Numeric ticks and contributions use Times New Roman.
        import matplotlib
        chinese = next(f for f in matplotlib.rcParams['font.family'] if f not in ('Times New Roman', 'DejaVu Serif', 'DejaVu Sans', s['latin_font']))
        cn = FontProperties(family=chinese)
        fig = plt.figure(figsize=(p['width'], p['height']))
        grid = fig.add_gridspec(3, 2, left=p['left'], right=p['right'], bottom=p['bottom'], top=p['top'],
            height_ratios=[p['summary_height'], p['waterfall_height'], p['force_height']], wspace=p['wspace'], hspace=p['hspace'])
        a, b = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
        c, d = fig.add_subplot(grid[1, :]), fig.add_subplot(grid[2, :])
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        label_font = FontProperties(family=chinese, size=s['tick_size'], weight=p['feature_weight'])

        def measure(text, font=label_font):
            return renderer.get_text_width_height_descent(text, font, False)[0] / fig.dpi

        def wrap(text, limit=p['label_width']):
            lines = []
            for paragraph in str(text).split('\n'):
                line = ''
                for char in paragraph:
                    if line and measure(line + char) > limit:
                        lines.append(line)
                        line = ''
                    line += char
                lines.append(line)
            return '\n'.join(lines)

        top_labels = [label(j) for j in ordered]
        local_labels = [v[0] for v in local]
        # Default six-variable layout uses exactly the reference GridSpec.
        # Extra height is allocated only to the panel needing additional rows.
        force_columns = 6
        if p['auto_layout']:
            top_labels = [wrap(t) for t in top_labels]
            local_labels = [wrap(t) for t in local_labels]
            width, height = fig.get_size_inches()
            boxes = [ax.get_position().frozen() for ax in (a, b, c, d)]
            base_summary, base_water, base_force = [boxes[i].height * height for i in (0, 2, 3)]
            line = s['tick_size'] / 72 * 1.2
            row_sizes = lambda labels: [max(p['row_height'], (v.count('\n') + 1) * line + .10) for v in labels]
            summary = max(base_summary, sum(row_sizes(top_labels)) + .1)
            water = max(base_water, sum(row_sizes(local_labels)) + .1)
            force_columns = min(6, max(1, int((boxes[3].width * width) / max(1.4, min(p['label_width'], 2.1)))))
            # Six short labels retain the reference's six evenly spaced anchors.
            if max(measure(v[0]) for v in local) <= boxes[3].width * width / min(6, len(local)):
                force_columns = min(6, len(local))
            force_rows = math.ceil(len(local) / force_columns)
            force_extra = max(0, force_rows - 1) * .65
            force = base_force + force_extra
            extra = summary - base_summary + water - base_water + force_extra
            if extra > 1e-9:
                height += extra
                fig.set_size_inches(width, height)
            # Keep physical header, inter-panel gaps and footer unchanged.
            footer = boxes[3].y0 * p['height']
            gap_cd = (boxes[2].y0 - boxes[3].y1) * p['height']
            gap_ac = (boxes[0].y0 - boxes[2].y1) * p['height']
            left = max(p['left'] * width, max(measure(v) for t in top_labels + local_labels for v in t.split('\n')) + .16)
            right = p['right'] * width
            original_gap = (boxes[1].x0 - boxes[0].x1) * width
            middle = max(original_gap, max(measure(v) for t in top_labels for v in t.split('\n')) + (.65 if p['colorbar'] else .18))
            panel_width = max(.5, (right - left - middle) / 2)
            water_y = footer + force + gap_cd
            summary_y = water_y + water + gap_ac
            for ax, bounds in zip((a, b, c, d), (
                (left, summary_y, panel_width, summary), (left + panel_width + middle, summary_y, panel_width, summary),
                (left, water_y, right - left, water), (left, footer, right - left, force))):
                x, y, w, h = bounds
                ax.set_position([x / width, y / height, w / width, h / height])
        else:
            force_rows = 1
        height = fig.get_figheight()
        scale_y = p['height'] / height
        display_model = {'XGB': 'XGBoost', 'RF': '随机森林', 'LR': 'Logistic回归'}.get(r['model'], r['model'])
        fig.suptitle(p['title'].replace('{model}', display_model), fontproperties=cn, fontsize=s['title_size'],
            fontweight=p['title_weight'], x=p['title_x'], y=1 - (1 - p['title_y']) * scale_y)

        def title(ax, letter, text):
            t = ax.text(0, 1.035, (letter + '  ' if p['panel_labels'] else '') + text,
                transform=ax.transAxes, ha='left', va='bottom', fontproperties=cn,
                fontsize=s['panel_title_size'], fontweight=p['title_weight'])
            t.set_gid('shap-title-' + letter)

        title(a, 'A', p['summary_title'])
        title(b, 'B', p['importance_title'])
        cmap = LinearSegmentedColormap.from_list('reference_blue_pink', [p['low_color'], p['high_color']])
        rng = np.random.default_rng(int(p['scatter_seed']))
        jitter = np.ptp(values) * p['horizontal_jitter']
        for row, j in enumerate(ordered):
            x = values[:, j] + np.clip(rng.normal(0, jitter / 2, len(values)), -jitter, jitter)
            y = row + rng.uniform(-p['jitter'], p['jitter'], len(values))
            finite = np.isfinite(colors[:, j])
            a.scatter(x[finite], y[finite], c=colors[finite, j], cmap=cmap, vmin=0, vmax=1,
                s=p['point_size'], alpha=p['point_alpha'], linewidths=0, rasterized=True)
            if (~finite).any():
                a.scatter(x[~finite], y[~finite], color=p['neutral_color'], s=p['point_size'], alpha=p['point_alpha'], linewidths=0, rasterized=True)
        a.axvline(0, color='#A8A8A8', lw=.7, zorder=0)
        a.set_ylim(len(ordered) - .55, -.55)
        a.set_yticks(range(len(ordered)), top_labels, fontproperties=cn, fontsize=s['tick_size'], fontweight=p['feature_weight'])
        a.set_xlabel('SHAP值（' + unit + '）', fontproperties=cn, fontsize=s['label_size'], fontweight=p['label_weight'])
        a.text(.97, 1.035, f'{dataset}{len(r["sample_ids"])}例', transform=a.transAxes, ha='right', va='bottom', fontproperties=cn, fontsize=max(6, s['note_size'] - .5)).set_gid('shap-sample-count')
        if p['colorbar']:
            cb = fig.colorbar(ScalarMappable(norm=Normalize(0, 1), cmap=cmap), ax=a, use_gridspec=False, fraction=.035, pad=.035, aspect=30)
            cb.set_ticks([0, 1], labels=['低', '高'])
            for tick in cb.ax.get_yticklabels():
                tick.set_fontproperties(cn)
                tick.set_fontsize(s['legend_size'])
            cb.ax.set_title('特征值', fontproperties=cn, fontsize=s['legend_size'], pad=6, fontweight=p['label_weight'])
            cb.outline.set_linewidth(.5)
        b.barh(range(len(ordered)), importance[ordered], height=p['bar_height'],
            color=[styles.get(names[j], {}).get('color', p['bar_color']) for j in ordered], edgecolor='#2F6080', linewidth=.5)
        b.set_ylim(len(ordered) - .55, -.55)
        b.set_yticks(range(len(ordered)), top_labels, fontproperties=cn, fontsize=s['tick_size'], fontweight=p['feature_weight'])
        maximum = max(float(importance.max()), 1e-6)
        b.set_xlim(0, maximum * 1.19)
        if p['show_values']:
            for row, j in enumerate(ordered):
                b.text(importance[j] + maximum * .018, row, f'{importance[j]:.{int(p["value_digits"])}f}', va='center', fontsize=s['legend_size'], fontweight='bold')
        b.set_xlabel('平均|SHAP值|（' + unit + '）', fontproperties=cn, fontsize=s['label_size'], fontweight=p['label_weight'])

        base, output = case['base'], case['output']
        points = np.r_[base, base + np.cumsum([v[1] for v in local])]
        span = max(np.ptp(points), 1)
        xmin, xmax = min(points) - span * .05, max(points) + span * .19
        title(c, 'C', p['waterfall_title'] + f'（编号{case["id"]}）')
        cursor = base
        digits = int(p['value_digits'])
        for k, (_, value, _) in enumerate(local):
            y = len(local) - k
            end = cursor + value
            color = p['positive_color'] if value > 0 else p['negative_color'] if value < 0 else '#777777'
            if abs(value) > 1e-9:
                patch = Rectangle((min(cursor, end), y - .29), abs(value), .58, facecolor=color, edgecolor='white', lw=.6)
                patch.set_gid('shap-waterfall-' + str(k));c.add_patch(patch)
                if p['show_values']:
                    text = f'{value:+.{digits}f}'
                    if abs(value) > span * .13:
                        c.text((cursor + end) / 2, y, text, ha='center', va='center', color='white', fontsize=s['legend_size'], fontweight='bold')
                    else:
                        c.text(max(cursor, end) + span * .015, y, text, ha='left', va='center', color=color, fontsize=s['legend_size'], fontweight='bold')
            else:
                c.plot([end], [y], 'o', ms=2.5, color=color)
                if p['show_values']:c.text(end + span * .02, y, f'{value:.{digits}f}', ha='left', va='center', color=color, fontsize=s['legend_size'])
            if k < len(local) - 1:
                c.plot([end, end], [y - .30, y - .70], color='#CCCCCC', lw=.6)[0].set_gid('shap-waterfall-connector')
            cursor = end
        c.set_yticks(np.arange(len(local), 0, -1), local_labels, fontproperties=cn, fontsize=s['tick_size'], fontweight=p['feature_weight'])
        c.set_xlim(xmin, xmax);c.set_ylim(.35, len(local) + .85)
        c.set_xlabel('模型输出（' + unit + '）', fontproperties=cn, fontsize=s['label_size'], fontweight=p['label_weight'])
        c.axvline(base, color='#777777', ls='--', lw=.6, zorder=0)
        c.axvline(output, color='#777777', lw=.6, zorder=0)
        c.text(base, len(local) + .52, f'基准值 {base:.3f}', ha='left', va='center', fontproperties=cn, fontsize=s['legend_size'])
        c.text(xmax - span * .01, len(local) + .52, f'模型输出 {output:.3f}', ha='right', va='center', fontproperties=cn, fontsize=s['legend_size'], fontweight='bold')

        title(d, 'D', p['force_title'] + f'（编号{case["id"]}）')
        positive = [v for v in local if v[1] > 1e-9]
        negative = [v for v in local if v[1] < -1e-9]
        zero = [v for v in local if abs(v[1]) <= 1e-9]
        left = output - sum(v[1] for v in positive)
        right = output - sum(v[1] for v in negative)
        # Reference data has positive contributions only. Include both tails for
        # arbitrary mixed-sign cases without changing the reference's x range.
        force_min, force_max = min(xmin, left - span * .05), max(xmax, right + span * .05)
        d.set_xlim(force_min, force_max)
        d.set_ylim(-.64 - (force_rows - 1) * .72, 1.36)
        d.set_yticks([])
        d.set_xlabel('模型输出（' + unit + '）', fontproperties=cn, fontsize=s['label_size'], fontweight=p['label_weight'])
        segments = []
        cursor = left
        for name, value, feature in positive:
            end = cursor + value;head = min(value * .22, span * .016)
            patch = Polygon([(cursor, .40), (end - head, .40), (end, .62), (end - head, .84), (cursor, .84)], closed=True, facecolor=p['positive_color'], edgecolor='white', lw=.7)
            patch.set_gid('shap-force-positive');d.add_patch(patch)
            if p['show_values'] and value > span * p['force_label_min']:
                d.text((cursor + end) / 2, .62, feature + f' {value:+.{digits}f}', ha='center', va='center', fontproperties=cn, fontsize=max(6, s['legend_size'] - 1), color='white')
            segments.append((name, value, (cursor + end) / 2, p['positive_color']));cursor = end
        cursor = output
        for name, value, _ in negative:
            end = cursor - value;head = min(abs(value) * .22, span * .016)
            patch = Polygon([(end, .40), (cursor + head, .40), (cursor, .62), (cursor + head, .84), (end, .84)], closed=True, facecolor=p['negative_color'], edgecolor='white', lw=.7)
            patch.set_gid('shap-force-negative');d.add_patch(patch)
            segments.append((name, value, (cursor + end) / 2, p['negative_color']));cursor = end
        segments.extend((name, value, output, '#777777') for name, value, _ in zero)
        segments.sort(key=lambda v: v[2])
        for k, (name, value, mid, color) in enumerate(segments):
            row, column = divmod(k, force_columns) if p['auto_layout'] else (0, k)
            columns = min(force_columns, len(segments) - row * force_columns) if p['auto_layout'] else len(segments)
            anchor = force_min + (force_max - force_min) * (column + .5) / columns
            y = -.02 - row * .72
            d.plot([mid, mid, anchor], [.36, .22 - row * .08, y + .04], color=color, lw=.55)[0].set_gid('shap-force-leader')
            t = d.text(anchor, y, wrap(name, max(.6, d.get_position().width * fig.get_figwidth() / columns * .92)) if p['auto_layout'] else name,
                ha='center', va='top', fontproperties=cn, fontsize=max(6, s['legend_size'] - 1))
            t.set_gid('shap-force-label')
            if p['show_values']:
                d.text(anchor, y - .28, f'{value:+.{digits}f}', ha='center', va='top', fontsize=max(6, s['legend_size'] - 1), color=color)
        for x in (base, output):d.plot([x, x], [.86, 1.10], color='#777777', lw=.6)
        d.text(base, 1.16, f'基准值 {base:.3f}', ha='left', va='bottom', fontproperties=cn, fontsize=s['legend_size'])
        d.text(force_max - span * .01, 1.16, f'模型输出 {output:.3f}；预测概率 {case["probability"]:.1%}', ha='right', va='bottom', fontproperties=cn, fontsize=s['legend_size'], fontweight='bold')
        for ax in (a, b, c, d):
            ax.tick_params(labelsize=s['tick_size'], length=s['tick_length'], width=s['tick_width'], direction=s['tick_direction'])
            for spine in ax.spines.values():spine.set_linewidth(s['axis_width'])
            if p['show_grid']:
                ax.grid(axis='y', color=s['grid_color'], linestyle=s['grid_style'], lw=s['grid_width'], alpha=s['grid_alpha']);ax.set_axisbelow(True)
        if p['note']:
            fig.text(p['note_x'], p['note_y'] * scale_y, p['note'], ha='center', fontproperties=cn, fontsize=s['note_size'])
        elif p['auto_note']:
            note = f'A、B：{dataset}{len(r["sample_ids"])}例；C、D：编号{case["id"]}；预测概率为{case["probability"]:.1%}。'
            fig.text(p['note_x'], (p['note_y'] + .046) * scale_y, note, ha='center', fontproperties=cn, fontsize=s['legend_size'])
            fig.text(p['note_x'], (p['note_y'] + .023) * scale_y, '蜂群图颜色：蓝色为低值，玫红为高值；为减少重叠，散点仅作微量显示抖动。', ha='center', fontproperties=cn, fontsize=s['note_size'])
            fig.text(p['note_x'], p['note_y'] * scale_y, f'正SHAP推高预测风险，负SHAP降低预测风险；SHAP表示{unit}，不代表因果效应。', ha='center', fontproperties=cn, fontsize=s['note_size'])
        save(fig, p['filename'], s)
