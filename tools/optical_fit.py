#!/usr/bin/env python3
r"""用同一个全局函数做图标的光学归一化。

图标在页面上以圆形显示（CSS border-radius: 50%）。所有主体——白底标志、
透明标志、彩色底板上的标志——都用同一个尺寸函数定大小：

  visual = 外接框长边 × (包围圆直径 / 外接框长边) ** reach_key
                       × (外接框短边 / 外接框长边) ** thin_key

裸标志用 REACH_KEY / THIN_KEY；底板上的标志单独用 PLATE_REACH_KEY /
PLATE_THIN_KEY，因为底板已经提供了圆形外轮廓，标志自身的包围圆对观感
影响更大，细长修正则相对更弱。

  * 圆形     两项都等于 1，visual 就是外接框，可以占满 --diameter。
  * 方形     包围圆比外接框大，第一项把方形收到约 79% 的键线；短边等于
             长边，第二项不动，不会和圆形一样撑满画布。
  * 字标     短边远小于长边，第二项按细长程度连续放大：横排和竖排的标志
             都朝同一个视觉宽度长大，不再因为一条边短就显得小；放大到
             WIDTH_RATIO 倍目标为止。
  * 斜条     包围圆和外接框接近，第一项略收，第二项不动，外缘落在同一包络。
  指数都是常量，没有任何按形状分类的档位、圆形度阈值或实心度权重。
  两套指数来自手动标定（每个图标点 +/− 调到顺眼，再按
  log visual ~ log 包围圆比 + log 细长比 分组拟合）。

  * 背景     接近白色的灰色（例如 CASS 的浅灰纸面）统一改成纯白；
             彩色底板去掉白边后铺满整个画布，保留源图里的渐变与纹理。
  * 主体     白纸或透明背景时，可见图标是标志本身；贴着画布边缘的零散前景
             （例如白色纸边）会被去掉。彩色底板上的标志单独拆出来，按它自己的
             外接框计算大小——黑框、底板只当背景，不参与标志尺寸。
             底板和标志都走同一个 visual 函数，但底板上的标志固定用
             PLATE_TARGET：底板的色块已经提供了外轮廓，标志再跟 --fill
             一起缩放，低 fill 时彩盘会空、高 fill 时又和底板一起显大。
             底板本身铺满画布，是图标的背景而不是被放大的一层。
  * 位置     小偏移时按源图画布中心摆放，保留设计稿的光学位置（字标往往不是
             几何居中）；偏移超过短边 2% 就当作裁切失误，连续过渡到外接框中心。
  * 安全区   外缘顶到圆边时收在圆内，全图统一 EDGE_MARGIN；长边另外受
             WIDTH_RATIO 限制，细长字标不会一路长到贴住圆边。

测量始终在原图分辨率上完成，最后一步才缩放并压成 WebP。目录模式会递归
查找源图，同名文件取分辨率最高的一个（同分辨率取文件更大的）。
--preview 把这一批图标按页面上的圆形样式渲染成一张对照图，方便直接看
不同 --diameter 下是否均匀。

用法示例
--------
# 单个图标，默认 diameter=0.794
python3 tools/optical_fit.py ori_icon/x.png -o web_icon/x.webp

# 按 index.html + js/config.js 里引用的图标批量更新；
# 源图在 ori_icon 里递归找高清版，输出写到 web_icon
python3 tools/optical_fit.py ori_icon -o web_icon --from-index index.html --diameter 0.794

# 只更新 web_icon 里已经有的图标（不读 index）
python3 tools/optical_fit.py ori_icon -o web_icon --diameter 0.794

# 处理源目录里的全部图片（包括 index 还没用到的），并生成圆形对照图
python3 tools/optical_fit.py ori_icon -o web_icon --all --preview preview.png

参数说明
--------
--diameter   裸标志的视觉直径 ÷ 显示圆直径（默认 0.794），圆形主体可以占满
             这个比例，方形按包围圆收到约 79%，细长字标按短边比例放大，
             最多到目标的 WIDTH_RATIO 倍。--fill 是旧名
--plate-target 底板标志的视觉直径 ÷ 画布（默认 PLATE_TARGET=0.786）；
             底板本身始终铺满画布，只调上面的标志，不受 --diameter 影响
--uniform    同时设置上面两个值，等价于 --diameter X --plate-target X
--size       输出画布边长（默认 140，即 CSS 74px 的 2 倍）
-o/--output  输出文件或目录；省略时写在输入旁边，扩展名换 .webp
--quality    WebP 质量（默认 90）
--from-index 从 index.html（及其本地脚本）读取需要处理的图标；省略路径时用 index.html
--all        目录模式默认只更新输出目录里已有的同名图标；加 --all 全部输出
--preview    处理完后把结果按圆形显示样式拼成一张 PNG；省略路径时用 preview.png
"""

