#!/usr/bin/env python3
r"""生成图标标定页（js/lab.js）要用的百分比变体和清单。

标定页是 index-lab.html：和 index.html 相同的网格，但给每个图标加了 +/−，
按 1% 切换 web_icon/lab 下预渲染好的视觉直径。图标清单仍然从 index.html
读取，所以正式页新增/删除图标后，把 index.html 同步成 index-lab.html 即可。
改了 optical_fit.py 的全局参数后，自动值和变体都会失效，跑一遍这个脚本
即可全部重算：

  python3 tools/gen_lab.py             # 补齐缺失变体，更新 js/lab-data.js
  python3 tools/gen_lab.py --force     # 按当前参数重渲染全部变体
  python3 tools/gen_lab.py --data-only # 只更新清单，不渲染图片

变体按「视觉直径 = 百分比 × 画布」渲染（limits=False），所以按钮上的
数字就是实际画出来的大小。判断参数是否变化靠 web_icon/lab/stamp.json：
来源文件的 mtime/大小或 optical_fit 的常量一变，下次运行自动 --force。
"""

import argparse
import hashlib
import io
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optical_fit as of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = 'stamp.json'


def auto_value(source, size, fill):
    """和 optical_fit.fit 一致地算出自动视觉直径（不改动任何文件）。"""
    image = of.load_image(source)
    plate = of.is_plate_source(np.asarray(image).astype(np.float32))
    if plate:
        _, layer = of.plate_parts(image.crop(of.plate_bounds(image)))
        try:
            info = of.measure(layer)
        except ValueError:
            return None, None, True
        info['plate'] = True
        target = of.PLATE_TARGET
    else:
        info = of.measure(image)
        target = fill
    optical = of.optical_diameter(info, target)
    scale, _ = of.layout_scale(info, target, size, True)
    return round(scale * optical / size, 3), round(optical, 3), plate


def collect(index_path, source_dir, size, fill):
    sources = of.pick_sources(source_dir)
    icons = []
    for name in of.index_targets(index_path):
        stem = os.path.splitext(name)[0].lower()
        source = sources.get(stem)
        if source is None:
            fallback = os.path.join(ROOT, 'web_icon', name)
            if not os.path.isfile(fallback):
                print(f'  跳过 {name}: 没有源图')
                continue
            source = fallback
            print(f'  没有高清源图，使用 {fallback}')
        auto, optical, plate = auto_value(source, size, fill)
        if auto is None:
            print(f'  跳过 {name}: 底板里没有检测到标志')
            continue
        icons.append({
            'name': name,
            'stem': stem,
            'plate': plate,
            'auto': auto,
            'optical': optical,
            'source': source,
        })
    return icons


def fingerprint(icons, size, quality):
    """来源文件与拟合常量的指纹；变了就说明现有变体该重渲染。"""
    params = {
        'size': size,
        'quality': quality,
        'reach_key': of.REACH_KEY,
        'plate_reach_key': of.PLATE_REACH_KEY,
        'thin_key': of.THIN_KEY,
        'thin_scale_key': of.THIN_SCALE_KEY,
        'plate_thin_key': of.PLATE_THIN_KEY,
        'plate_thin_scale_key': of.PLATE_THIN_SCALE_KEY,
        'thin_scale_ref': of.THIN_SCALE_REF,
        'width_ratio': of.WIDTH_RATIO,
        'plate_target': of.PLATE_TARGET,
        'edge_margin': of.EDGE_MARGIN,
        'center_tolerance': of.CENTER_TOLERANCE,
    }
    files = {}
    for icon in icons:
        stat = os.stat(icon['source'])
        files[icon['stem']] = [os.path.abspath(icon['source']), stat.st_mtime, stat.st_size]
    payload = json.dumps({'params': params, 'files': files}, sort_keys=True)
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()


def render_one(task):
    source, output, fill, size, quality, value = task
    if os.path.exists(output):
        return value, None, False
    try:
        with redirect_stdout(io.StringIO()):
            of.fit(source, output, fill, size, quality,
                   target=value / 100.0, limits=False)
        return value, None, True
    except Exception as exc:  # noqa: BLE001
        return value, str(exc), False


