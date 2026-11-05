#!/usr/bin/env python3
r"""从标定页导出的 TSV 拟合 optical_fit 的全局缩放参数。

模型里每个图标的视觉直径

    visual = extent × R ** reach_key × T ** thin_key

R = 2·reach/extent（包围圆比），T = short/extent（细长比）。fill / PLATE_TARGET
是两组的截距；细长指数本身随目标尺寸变化：

    thin_key(t) = THIN_KEY + THIN_SCALE_KEY · ln(t / THIN_SCALE_REF)

把 fill 作为截距 + 尺寸交互项一起拟合，才不会在小尺寸和大尺寸之间二选一。
单份 TSV 只能定当轮尺寸下的局部指数；多份 TSV（不同 fill）才能定交互斜率。

用法示例
--------
# 单轮：看这轮尺寸下的局部参数
python3 tools/fit_scale.py tools/3.tsv

# 多轮：联合拟合，同时给出尺寸交互
python3 tools/fit_scale.py tools/2.tsv tools/3.tsv

# 旧 TSV 表头没写指数时，指定导出时的基准
python3 tools/fit_scale.py tools/2.tsv --base 0.697,1.071,0.136,0.136

# 写回 optical_fit.py / gen_lab.py / lab.py
python3 tools/fit_scale.py tools/2.tsv tools/3.tsv --write

# 检查函数形式：交互、solidity、墨迹密度等
python3 tools/fit_scale.py tools/3.tsv --diagnose
"""

import argparse
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optical_fit as of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONSTANTS = ('REACH_KEY', 'PLATE_REACH_KEY', 'THIN_KEY', 'THIN_SCALE_KEY',
             'PLATE_THIN_KEY', 'PLATE_THIN_SCALE_KEY', 'THIN_SCALE_REF',
             'PLATE_TARGET')
DEFAULT_REF = 0.600


def read_header(path):
    params = {}
    with open(path, encoding='utf-8') as file:
        for line in file:
            if not line.startswith('#'):
                break
            for key, value in re.findall(r'([a-z_]+)=([\d.]+)', line):
                try:
                    params[key] = float(value)
                except ValueError:
                    pass
    return params


def baseline_thin(header, plate, value, fallback, fallback_scale,
                  fallback_ref):
    """这条数据在导出时用的细长指数（可能随尺寸变化）。"""
    if plate:
        base = header.get('plate_thin', header.get('thin'))
        slope = header.get('plate_thin_scale')
    else:
        base = header.get('thin')
        slope = header.get('thin_scale')
    if base is None:
        base, slope = fallback, fallback_scale
    elif slope is None:
        slope = 0.0
    ref = header.get('thin_ref', fallback_ref)
    return base + slope * math.log(max(value, 1e-4) / ref)


def features(source):
    image = of.load_image(source)
    plate = of.is_plate_source(np.asarray(image).astype(np.float32))
    if plate:
        _, layer = of.plate_parts(image.crop(of.plate_bounds(image)))
        info = of.measure(layer)
        mask = np.asarray(layer)[..., 3].astype(np.float32) / 255.0
    else:
        info = of.measure(image)
        mask = of.subject_mask(np.asarray(image).astype(np.float32))[0]
    extent = info['extent']
    short = min(info['bbox_w'], info['bbox_h'])
    ink = float((mask > 0.5).sum()) / max(1.0, info['bbox_w'] * info['bbox_h'])
    return (max(1.0, 2.0 * info['reach'] / extent),
            min(1.0, max(short, 0.5) / extent), plate, {
                'solid': info['area'] / max(1.0, info['bbox_w'] * info['bbox_h']),
                'circ': info['area'] / max(1e-6, math.pi * (extent / 2) ** 2),
                'd_eq': info['d_eq'] / max(1e-6, extent),
                'ink': max(1e-6, ink),
            })


