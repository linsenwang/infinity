#!/usr/bin/env python3
r"""按等效圆直径做图标的光学归一化。

图标在页面上以圆形显示（CSS border-radius: 50%）。--diameter 控制主体**等效圆
直径**占显示圆直径的比例，0.5 就是 0.5D；不同形状再按统一规则做视觉修正：

  * 背景     接近白色的灰色（例如 CASS 的浅灰纸面）统一改成纯白；
             彩色底板去掉白边后铺满整个画布，保留源图里的渐变与纹理。
  * 主体     白纸或透明背景时，可见图标是标志本身；贴着画布边缘的零散前景
             （例如白色纸边）会被去掉。彩色底板上的标志单独拆出来，按它自己的
             凸包计算大小——黑框、底板只当背景，不参与标志尺寸。
  * 等面积   按凸包面积折算等效圆直径；再按形状做两项光学修正：
             实心的长条、斜块视觉上比等面积圆更大，按外缘收敛；越接近圆的
             徽章尖角越少，越可以放大——按凸包圆形度 c 连续过渡到 COMPACT_MAX，
             四周留一圈，没有档位和阈值。字标圆形度低，基本保持原宽度。
  * 位置     小偏移时按源图画布中心摆放，保留设计稿的光学位置（字标往往不是
             几何居中）；偏移超过短边 2% 就当作裁切失误，连续过渡到外接框中心。
  * 安全区   外缘顶到圆边时收在圆内；边距随圆形度连续变化。

测量始终在原图分辨率上完成，最后一步才缩放并压成 WebP。目录模式会递归
查找源图，同名文件取分辨率最高的一个（同分辨率取文件更大的）。

用法示例
--------
# 单个图标，默认 diameter=0.6
python3 tools/optical_fit.py ori_icon/x.png -o web_icon/x.webp

# 按 index.html + js/config.js 里引用的图标批量更新；
# 源图在 ori_icon 里递归找高清版，输出写到 web_icon
python3 tools/optical_fit.py ori_icon -o web_icon --from-index index.html --diameter 0.6

# 只更新 web_icon 里已经有的图标（不读 index）
python3 tools/optical_fit.py ori_icon -o web_icon --diameter 0.6

# 处理源目录里的全部图片（包括 index 还没用到的）
python3 tools/optical_fit.py ori_icon -o web_icon --all

参数说明
--------
--diameter   主体等效圆直径 ÷ 显示圆直径（默认 0.6），唯一需要调的占比参数；
             实心斜块等形状会按外缘自动收小，圆形徽章会按圆形度放大，
             字标基本保持原来的宽度；彩色底板始终铺满画布，不受此参数影响。
             --fill 是旧名
--size       输出画布边长（默认 140，即 CSS 74px 的 2 倍）
-o/--output  输出文件或目录；省略时写在输入旁边，扩展名换 .webp
--quality    WebP 质量（默认 90）
--from-index 从 index.html（及其本地脚本）读取需要处理的图标；省略路径时用 index.html
--all        目录模式默认只更新输出目录里已有的同名图标；加 --all 全部输出
"""

import argparse
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

EDGE_MARGIN = 0.04          # 圆边安全距离，占半径的比例
COLOR_THRESHOLD = 40.0      # 与底板色的 RGB 距离阈值
ALPHA_MIN_COVERAGE = 0.003  # 透明像素超过这个比例就用 alpha 作为主体
PLATE_DISTANCE = 20.0       # 边框色离白色超过这个距离，视为可见彩色底板
SPREAD_REFERENCE = 1.25     # 方形/圆形的外缘半径与等效半径之比，作为无修正基准
SPREAD_WEIGHT = 0.50        # 实心形状的外缘对视觉尺寸的权重
COMPACT_MAX = 0.70          # 圆形徽章最多占画布直径的比例，四周留一圈
ROUND_REFERENCE = 0.70      # 圆角方块/紧凑外框的圆形度参考，达到即按满档缩放
CENTER_TOLERANCE = 0.02     # 墨迹中心偏离画布中心超过短边 2% 时视为裁切偏移
MARK_TOLERANCE = 60.0       # 拟合底板时，离边框色超过此值的像素不参与


def load_image(path):
    return Image.open(path).convert('RGBA')