def write_data(path, fill, size, icons, low, high):
    rows = []
    for icon in icons:
        rows.append('        ' + json.dumps({
            'name': icon['name'],
            'stem': icon['stem'],
            'plate': icon['plate'],
            'auto': icon['auto'],
            'optical': icon['optical'],
        }, ensure_ascii=False))
    text = (
        '/* 由 tools/gen_lab.py 生成，勿手改。 */\n'
        'window.INFINITY_LAB = {\n'
        f'    "fill": {fill:.3f},\n'
        f'    "plate": {of.PLATE_TARGET:.3f},\n'
        f'    "reach": {of.REACH_KEY:.3f},\n'
        f'    "plate_reach": {of.PLATE_REACH_KEY:.3f},\n'
        f'    "thin": {of.THIN_KEY:.3f},\n'
        f'    "thin_scale": {of.THIN_SCALE_KEY:.3f},\n'
        f'    "plate_thin": {of.PLATE_THIN_KEY:.3f},\n'
        f'    "plate_thin_scale": {of.PLATE_THIN_SCALE_KEY:.3f},\n'
        f'    "thin_ref": {of.THIN_SCALE_REF:.3f},\n'
        f'    "width_ratio": {of.WIDTH_RATIO:.3f},\n'
        f'    "size": {size},\n'
        f'    "min": {low},\n'
        f'    "max": {high},\n'
        '    "icons": [\n' + ',\n'.join(rows) + '\n'
        '    ]\n'
        '};\n'
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        file.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='生成标定页的百分比变体与清单',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split('用法示例', 1)[-1].strip() if '用法示例' in __doc__ else None,
    )
    parser.add_argument('--index', default=os.path.join(ROOT, 'index.html'))
    parser.add_argument('--source', default=os.path.join(ROOT, 'ori_icon'),
                        help='高清源图目录（默认 ori_icon）')
    parser.add_argument('--out', default=os.path.join(ROOT, 'web_icon', 'lab'),
                        help='变体输出目录（默认 web_icon/lab）')
    parser.add_argument('--data', default=os.path.join(ROOT, 'js', 'lab-data.js'),
                        help='清单输出文件（默认 js/lab-data.js）')
    parser.add_argument('--fill', type=float, default=0.794,
                        help='裸标志的基准视觉直径（默认 0.794）')
    parser.add_argument('--size', type=int, default=140, help='画布边长（默认 140）')
    parser.add_argument('--quality', type=int, default=90, help='WebP 质量（默认 90）')
    parser.add_argument('--min', dest='low', type=int, default=30,
                        help='最小百分比（默认 30）')
    parser.add_argument('--max', dest='high', type=int, default=90,
                        help='最大百分比（默认 90）')
    parser.add_argument('--step', type=int, default=1, help='百分比步进（默认 1）')
    parser.add_argument('--force', action='store_true', help='忽略缓存，重渲染全部变体')
    parser.add_argument('--data-only', action='store_true', help='只写清单，不渲染图片')
    parser.add_argument('--jobs', type=int, default=os.cpu_count() or 1,
                        help='并行进程数（默认 CPU 核数）')
    args = parser.parse_args(argv)

    if not os.path.isfile(args.index):
        parser.error(f'找不到页面: {args.index}')
    if not os.path.isdir(args.source):
        parser.error(f'找不到源图目录: {args.source}')
    if not 0 < args.fill <= 1:
        parser.error('--fill 必须在 (0, 1] 之间')
    if not 0 < args.low < args.high <= 200 or args.step < 1:
        parser.error('需要 0 < --min < --max 且 --step >= 1')
    if args.size < 1:
        parser.error('--size 必须 >= 1')

    icons = collect(os.path.abspath(args.index), os.path.abspath(args.source),
                    args.size, args.fill)
    if not icons:
        raise SystemExit('没有收集到图标')
    values = list(range(args.low, args.high + 1, args.step))

    stamp_path = os.path.join(args.out, STAMP)
    digest = fingerprint(icons, args.size, args.quality)
    force = args.force
    if not force and os.path.isfile(stamp_path):
        try:
            with open(stamp_path, encoding='utf-8') as file:
                old = json.load(file)
            if old.get('fingerprint') != digest:
                print('检测到源图或拟合常量变化，重渲染全部变体')
                force = True
        except (OSError, ValueError):
            force = True
    elif not force:
        print('没有 stamp，按现有变体缓存处理')

    total = len(icons) * len(values)
    missing = sum(1 for icon in icons for value in values
                  if not os.path.isfile(os.path.join(args.out, icon['stem'], f'{value}.webp')))
    print(f'{len(icons)} 个图标 × {len(values)} 档（{args.low}%–{args.high}%）= {total} 个变体，'
          f'已有 {total - missing} 个')

    write_data(args.data, args.fill, args.size, icons, args.low, args.high)
    print(f'清单 -> {args.data}')

    failed = 0
    if not args.data_only:
        tasks = []
        for icon in icons:
            for value in values:
                tasks.append((icon['source'],
                              os.path.join(args.out, icon['stem'], f'{value}.webp'),
                              args.fill, args.size, args.quality, value))
        if force:
            for _, output, *_ in tasks:
                try:
                    os.remove(output)
                except OSError:
                    pass
        done = skipped = 0
        with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futures = [pool.submit(render_one, task) for task in tasks]
            for future in as_completed(futures):
                _, error, rendered = future.result()
                if error:
                    failed += 1
                    print(f'\n  失败: {error}')
                elif rendered:
                    done += 1
                else:
                    skipped += 1
                if (done + skipped + failed) % 100 == 0:
                    print(f'  渲染 {done + skipped + failed}/{total}', end='\r', flush=True)
        print(' ' * 40, end='\r')
        print(f'完成 {done} 个，复用 {skipped} 个，失败 {failed} 个')

    if failed or (args.data_only and missing):
        print('有缺失或失败，未写 stamp；下次运行会继续补齐')
        return 1

    os.makedirs(args.out, exist_ok=True)
    with open(stamp_path, 'w', encoding='utf-8') as file:
        json.dump({
            'fingerprint': digest,
            'fill': args.fill,
            'size': args.size,
            'quality': args.quality,
            'min': args.low,
            'max': args.high,
            'step': args.step,
        }, file, indent=2)
    return 0


if __name__ == '__main__':
    sys.exit(main())