def load_rows(path, sources, header, base):
    rows = []
    with open(path, encoding='utf-8') as file:
        for line in file:
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 3:
                continue
            name, kind, visual = parts[0], parts[1], float(parts[2])
            stem = os.path.splitext(name)[0].lower()
            source = sources.get(stem)
            if source is None:
                raise SystemExit(f'{path}: 找不到 {name} 的源图（{stem}）')
            R, T, plate, extra = features(source)
            fb = base[1 if plate else 0]
            rows.append({
                'name': name, 'v': visual, 'plate': plate,
                'R': R, 'T': T, 'extra': extra,
                'b0': baseline_thin(header, plate, visual, fb[1], fb[2], fb[3]),
            })
    return rows


def fit_round(rows, a0, a_shared=None, interaction=False, extras=()):
    """固定 a 时拟合 b 和截距；a_shared 为 None 时 a 也一起拟合。"""
    lr = np.log([r['R'] for r in rows])
    lt = np.log([r['T'] for r in rows])
    y = np.log([r['v'] for r in rows]) - np.array([r['b0'] for r in rows]) * lt
    columns = []
    if a_shared is None:
        columns.append(lr)
    else:
        # reach 固定：把 (a0 - a)·logR 移到因变量，不参与回归
        y = y - (a0 - a_shared) * lr
    thin_index = len(columns)
    columns.append(lt)
    if interaction:
        columns.append(lr * lt)
    for key in extras:
        columns.append(np.log([r['extra'][key] for r in rows]))
    columns.append(np.ones(len(rows)))
    X = np.column_stack(columns)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    error = y - X @ coef
    a = a0 - coef[0] if a_shared is None else a_shared
    thin = -coef[thin_index]
    fill = math.exp(coef[-1])
    return {
        'a': a, 'b': thin, 'fill': fill, 'coef': coef,
        'rms': math.sqrt(float((error ** 2).mean())) * 100,
        'error': error, 'n': len(rows),
    }


def grid_a(rounds, a0s, lo=-1.0, hi=2.0, step=0.001):
    """多轮共用 reach 指数：搜索使总 SSE 最小的 a。"""
    best, best_sse = None, None
    for a in np.arange(lo, hi + step / 2, step):
        total = 0.0
        for rows, a0 in zip(rounds, a0s):
            result = fit_round(rows, a0, a_shared=a)
            total += float((result['error'] ** 2).sum())
        if best_sse is None or total < best_sse:
            best, best_sse = a, total
    return float(best)


def report(label, result, rows):
    print(f'{label}  n={result["n"]}  '
          f'fill={result["fill"]:.4f}  reach={result["a"]:.4f}  '
          f'thin(局部)={result["b"]:.4f}  rms={result["rms"]:.2f}%')
    worst = sorted(zip(rows, result['error']), key=lambda item: -abs(item[1]))[:3]
    for row, error in worst:
        print(f'    {row["name"][:36]:38s} visual={row["v"]:.3f}  '
              f'R={row["R"]:.2f} T={row["T"]:.2f}  miss={error * 100:+.1f}%')


def pooled(rounds, a0s, label):
    """多轮：共享 reach，估计 thin 随 ln(fill) 的斜率。"""
    if len(rounds) == 1:
        result = fit_round(rounds[0], a0s[0])
        result['scale_key'] = None
        result['ref_key'] = None
        return result
    a = grid_a(rounds, a0s)
    points = []
    total_sse = 0.0
    for rows, a0 in zip(rounds, a0s):
        result = fit_round(rows, a0, a_shared=a)
        total_sse += float((result['error'] ** 2).sum())
        points.append((math.log(result['fill']), result['b'], len(rows)))
    x = np.array([p[0] for p in points])
    y = np.array([p[1] for p in points])
    w = np.array([p[2] for p in points], dtype=float)
    slope = float(np.polyfit(x, y, 1, w=np.sqrt(w))[0])
    ref_key = DEFAULT_REF
    key = float(np.mean(y - slope * (x - math.log(ref_key))))
    fills = [p[0] for p in points]
    print(f'{label}  联合拟合：reach={a:.4f}，rms={math.sqrt(total_sse / sum(w)) * 100:.2f}%')
    for fill, b, n in points:
        print(f'    fill={math.exp(fill):.3f}  thin(局部)={b:.4f}  n={n}')
    print(f'    thin(t) = {key:.3f} + {slope:+.3f} · ln(t / {ref_key:.3f})')
    return {
        'a': a, 'key': key, 'scale_key': slope, 'ref_key': ref_key,
        'fill': math.exp(fills[-1]),
        'rms': math.sqrt(total_sse / sum(w)) * 100,
    }