import argparse
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

EDGE_MARGIN = 0.04          # 圆边安全距离，占半径的比例
COLOR_THRESHOLD = 40.0      # 与底板色的 RGB 距离阈值
ALPHA_MIN_COVERAGE = 0.003  # 透明像素超过这个比例就用 alpha 作为主体
PLATE_DISTANCE = 20.0       # 边框色离白色超过这个距离，视为可见彩色底板
DEFAULT_FILL = 0.794        # 裸标志的默认视觉直径（--diameter / --fill 的默认值）
REACH_KEY = 0.691           # 裸标志：包围圆对外接框的修正强度
PLATE_REACH_KEY = 1.067     # 底板上的标志：底板提供外轮廓，包围圆的影响更大
THIN_KEY = 0.192            # 裸标志的细长修正（在 THIN_SCALE_REF 这个尺寸处）
THIN_SCALE_KEY = -0.203     # 细长修正随目标尺寸变化：小图标需要更强的细长放大
PLATE_THIN_KEY = 0.140      # 底板标志的细长修正（在 THIN_SCALE_REF 处）
PLATE_THIN_SCALE_KEY = -0.034  # 底板标志的细长修正随尺寸的变化（很弱）
THIN_SCALE_REF = 0.600      # 上面两个 THIN_KEY 对应的目标尺寸
WIDTH_RATIO = 1.50          # 长边上限 = 目标 × 1.50（裸标志 0.794 时即 1.19，实际受圆边限制）
PLATE_TARGET = 0.786        # 底板上的标志：占画布的固定比例，底板已经提供外轮廓
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


def classify(rgba):
    """统一的背景判定：(边框色, 是否近白纸面, 是否彩色底板, 是否透明底)。

    透明像素占多数时，主体就是 alpha；否则看边框色：近白（含浅灰纸面）
    只保留标志，明显有色/深色则视为铺满画布的底板。所有分支共用这一处。
    """
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    if (alpha < 0.5).mean() > ALPHA_MIN_COVERAGE:
        return None, False, False, True
    bg = np.median(border_band(rgba), axis=0)
    near_white = bool(bg.max() - bg.min() <= 8 and bg.min() >= 228)
    plate = (not near_white) and float(np.linalg.norm(bg - 255.0)) > PLATE_DISTANCE
    return tuple(float(v) for v in bg), near_white, plate, False


def is_plate_source(rgba):
    """边框色是明显的彩色/深色时，视为有色底板（需要铺满并裁边）。"""
    return classify(rgba)[2]


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
    bg, near_white, plate, alpha_bg = classify(rgba)
    if alpha_bg:
        return rgba[..., 3].astype(np.float32) / 255.0, None, False, None, False

    dist = np.sqrt(((rgba[..., :3].astype(np.float32) - np.array(bg)) ** 2).sum(axis=-1))
    subject = dist > COLOR_THRESHOLD
    if not plate and (subject[0, :].any() or subject[-1, :].any() or
                      subject[:, 0].any() or subject[:, -1].any()):
        trimmed = drop_border_components(subject)
        if trimmed.any() and trimmed.sum() >= subject.sum() * 0.3:
            subject = trimmed
    fill_bg = (255, 255, 255) if near_white else tuple(int(round(v)) for v in bg)
    return subject.astype(np.float32), fill_bg, plate, bg, near_white


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
    """在原图分辨率上测量主体：外接尺寸、等效直径、外缘距离与摆放中心。"""
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
        'bbox_w': bbox_w,
        'bbox_h': bbox_h,
        'area': area,
        'd_eq': d_eq,
        'reach': reach,
        'center': center,
        'hull': hull,
    }