def border_band(rgba, frac=0.08):
    h, w = rgba.shape[:2]
    b = max(1, round(min(h, w) * frac))
    return np.concatenate([
        rgba[:b, :, :3].reshape(-1, 3), rgba[-b:, :, :3].reshape(-1, 3),
        rgba[:, :b, :3].reshape(-1, 3), rgba[:, -b:, :3].reshape(-1, 3),
    ]).astype(np.float32)


def is_plate_source(rgba):
    """边框色是明显的彩色/深色时，视为有色底板（需要铺满并裁边）。"""
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    if (alpha < 0.5).mean() > ALPHA_MIN_COVERAGE:
        return False
    bg = np.median(border_band(rgba), axis=0)
    near_white = bool(bg.max() - bg.min() <= 8 and bg.min() >= 228)
    return (not near_white) and float(np.linalg.norm(bg - 255.0)) > PLATE_DISTANCE


def drop_border_components(mask):
    """去掉与画布边缘相连的前景连通块（例如彩色底板外面的白纸边）。"""
    img = Image.fromarray((mask * 255).astype(np.uint8), 'L').copy()
    h, w = mask.shape
    seeds = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    seeds += [(0, y) for y in range(1, h - 1)] + [(w - 1, y) for y in range(1, h - 1)]
    for point in seeds:
        if img.getpixel(point) == 255:
            ImageDraw.floodfill(img, point, 0, thresh=0)
    return np.asarray(img) > 127


def subject_mask(rgba):
    """返回 (主体蒙版, 底板色, 是否彩色底板, 原始边框色, 是否近白纸面)。

    有颜色的底板会铺满整个输出画布，只缩放上面的标志；白纸或透明背景
    则只保留标志本身。接近白色的灰色纸面（例如 CASS）会把纸面统一成纯白。
    """
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    if (alpha < 0.5).mean() > ALPHA_MIN_COVERAGE:
        return alpha, None, False, None, False

    bg = np.median(border_band(rgba), axis=0)
    near_white = bool(bg.max() - bg.min() <= 8 and bg.min() >= 228)
    plate = (not near_white) and float(np.linalg.norm(bg - 255.0)) > PLATE_DISTANCE
    dist = np.sqrt(((rgba[..., :3].astype(np.float32) - bg) ** 2).sum(axis=-1))
    subject = dist > COLOR_THRESHOLD
    if not plate and (subject[0, :].any() or subject[-1, :].any() or
                      subject[:, 0].any() or subject[:, -1].any()):
        trimmed = drop_border_components(subject)
        if trimmed.any() and trimmed.sum() >= subject.sum() * 0.3:
            subject = trimmed
    fill_bg = (255, 255, 255) if near_white else tuple(int(round(v)) for v in bg)
    return subject.astype(np.float32), fill_bg, plate, tuple(float(v) for v in bg), near_white


def convex_hull(points):
    """单调链凸包，points 为 Nx2 像素坐标。"""
    pts = np.unique(points, axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1], dtype=np.float64)