def diagnose(rows, a0):
    print('\n函数形式对比（RMS / LOOCV）')
    tests = [
        ('当前：logR + logT', False, ()),
        ('+ logR×logT', True, ()),
        ('+ solidity', False, ('solid',)),
        ('+ hull/圆面积', False, ('circ',)),
        ('+ log(d_eq/extent)', False, ('d_eq',)),
        ('+ 墨迹密度', False, ('ink',)),
    ]
    for label, interaction, extras in tests:
        result = fit_round(rows, a0, interaction=interaction, extras=extras)
        print(f'  {label:28s} rms={result["rms"]:5.2f}%')


def write_constants(fill, values):
    """写回 optical_fit.py 的常量，并同步三个入口的默认 fill。"""
    optical = os.path.join(ROOT, 'tools', 'optical_fit.py')
    text = open(optical, encoding='utf-8').read()
    old_fill = re.search(r'--diameter[\s\S]{0,160}?default=([\d.]+)', text)
    old_fill = old_fill.group(1) if old_fill else None

    for name in CONSTANTS:
        value = values[name]
        pattern = re.compile(rf'^{name} = [-\d.]+', re.M)
        if pattern.search(text):
            text = pattern.sub(f'{name} = {value:.3f}', text)
        else:
            anchor = re.search(r'^PLATE_THIN_KEY = .*$', text, re.M)
            if anchor:
                text = text[:anchor.end()] + f'\n{name} = {value:.3f}' + text[anchor.end():]
    text = re.sub(r'^DEFAULT_FILL = [-\d.]+', f'DEFAULT_FILL = {fill:.3f}', text, flags=re.M)
    open(optical, 'w', encoding='utf-8').write(text)

    if old_fill and old_fill != f'{fill:.3f}':
        for path in (optical,
                     os.path.join(ROOT, 'tools', 'gen_lab.py'),
                     os.path.join(ROOT, 'tools', 'lab.py')):
            body = open(path, encoding='utf-8').read()
            body = body.replace(old_fill, f'{fill:.3f}')
            open(path, 'w', encoding='utf-8').write(body)

    print(f'\n已写回：fill={fill:.3f}, ' +
          ', '.join(f'{k}={v:.3f}' for k, v in values.items()))
    print('下一步：')
    print('  python3 tools/optical_fit.py ori_icon -o web_icon --from-index index.html')
    print('  python3 tools/gen_lab.py')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='从标定页 TSV 拟合 optical_fit 的全局缩放参数',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split('用法示例', 1)[-1].strip() if '用法示例' in __doc__ else None,
    )
    parser.add_argument('tsv', nargs='+', help='一个或多个标定页导出的 TSV')
    parser.add_argument('--source', default=os.path.join(ROOT, 'ori_icon'),
                        help='高清源图目录（默认 ori_icon）')
    parser.add_argument('--base', action='append',
                        help='旧 TSV 的基准指数：FILE=reach,plate_reach,thin,plate_thin；'
                             '可重复，也可以只给 4 个数作为所有旧文件的默认值')
    parser.add_argument('--interaction', action='store_true',
                        help='额外展示 R×T 交互项（只报告）')
    parser.add_argument('--diagnose', action='store_true',
                        help='对比几个额外的形状特征')
    parser.add_argument('--write', action='store_true',
                        help='把结果写回 optical_fit.py / gen_lab.py / lab.py')
    args = parser.parse_args(argv)

    for path in args.tsv:
        if not os.path.isfile(path):
            parser.error(f'找不到文件: {path}')
    if not os.path.isdir(args.source):
        parser.error(f'找不到源图目录: {args.source}')

    base_map = {}
    base_global = None
    if args.base:
        for spec in args.base:
            try:
                if '=' in spec:
                    name, numbers = spec.split('=', 1)
                    values = [float(x) for x in numbers.split(',')]
                    if len(values) != 4:
                        raise ValueError
                    base_map[os.path.basename(name)] = values
                else:
                    values = [float(x) for x in spec.split(',')]
                    if len(values) != 4:
                        raise ValueError
                    base_global = values
            except ValueError:
                parser.error('--base 需要 FILE=reach,plate_reach,thin,plate_thin '
                             '或 4 个逗号分隔的数')

    sources = of.pick_sources(args.source)
    # 每组基准：旧 TSV 没写指数时用 --base / 当前值（斜率取 0）
    fallback = [
        (of.REACH_KEY, of.THIN_KEY, of.THIN_SCALE_KEY, of.THIN_SCALE_REF),
        (of.PLATE_REACH_KEY, of.PLATE_THIN_KEY, of.PLATE_THIN_SCALE_KEY,
         of.THIN_SCALE_REF),
    ]

    datasets = []
    for path in args.tsv:
        header = read_header(path)
        file_base = base_map.get(os.path.basename(path)) or base_global
        local = fallback
        if file_base:
            local = [(file_base[0], file_base[2], 0.0, DEFAULT_REF),
                     (file_base[1], file_base[3], 0.0, DEFAULT_REF)]
        if 'reach' not in header or 'thin' not in header:
            print(f'{path}: 表头没有完整指数，使用 --base / 当前值作为基准')
        rows = load_rows(path, sources, header, local)
        datasets.append((path, header, rows, local))
        print(f'{path}: {len(rows)} 行')

    logo_rounds, logo_a0, plate_rounds, plate_a0 = [], [], [], []
    for path, header, rows, local in datasets:
        logos = [r for r in rows if not r['plate']]
        plates = [r for r in rows if r['plate']]
        if logos:
            a0 = header.get('reach', local[0][0])
            logo_rounds.append(logos)
            logo_a0.append(a0)
            result = fit_round(logos, a0)
            report(path + ' 裸标志', result, logos)
            if args.interaction:
                alt = fit_round(logos, a0, interaction=True)
                print(f'    + logR×logT: rms={alt["rms"]:.2f}%')
            if args.diagnose:
                diagnose(logos, a0)
        if plates:
            a0 = header.get('plate_reach', local[1][0])
            plate_rounds.append(plates)
            plate_a0.append(a0)
            result = fit_round(plates, a0)
            report(path + ' 底板', result, plates)

    print()
    logo = pooled(logo_rounds, logo_a0, '裸标志') if logo_rounds else None
    plate = pooled(plate_rounds, plate_a0, '底板标志') if plate_rounds else None

    if not args.write:
        return 0
    if logo is None and plate is None:
        raise SystemExit('没有拟合结果')

    values = {name: getattr(of, name) for name in CONSTANTS}
    fill = logo['fill'] if logo else plate['fill']
    if logo:
        values['REACH_KEY'] = logo['a']
        if logo['scale_key'] is not None:
            values['THIN_KEY'] = logo['key']
            values['THIN_SCALE_KEY'] = logo['scale_key']
        else:
            # 单轮：保持现有斜率，只把曲线在 fill 处对齐到局部指数
            values['THIN_KEY'] = logo['b'] - of.THIN_SCALE_KEY * math.log(
                fill / of.THIN_SCALE_REF)
        values['THIN_SCALE_REF'] = DEFAULT_REF
    if plate:
        values['PLATE_REACH_KEY'] = plate['a']
        values['PLATE_TARGET'] = plate['fill']
        if plate['scale_key'] is not None:
            values['PLATE_THIN_KEY'] = plate['key']
            values['PLATE_THIN_SCALE_KEY'] = plate['scale_key']
        else:
            values['PLATE_THIN_KEY'] = plate['b'] - of.PLATE_THIN_SCALE_KEY * math.log(
                plate['fill'] / of.THIN_SCALE_REF)
    write_constants(fill, values)
    return 0


if __name__ == '__main__':
    sys.exit(main())