def thin_key_for(info, target):
    """细长指数随目标尺寸变化：小图标需要更强的细长放大，大图标要收一点。

    target 是这次渲染的视觉直径（--fill / PLATE_TARGET / 标定页的单个值），
    所以同一个图标在 43% 和 79% 下会得到不同的细长修正；这也让标定页
    预渲染的每一档 v 都天然带着对应尺寸的修正。
    """
    if target is None:
        target = PLATE_TARGET if info.get('plate') else DEFAULT_FILL
    target = max(float(target), 1e-4)
    ratio = math.log(target / THIN_SCALE_REF)
    if info.get('plate'):
        return PLATE_THIN_KEY + PLATE_THIN_SCALE_KEY * ratio
    return THIN_KEY + THIN_SCALE_KEY * ratio


def optical_diameter(info, target=None):
    """视觉直径：外接框长边，乘两个连续的形状修正。

    1. 包围圆：外接框点到摆放中心的最远距离 ×2。圆形主体与长边相等，
       占满目标比例；方形、斜块的包围圆更大，视觉直径变大，外框收到更小。
       指数按主体类型分开：裸标志用 REACH_KEY，底板上的标志用
       PLATE_REACH_KEY（底板已经提供了圆形外轮廓，标志自身的包围圆影响更大）。
    2. 细长：短边 / 长边。短边越短，视觉直径越小，缩放越大、长边越长——
       横排字标（CEIC、kaggle）和竖排标志走同一条规则，大小不再只由一条
       边决定；长边最终由 WIDTH_RATIO 倍目标收住。
       细长指数还随目标尺寸变化（见 thin_key_for），裸标志和底板各一套基准。

    指数来自两轮不同尺寸的手动标定，没有形状分类或档位。
    """
    extent = info['extent']
    if extent <= 0:
        return extent
    short = min(info['bbox_w'], info['bbox_h'])
    reach_ratio = max(1.0, 2.0 * info['reach'] / extent)
    thin_ratio = min(1.0, max(short, 0.5) / extent)
    key = thin_key_for(info, target)
    if info.get('plate'):
        return extent * reach_ratio ** PLATE_REACH_KEY * thin_ratio ** key
    return extent * reach_ratio ** REACH_KEY * thin_ratio ** key


def layout_scale(info, target, size, limits=True):
    """按视觉直径换算缩放比例；长边受宽度键线限制，外缘受圆边限制。

    target 是这类主体的视觉直径占画布的比例：裸标志用 --fill，底板标志用
    PLATE_TARGET。宽度键线按 target 等比例缩放，否则底板里的细长字标会被
    画布级的上限放大，和同一块底板上的紧凑标志差出一倍多。

    limits=False 时不做键线收敛，请求的视觉直径就是渲染出来的大小——
    手动标定页用它，保证按钮上的数字和眼睛看到的一致。
    """
    scale = target * size / optical_diameter(info, target)
    if not limits:
        return scale, None
    width_cap = (WIDTH_RATIO * target * size / info['extent']
                 if info['extent'] > 0 else scale)
    reach_cap = (size / 2.0) * (1 - EDGE_MARGIN)
    circle_cap = reach_cap / info['reach'] if info['reach'] > 0 else scale
    limit = min(scale, width_cap, circle_cap)
    if limit >= scale:
        return scale, None
    return limit, ('circle' if circle_cap <= width_cap else 'width')


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
    # 圆角方形底板的四个白角本来就落在画布内：深色模式反色后会变成一圈暗边。
    # 只填与画布边缘相连的近白像素，标志里的白色笔画不受影响。
    white = arr.min(axis=-1) > 232
    if white.any():
        edge_white = white & ~drop_border_components(white)
        background[edge_white] = bg[edge_white]
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