def polygon_area(poly):
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def measure(rgba):
    """在原图分辨率上测量主体：等效直径、外接尺寸、外缘距离与实心度。"""
    arr = np.asarray(rgba).astype(np.float32)
    mask, bg, plate, raw_bg, near_white = subject_mask(arr)
    h, w = arr.shape[:2]

    binary = mask > 0.5
    if not binary.any():
        raise ValueError('没有检测到主体')

    # 只取边界像素做凸包，结果与全部像素一致，但快很多
    inner = (binary[1:-1, 1:-1] & binary[:-2, 1:-1] & binary[2:, 1:-1] &
             binary[1:-1, :-2] & binary[1:-1, 2:])
    boundary = binary.copy()
    boundary[1:-1, 1:-1] &= ~inner
    by, bx = np.nonzero(boundary)
    hull = convex_hull(np.column_stack([bx, by]))
    if len(hull) < 3:
        raise ValueError('主体太小，无法计算凸包')

    bbox_w = float(bx.max() - bx.min() + 1)
    bbox_h = float(by.max() - by.min() + 1)
    extent = max(bbox_w, bbox_h)
    area = polygon_area(hull)
    d_eq = 2.0 * math.sqrt(area / math.pi)

    # 实心度：实际墨迹面积 ÷ 凸包面积。字标笔画稀疏，值明显小于 1。
    solidity = min(1.0, float(mask.sum()) / area) if area else 1.0
    # 圆形度：以凸包自身中心的半径衡量凸包有多接近圆，用来识别徽章/圆形标志
    hx = (hull[:, 0].min() + hull[:, 0].max()) / 2.0
    hy = (hull[:, 1].min() + hull[:, 1].max()) / 2.0
    hull_reach = float(np.hypot(hull[:, 0] - hx, hull[:, 1] - hy).max())
    circularity = (d_eq / (2.0 * hull_reach)) ** 2 if hull_reach > 0 else 1.0

    # 摆放中心：画布中心在小偏移时可信（保留设计稿的光学位置）；
    # 偏移大到像裁切失误时，连续过渡到标志的外接框中心。
    ink = ((float(bx.min()) + float(bx.max())) / 2.0,
           (float(by.min()) + float(by.max())) / 2.0)
    dx, dy = ink[0] - w / 2.0, ink[1] - h / 2.0
    r = math.hypot(dx, dy) / max(1.0, CENTER_TOLERANCE * min(w, h))
    r2 = r * r
    w_ink = r2 * r2 / (1.0 + r2 * r2)
    center = (w / 2.0 + dx * w_ink, h / 2.0 + dy * w_ink)
    reach = float(np.hypot(hull[:, 0] - center[0], hull[:, 1] - center[1]).max())

    return {
        'plate': plate,
        'alpha': bg is None,
        'bg': bg,
        'raw_bg': raw_bg,
        'near_white': near_white,
        'extent': extent,
        'area': area,
        'd_eq': d_eq,
        'solidity': solidity,
        'reach': reach,
        'circularity': circularity,
        'center': center,
        'hull': hull,
    }


def optical_diameter(info, fill):
    """等效圆直径的光学修正。

    1. 铺得开的实心形状（斜条、粗笔画）外缘伸得更远，视觉上比等面积圆更大：
       按外缘超出方形基准的比例放大"视觉直径"，放大系数按实心度加权——字标
       笔画稀疏，实心度低，几乎保持原来的宽度。
    2. 越接近圆的徽章，外凸尖角越少，越可以占满画布。凸包圆形度先按
       ROUND_REFERENCE 归一（圆角方块的常见圆形度就在 0.7 附近），再用 c³
       连续过渡：c=0 时就是 fill，c=1 时等效直径收敛到 COMPACT_MAX，
       四周留一圈，没有档位或阈值。
    """
    r_eq = info['d_eq'] / 2.0
    spread = info['reach'] / r_eq
    penalty = max(1.0, spread / SPREAD_REFERENCE) ** (SPREAD_WEIGHT * info['solidity'])
    compact = min(1.0, info['circularity'] / ROUND_REFERENCE) ** 3
    limit = max(fill, COMPACT_MAX)
    boost = (limit / fill) ** compact
    return info['d_eq'] * penalty / boost


def plate_bounds(rgba):
    """彩色底板的外接框：去掉源图边缘的白边/白脚，保留框内全部像素。"""
    arr = np.asarray(rgba).astype(np.float32)
    colored = np.abs(arr[..., :3] - 255.0).max(axis=-1) > 8.0
    ys, xs = np.nonzero(colored)
    if len(xs) == 0:
        return (0, 0, rgba.width, rgba.height)
    pad = max(1, round(min(rgba.size) * 0.002))
    return (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
            min(rgba.width, int(xs.max()) + 1 + pad),
            min(rgba.height, int(ys.max()) + 1 + pad))