def fit(source_path, output_path, diameter, size, quality, target=None, limits=True,
        plate_target=None):
    source = load_image(source_path)
    before = os.path.getsize(source_path)
    plate = is_plate_source(np.asarray(source).astype(np.float32))

    if plate:
        # 彩色底板：背景铺满画布；底板上的标志按视觉直径缩放，
        # 黑框/底板只当背景，不参与标志尺寸的计算。
        background, layer = plate_parts(source.crop(plate_bounds(source)))
        canvas = ImageOps.fit(background, (size, size), Image.LANCZOS).convert('RGBA')
        try:
            info = measure(layer)
        except ValueError:
            save_image(canvas, output_path, quality)
            after = os.path.getsize(output_path)
            print(f'{source_path}  {source.width}x{source.height} {before / 1024:.1f}KB')
            print(f'  -> {output_path}  {size}x{size} {after / 1024:.1f}KB'
                  f'  底板铺满 · 未检测到标志，保持源图')
            return {'path': output_path, 'visual': None, 'extent': None,
                    'clamped': False, 'plate': True}
        # 标志层是透明底，measure() 会把它当普通标志；这里明确标记成底板标志，
        # 让 optical_diameter() 使用 PLATE_REACH_KEY。
        info['plate'] = True
    else:
        info = measure(source)
        if info['near_white'] and not info['alpha']:
            # 近白灰纸面统一改纯白，避免源图底色作为一块浅灰方块被贴进来
            arr = np.array(source)
            raw = np.array(info['raw_bg'], np.float32)
            dist = np.sqrt(((arr[..., :3].astype(np.float32) - raw) ** 2).sum(axis=-1))
            arr[..., :3][dist <= 12] = 255
            source = Image.fromarray(arr, 'RGBA')
        layer = source
        if info['alpha']:
            canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        else:
            # 白纸：纸面色铺满周围，只缩放主体
            canvas = Image.new('RGB', (size, size), info['bg'])

    # 底板上的标志用 PLATE_TARGET：底板已经铺满画布并提供了外轮廓，
    # 标志不跟着 --fill 一起缩小，否则低 fill 时彩盘会显得空。
    # target 显式给出时优先（手动标定页按每个图标自己的视觉直径渲染）。
    if target is None:
        target = (plate_target if plate_target is not None else PLATE_TARGET) \
            if plate else diameter
    scale, limit = layout_scale(info, target, size, limits)
    new_w = max(1, round(layer.width * scale))
    new_h = max(1, round(layer.height * scale))
    icon = layer.resize((new_w, new_h), Image.LANCZOS)
    # 小偏移保留源图画布的设计位置；明显偏移（裁切失误）则按墨迹中心校正
    x = round(size / 2.0 - scale * info['center'][0])
    y = round(size / 2.0 - scale * info['center'][1])
    canvas.paste(icon, (x, y), icon.getchannel('A') if icon.mode == 'RGBA' else None)
    save_image(canvas, output_path, quality)

    visual = scale * optical_diameter(info, target) / size
    extent = scale * info['extent'] / size
    equal = scale * info['d_eq'] / size
    after = os.path.getsize(output_path)
    scope = '底板铺满 · 标志' if plate else ''
    note = {'circle': '，受圆边限制', 'width': '，受宽度键线限制'}.get(limit, '')
    print(f'{source_path}  {source.width}x{source.height} {before / 1024:.1f}KB')
    print(f'  -> {output_path}  {size}x{size} {after / 1024:.1f}KB'
          f'  {scope}视觉 {visual * 100:.1f}% D'
          f' · 外接 {extent * 100:.1f}% D · 等径 {equal * 100:.1f}% D'
          f' (目标 {target * 100:.0f}% D{note})')
    return {'path': output_path, 'visual': visual, 'extent': extent,
            'clamped': limit is not None, 'plate': plate}


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