def plate_parts(source):
    """把彩色底板拆成（底板背景图, 标志 RGBA）。

    标志按边框色的距离找，并去掉贴着画布边缘的白色纸边；底板用二次曲面
    拟合（排除标志和白边），这样渐变底板也能得到干净、无标志的背景。
    """
    arr = np.asarray(source.convert('RGB')).astype(np.float32)
    h, w = arr.shape[:2]
    base = np.median(border_band(np.asarray(source).astype(np.float32)), axis=0)
    dist = np.sqrt(((arr - base) ** 2).sum(axis=-1))
    mark = dist > COLOR_THRESHOLD
    if mark.any():
        trimmed = drop_border_components(mark)
        if trimmed.any():
            mark = trimmed

    plate_like = dist <= MARK_TOLERANCE
    valid = plate_like & ~mark
    if valid.sum() < 50:
        valid = ~mark

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx / max(w - 1, 1)) * 2.0 - 1.0
    ny = (yy / max(h - 1, 1)) * 2.0 - 1.0
    terms = np.stack([np.ones_like(nx), nx, ny, nx * nx, nx * ny, ny * ny], axis=-1)
    coef, *_ = np.linalg.lstsq(terms[valid], arr[valid], rcond=None)
    bg = np.clip(terms @ coef, 0, 255)

    resid = np.sqrt(((arr - bg) ** 2).sum(axis=-1))
    alpha = np.clip((resid - 10.0) / 30.0, 0, 1)
    gate = np.asarray(
        Image.fromarray((mark * 255).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(5))
    ) > 0
    alpha[~gate] = 0

    background = arr.copy()
    background[alpha > 0.02] = bg[alpha > 0.02]
    mark_rgba = np.dstack([arr, alpha * 255.0]).astype(np.uint8)
    return (Image.fromarray(background.astype(np.uint8), 'RGB'),
            Image.fromarray(mark_rgba, 'RGBA'))


def save_image(canvas, output_path, quality):
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    ext = os.path.splitext(output_path)[1].lower()
    if ext == '.webp':
        canvas.save(output_path, 'WEBP', quality=quality, method=6)
    elif ext in ('.jpg', '.jpeg'):
        canvas.convert('RGB').save(output_path, 'JPEG', quality=quality)
    else:
        canvas.save(output_path, 'PNG', optimize=True)


def fit(source_path, output_path, diameter, size, quality):
    source = load_image(source_path)
    before = os.path.getsize(source_path)

    if is_plate_source(np.asarray(source).astype(np.float32)):
        # 彩色底板：背景铺满画布；底板上的标志按它自己的凸包做光学归一化，
        # 黑框/底板只当背景，不参与标志尺寸的计算。
        plate = source.crop(plate_bounds(source))
        background, mark = plate_parts(plate)
        canvas = ImageOps.fit(background, (size, size), Image.LANCZOS)
        try:
            info = measure(mark)
        except ValueError:
            save_image(canvas, output_path, quality)
            after = os.path.getsize(output_path)
            print(f'{source_path}  {source.width}x{source.height} {before / 1024:.1f}KB')
            print(f'  -> {output_path}  {size}x{size} {after / 1024:.1f}KB'
                  f'  底板铺满 · 未检测到标志，保持源图')
            return 1.0, False
        scale = diameter * size / optical_diameter(info, diameter)
        cap = (size / 2.0) * (1 - EDGE_MARGIN * (1 - info['circularity']))
        if info['reach'] > 0:
            scale = min(scale, cap / info['reach'])
        new_w = max(1, round(mark.width * scale))
        new_h = max(1, round(mark.height * scale))
        icon = mark.resize((new_w, new_h), Image.LANCZOS)
        x = round(size / 2.0 - scale * info['center'][0])
        y = round(size / 2.0 - scale * info['center'][1])
        canvas.paste(icon, (x, y), icon)
        save_image(canvas, output_path, quality)
        actual_eq = scale * info['d_eq'] / size
        after = os.path.getsize(output_path)
        print(f'{source_path}  {source.width}x{source.height} {before / 1024:.1f}KB')
        print(f'  -> {output_path}  {size}x{size} {after / 1024:.1f}KB'
              f'  底板铺满 · 标志等径 {actual_eq * 100:.1f}% D'
              f' · 最宽 {scale * info["extent"] / size * 100:.1f}% D')
        return actual_eq, False

    info = measure(source)
    if info['near_white'] and not info['alpha']:
        # 近白灰纸面统一改纯白，避免源图底色作为一块浅灰方块被贴进来
        arr = np.array(source)
        raw = np.array(info['raw_bg'], np.float32)
        dist = np.sqrt(((arr[..., :3].astype(np.float32) - raw) ** 2).sum(axis=-1))
        arr[..., :3][dist <= 12] = 255
        source = Image.fromarray(arr, 'RGBA')
    radius = size / 2.0
    circle_area = math.pi * radius ** 2

    # 光学等效直径：等面积 + 外缘/实心度修正 + 圆形度放大
    d_opt = optical_diameter(info, diameter)
    scale = diameter * size / d_opt

    # 圆边安全区（按画布中心摆放，外缘也相对画布中心算）。
    # 越接近圆的徽章，外缘越没有尖角，安全边距也连续收到 0。
    cap = radius * (1 - EDGE_MARGIN * (1 - info['circularity']))
    fit_scale = cap / info['reach'] if info['reach'] > 0 else scale
    clamped = fit_scale < scale
    scale = min(scale, fit_scale)

    new_w = max(1, round(source.width * scale))
    new_h = max(1, round(source.height * scale))
    icon = source.resize((new_w, new_h), Image.LANCZOS)
    # 小偏移保留源图画布的设计位置；明显偏移（裁切失误）则按墨迹中心校正
    x = round(size / 2.0 - scale * info['center'][0])
    y = round(size / 2.0 - scale * info['center'][1])

    if info['alpha']:
        canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        canvas.paste(icon, (x, y), icon)
    else:
        # 白纸：背景铺满，只缩放主体；纸面色填满周围
        canvas = Image.new('RGB', (size, size), info['bg'])
        canvas.paste(icon, (x, y), icon.getchannel('A'))

    save_image(canvas, output_path, quality)

    actual_eq = scale * info['d_eq'] / size
    actual_opt = scale * d_opt / size
    actual_max = scale * info['extent'] / size
    actual_area = scale ** 2 * info['area'] / circle_area
    after = os.path.getsize(output_path)
    print(f'{source_path}  {source.width}x{source.height} {before / 1024:.1f}KB')
    print(f'  -> {output_path}  {size}x{size} {after / 1024:.1f}KB'
          f'  等径 {actual_eq * 100:.1f}% D · 视觉 {actual_opt * 100:.1f}% D'
          f' · 最宽 {actual_max * 100:.1f}% D'
          f' · 面积 {actual_area * 100:.1f}%'
          f' (目标 {diameter * 100:.0f}%{"，受圆边限制" if clamped else ""})')
    return actual_opt, clamped