def preview_sheet(results, output_path, display=74, scale=2):
    """把一批结果按页面上的圆形样式排成对照图。

    每格的上限直径用 --diameter 画出来是同一圈，所有图标都按这一圈对齐；
    圆形底板铺满画布，白底标志只看标志本身的视觉直径。这样可以直接肉眼
    检查一批图标是否均匀，而不必逐个打开。
    """
    if not results:
        return None
    tile = display * scale
    gap = 22
    caption = 15 * scale // 2
    cols = min(7, len(results))
    rows = (len(results) + cols - 1) // cols
    sheet = Image.new('RGB', (gap + cols * (tile + gap), gap + rows * (tile + gap + caption)),
                      '#ffffff')
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=11 * scale)
    except TypeError:
        font = ImageFont.load_default()
    mask = Image.new('L', (tile, tile), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, tile - 1, tile - 1), fill=255)
    for index, result in enumerate(results):
        icon = load_image(result['path'])
        plate = result.get('plate')
        tile_img = Image.new('RGB', (tile, tile), '#ffffff')
        if not plate:
            tile_img.paste(Image.new('RGB', (tile, tile), '#f4f4f7'), (0, 0), mask)
        art = icon.resize((tile, tile), Image.LANCZOS)
        tile_img.paste(art, (0, 0), art.getchannel('A'))
        x = gap + (index % cols) * (tile + gap)
        y = gap + (index // cols) * (tile + gap + caption)
        sheet.paste(tile_img, (x, y), mask)
        draw.ellipse((x, y, x + tile - 1, y + tile - 1), outline='#d8d8de')
        name = os.path.splitext(os.path.basename(result['path']))[0][:22]
        draw.text((x, y + tile + scale), name, fill='#555555', font=font)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    sheet.save(output_path, 'PNG', optimize=True)
    return output_path


def summarise(results):
    """打印这一批的视觉直径与实际外接分布。

    视觉直径由全局函数归一，裸标志和底板标志分组统计；外接长边则按形状自然
    分开（圆形满格、方形约 79%、细长字标更大），受键线限制的个数单独报出来。
    """
    values = [r for r in results if r.get('visual')]
    if not values:
        return
    for label, is_plate in (('裸标志', False), ('底板标志', True)):
        group = [r['visual'] for r in values if bool(r.get('plate')) == is_plate]
        if not group:
            continue
        mean = sum(group) / len(group)
        spread = math.sqrt(sum((v - mean) ** 2 for v in group) / len(group))
        print(f'{label} 视觉直径 {min(group) * 100:.1f}%–{max(group) * 100:.1f}% D'
              f'，均值 {mean * 100:.1f}% D，标准差 {spread * 100:.2f}%')
    extents = [r['extent'] for r in results if r.get('extent')]
    limited = sum(1 for r in results if r.get('clamped'))
    if extents:
        print(f'外接长边 {min(extents) * 100:.1f}%–{max(extents) * 100:.1f}% D'
              f'，{limited} 个受键线限制')


def run_batch(input_dir, output_dir, diameter, size, quality, process_all, preview=None,
              plate_target=None):
    sources = pick_sources(input_dir)
    targets = existing_targets(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    done = skipped = failed = 0
    results = []
    for stem, source in sources.items():
        if stem in targets:
            name = targets[stem]
        elif process_all:
            name = os.path.splitext(os.path.basename(source))[0] + '.webp'
        else:
            skipped += 1
            continue
        try:
            results.append(fit(source, os.path.join(output_dir, name),
                               diameter, size, quality, plate_target=plate_target))
            done += 1
        except Exception as exc:
            failed += 1
            print(f'  失败 {source}: {exc}')
    print(f'\n完成 {done} 个，跳过 {skipped} 个（输出目录无同名图标），失败 {failed} 个')
    summarise(results)
    if preview:
        path = preview_sheet(results, preview, size, 1)
        if path:
            print(f'对照图 -> {path}')


def run_indexed(input_root, index_path, output_dir, diameter, size, quality, preview=None,
                plate_target=None):
    names = index_targets(index_path)
    if not names:
        print(f'{index_path} 里没有找到 web_icon/ 引用')
        return
    sources = pick_sources(input_root)
    os.makedirs(output_dir, exist_ok=True)
    done = missing = failed = 0
    results = []
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
            results.append(fit(source, target, diameter, size, quality,
                               plate_target=plate_target))
            done += 1
        except Exception as exc:
            failed += 1
            print(f'  失败 {name}: {exc}')
    print(f'\n完成 {done} 个，缺少源图 {missing} 个，失败 {failed} 个')
    summarise(results)
    if preview:
        path = preview_sheet(results, preview, size, 1)
        if path:
            print(f'对照图 -> {path}')


def build_parser():
    parser = argparse.ArgumentParser(
        description='用全局视觉直径函数做图标的光学归一化',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(__doc__.split('用法示例', 1)[1].lstrip('\n-')
                if '用法示例' in __doc__ else None),
    )
    parser.add_argument('input', help='输入图片或目录')
    parser.add_argument('-o', '--output',
                        help='输出文件或目录（默认与输入同目录，扩展名换 .webp）')
    parser.add_argument('--diameter', '--fill', dest='diameter', type=float, default=0.794,
                        help='裸标志的视觉直径 ÷ 圆直径，0~1（默认 0.794；--fill 同义；'
                             '圆形主体可占满，方形按包围圆收到更小，细长字标按'
                             '短边放大；底板标志不受它影响，用 --plate-target）')
    parser.add_argument('--plate-target', type=float, default=None,
                        help=f'底板标志的视觉直径 ÷ 画布（默认 {PLATE_TARGET:.3f}）；'
                             '底板本身始终铺满画布，只调上面的标志')
    parser.add_argument('--uniform', type=float, default=None,
                        help='同时设置裸标志和底板标志的视觉直径，'
                             '等价于 --fill X --plate-target X（会覆盖这两个参数）')
    parser.add_argument('--size', type=int, default=140, help='输出画布边长（默认 140）')
    parser.add_argument('--quality', type=int, default=90, help='WebP 质量（默认 90）')
    parser.add_argument('--from-index', nargs='?', const='index.html', default=None,
                        metavar='HTML',
                        help='从 index.html（及其本地脚本）读取需要处理的图标；'
                             '省略路径时用 index.html')
    parser.add_argument('--all', action='store_true',
                        help='目录模式下处理全部源图，而不只是输出目录里已有的图标')
    parser.add_argument('--preview', nargs='?', const='preview.png', default=None,
                        metavar='PNG',
                        help='处理完后把结果按圆形显示样式拼成一张对照图；'
                             '省略路径时用 preview.png')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not os.path.exists(args.input):
        parser.error(f'输入不存在: {args.input}')
    if args.uniform is not None:
        if not 0 < args.uniform <= 1:
            parser.error('--uniform 必须在 (0, 1] 之间')
        args.diameter = args.uniform
        args.plate_target = args.uniform
    if not 0 < args.diameter <= 1:
        parser.error('--diameter 必须在 (0, 1] 之间')
    if args.plate_target is not None and not 0 < args.plate_target <= 1:
        parser.error('--plate-target 必须在 (0, 1] 之间')
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
                    args.diameter, args.size, args.quality, args.preview,
                    plate_target=args.plate_target)
        return 0

    if os.path.isdir(args.input):
        output_dir = args.output or args.input
        run_batch(args.input, output_dir, args.diameter, args.size, args.quality,
                  args.all, args.preview, plate_target=args.plate_target)
        return 0

    output = args.output
    if output is None:
        output = os.path.splitext(args.input)[0] + '.webp'
    elif os.path.isdir(output):
        output = os.path.join(output,
                              os.path.splitext(os.path.basename(args.input))[0] + '.webp')
    try:
        result = fit(args.input, output, args.diameter, args.size, args.quality,
                     plate_target=args.plate_target)
    except Exception as exc:
        parser.error(str(exc))
    if args.preview:
        print(f'对照图 -> {preview_sheet([result], args.preview, args.size, 1)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