def image_files(root):
    """递归列出目录下的图片；也接受单个文件。"""
    exts = ('.png', '.jpg', '.jpeg', '.webp')
    if os.path.isfile(root):
        return [root] if root.lower().endswith(exts) else []
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if name.lower().endswith(exts):
                paths.append(os.path.join(dirpath, name))
    return paths


def pick_sources(root):
    """同名源图取分辨率最高的；同分辨率取文件更大的（压缩更少）。"""
    best = {}
    for path in image_files(root):
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        with Image.open(path) as im:
            score = (im.width * im.height, os.path.getsize(path))
        if stem not in best or score > best[stem][0]:
            best[stem] = (score, path)
    return {stem: path for stem, (_, path) in best.items()}


def index_targets(index_path):
    """读 index.html 及其本地脚本里引用的 web_icon/ 文件名。"""
    index_path = os.path.abspath(index_path)
    root = os.path.dirname(index_path)
    with open(index_path, encoding='utf-8') as file:
        html = file.read()

    files = [index_path]
    for src in re.findall(r'<script[^>]+src=[\'"]([^\'"]+)[\'"]', html, re.I):
        if re.match(r'^(?:https?:)?//', src):
            continue
        path = os.path.normpath(os.path.join(root, src))
        if os.path.isfile(path) and path.lower().endswith('.js'):
            files.append(path)

    names = []
    pattern = re.compile(r'''web_icon/([^"')\s<>]+\.(?:webp|png|jpe?g))''', re.I)
    for path in files:
        with open(path, encoding='utf-8') as file:
            text = file.read()
        for match in pattern.finditer(text):
            name = os.path.basename(match.group(1))
            if name not in names:
                names.append(name)
    return names


def existing_targets(directory):
    result = {}
    if os.path.isdir(directory):
        for name in os.listdir(directory):
            if name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                result[os.path.splitext(name)[0].lower()] = name
    return result


def run_batch(input_dir, output_dir, diameter, size, quality, process_all):
    sources = pick_sources(input_dir)
    targets = existing_targets(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    done = skipped = failed = 0
    for stem, source in sources.items():
        if stem in targets:
            name = targets[stem]
        elif process_all:
            name = os.path.splitext(os.path.basename(source))[0] + '.webp'
        else:
            skipped += 1
            continue
        try:
            fit(source, os.path.join(output_dir, name), diameter, size, quality)
            done += 1
        except Exception as exc:
            failed += 1
            print(f'  失败 {source}: {exc}')
    print(f'\n完成 {done} 个，跳过 {skipped} 个（输出目录无同名图标），失败 {failed} 个')


def run_indexed(input_root, index_path, output_dir, diameter, size, quality):
    names = index_targets(index_path)
    if not names:
        print(f'{index_path} 里没有找到 web_icon/ 引用')
        return
    sources = pick_sources(input_root)
    os.makedirs(output_dir, exist_ok=True)
    done = missing = failed = 0
    for name in names:
        target = os.path.join(output_dir, name)
        source = sources.get(os.path.splitext(name)[0].lower())
        if source is None:
            if os.path.isfile(target):
                source = target
                print(f'  没有高清源图，使用现有文件: {target}')
            else:
                missing += 1
                print(f'  缺少源图: {name}')
                continue
        try:
            fit(source, target, diameter, size, quality)
            done += 1
        except Exception as exc:
            failed += 1
            print(f'  失败 {name}: {exc}')
    print(f'\n完成 {done} 个，缺少源图 {missing} 个，失败 {failed} 个')


def build_parser():
    parser = argparse.ArgumentParser(
        description='按等效圆直径做图标的光学归一化',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(__doc__.split('用法示例', 1)[1].lstrip('\n-')
                if '用法示例' in __doc__ else None),
    )
    parser.add_argument('input', help='输入图片或目录')
    parser.add_argument('-o', '--output',
                        help='输出文件或目录（默认与输入同目录，扩展名换 .webp）')
    parser.add_argument('--diameter', '--fill', dest='diameter', type=float, default=0.6,
                        help='主体等效圆直径 ÷ 圆直径，0~1（默认 0.6；--fill 同义；'
                             '圆形徽章会按圆形度自动放大，彩色底板始终铺满画布）')
    parser.add_argument('--size', type=int, default=140, help='输出画布边长（默认 140）')
    parser.add_argument('--quality', type=int, default=90, help='WebP 质量（默认 90）')
    parser.add_argument('--from-index', nargs='?', const='index.html', default=None,
                        metavar='HTML',
                        help='从 index.html（及其本地脚本）读取需要处理的图标；'
                             '省略路径时用 index.html')
    parser.add_argument('--all', action='store_true',
                        help='目录模式下处理全部源图，而不只是输出目录里已有的图标')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not os.path.exists(args.input):
        parser.error(f'输入不存在: {args.input}')
    if not 0 < args.diameter <= 1:
        parser.error('--diameter 必须在 (0, 1] 之间')
    if args.size < 1:
        parser.error('--size 必须 >= 1')
    if args.from_index is not None:
        if not os.path.isdir(args.input):
            parser.error('--from-index 模式需要把源图目录作为输入')
        if not os.path.isfile(args.from_index):
            parser.error(f'找不到 index 文件: {args.from_index}')
        output_dir = args.output or os.path.join(
            os.path.dirname(os.path.abspath(args.from_index)), 'web_icon')
        if os.path.isfile(output_dir):
            parser.error('--from-index 模式下 -o 必须是目录')
        run_indexed(args.input, args.from_index, output_dir,
                    args.diameter, args.size, args.quality)
        return 0

    if os.path.isdir(args.input):
        output_dir = args.output or args.input
        run_batch(args.input, output_dir, args.diameter, args.size, args.quality, args.all)
        return 0

    output = args.output
    if output is None:
        output = os.path.splitext(args.input)[0] + '.webp'
    elif os.path.isdir(output):
        output = os.path.join(output,
                              os.path.splitext(os.path.basename(args.input))[0] + '.webp')
    try:
        fit(args.input, output, args.diameter, args.size, args.quality)
    except Exception as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    sys.exit(main())
