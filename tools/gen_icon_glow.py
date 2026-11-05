#!/usr/bin/env python3
"""按图标颜色生成站点图标和搜索按钮的悬停阴影颜色，写入 css/icon-glow.css。

颜色在构建时算好，页面里不做 canvas 取色，悬停时没有额外开销。
新增或更换图标后重新执行（图标来自 index.html 与 js/config.js）：

    python3 tools/gen_icon_glow.py

取色规则
--------
- 先把透明像素按实际底色（--tile-bg，默认白）铺平，得到屏幕上看到的样子；
- 主色取占比最高的鲜艳色，图标本身是黑白时取占比最高的深色；
- 再用整幅图的平均色按图标饱和度混合：主色越鲜艳越保留本色，
  越接近黑白越偏向平均色——所以白底黑 Logo 的图标（ChatGPT、CS285 等）
  得到的是浅灰阴影，深色瓷砖图标（GitHub、6.031）保持深色；
- 混合出的颜色如果太浅（如 txtr、goodreads、gsh 这类浅色图标），
  在白色页面上几乎看不出阴影，因此用一条连续曲线按亮度压暗，保持色相不变；
  饱和度越高压得越少，cyweather、gfont 这类鲜艳的浅色保持本色。

深色模式下图标会被 CSS 反色（invert(88%) hue-rotate(180deg)），
所以深色阴影用同一段滤镜链把颜色换算成屏幕上实际显示的颜色。
"""

import math
import re
import colorsys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / 'index.html'
OUTPUT = ROOT / 'css' / 'icon-glow.css'

ALPHA = 0.45
INVERT = 0.88
WHITE = (255, 255, 255)

# 浅色阴影在白色页面上太淡，用 softmin 把亮度连续压向 GLOW_CAP；
# GLOW_SOFTNESS 越大，压暗从越暗的颜色开始生效、过渡越平缓。
# 饱和度越高压暗得越少：灰白图标全量压暗，鲜艳图标保持原色
GLOW_CAP = 150
GLOW_SOFTNESS = 14
PALE_SATURATION = 0.15
VIVID_SATURATION = 0.5


def clamp(value):
    return max(0, min(255, round(value)))


def luma(color):
    return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]


def deepen_pale(color):
    """压低浅色的亮度，饱和度越高压得越少，色相保持不变。

    亮度先用 softmin 连续压向 GLOW_CAP：深色几乎不变，浅色逐渐贴到上限，
    中间平滑过渡；再按饱和度加权——饱和度不超过 PALE_SATURATION 时全量
    压暗，达到 VIVID_SATURATION 后完全保留原色，所以鲜艳的浅色不会被压灰。
    """
    value = luma(color)
    if value <= 0:
        return color
    target = -GLOW_SOFTNESS * math.log(
        math.exp(-value / GLOW_SOFTNESS) + math.exp(-GLOW_CAP / GLOW_SOFTNESS)
    )
    saturation = colorsys.rgb_to_hsv(*(channel / 255 for channel in color))[1]
    t = (saturation - PALE_SATURATION) / (VIVID_SATURATION - PALE_SATURATION)
    t = max(0.0, min(1.0, t))
    pale = 1 - t * t * (3 - 2 * t)
    scale = (value + (target - value) * pale) / value
    return tuple(clamp(channel * scale) for channel in color)


def is_near_white(color):
    return min(color) >= 235 and max(color) - min(color) <= 12


def analyze_icon(path, background):
    """返回图标在给定底色上混合出的颜色（0-255 的 RGB，未按亮度压暗）。"""
    image = Image.open(path).convert('RGBA')
    image.thumbnail((96, 96))

    # 透明区域按实际底色铺平，参与平均色计算
    flat = Image.new('RGB', image.size, background)
    flat.paste(image, mask=image.getchannel('A'))
    pixels = list(flat.getdata())

    mean = tuple(sum(p[i] for p in pixels) / len(pixels) for i in range(3))

    bins = Counter()
    vivid_bins = Counter()
    for r, g, b in pixels:
        _, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if value >= 0.94 and saturation <= 0.12:  # 近白底色
            continue
        key = (r // 16, g // 16, b // 16)
        bins[key] += 1
        if saturation >= 0.25 and value >= 0.15:
            vivid_bins[key] += 1

    if bins:
        total = sum(bins.values())
        vivid_total = sum(vivid_bins.values())
        source = vivid_bins if vivid_total >= max(24, total * 0.10) else bins
        key = source.most_common(1)[0][0]

        # 量化桶只用来选出主色，实际颜色取桶内像素的平均值
        acc = [0, 0, 0]
        count = 0
        for r, g, b in pixels:
            if (r // 16, g // 16, b // 16) == key:
                acc[0] += r
                acc[1] += g
                acc[2] += b
                count += 1
        dominant = tuple(v / count for v in acc)
    else:
        dominant = mean

    # 主色饱和度越高越保留本色，越灰越偏向整幅图的平均亮度
    _, saturation, _ = colorsys.rgb_to_hsv(*(v / 255 for v in dominant))
    weight = 0.35 + 0.35 * saturation
    return tuple(
        clamp(weight * dominant[i] + (1 - weight) * mean[i])
        for i in range(3)
    )


def dark_variant(color):
    """按 CSS 的 invert(88%) hue-rotate(180deg) 换算深色模式下的显示色。"""
    r, g, b = (v / 255 for v in color)
    r, g, b = (
        r * (1 - INVERT) + (1 - r) * INVERT,
        g * (1 - INVERT) + (1 - g) * INVERT,
        b * (1 - INVERT) + (1 - b) * INVERT,
    )
    # hue-rotate(180deg) 的滤镜矩阵
    return (
        clamp((-0.574 * r + 1.430 * g + 0.144 * b) * 255),
        clamp((0.426 * r + 0.430 * g + 0.144 * b) * 255),
        clamp((0.426 * r + 1.430 * g - 0.856 * b) * 255),
    )


def parse_hex(value):
    value = value.lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    if len(value) != 6:
        return None
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def collect_icons(html, config_js):
    """返回 {src: {'site', 'search', 'tile_bg'}}，按出现顺序。

    site 图标来自 index.html，tile_bg 取自同一 <a> 的内联样式；
    search 图标来自 js/config.js 的 searchEngines。
    """
    icons = {}

    def entry(src, context, tile_bg=None):
        info = icons.setdefault(
            src, {'site': False, 'search': False, 'tile_bg': None}
        )
        info[context] = True
        if tile_bg is not None and info['tile_bg'] is None:
            info['tile_bg'] = tile_bg

    pattern = re.compile(
        r'<a\b([^>]*)>[\s\S]*?<img[^>]*src="(web_icon/[^"]+)"[\s\S]*?</a>'
    )
    for attributes, src in pattern.findall(html):
        match = re.search(r'--tile-bg:\s*(#[0-9a-fA-F]{3,8})', attributes)
        entry(src, 'site', parse_hex(match.group(1)) if match else None)

    for src in re.findall(r"icon:\s*'([^']+)'", config_js):
        if src.startswith('web_icon/'):
            entry(src, 'search')

    return icons


def rule_selectors(src, info):
    selectors = []
    if info['site']:
        selectors.append('.site img[src="%s"]' % src)
    if info['search']:
        selectors.append('.search-button img[src="%s"]' % src)
    return selectors


def make_rule(src, info, color):
    selectors = rule_selectors(src, info)
    if not selectors:
        return None
    return ',\n'.join(selectors) + ' { --icon-glow: rgba(%d, %d, %d, %s); }' % (
        *color, ALPHA
    )


def indent(text):
    return '\n'.join('    ' + line for line in text.split('\n'))


def build_css(icons):
    light_rules = []
    dark_rules = []

    for src, info in icons.items():
        path = ROOT / src
        if not path.exists():
            print('missing:', src)
            continue

        color = analyze_icon(path, info['tile_bg'] or WHITE)
        if is_near_white(color):
            continue
        color = deepen_pale(color)

        light_rules.append(make_rule(src, info, color))
        dark_rules.append(make_rule(src, info, dark_variant(color)))

    lines = [
        '/* 由 tools/gen_icon_glow.py 生成，请勿手改 */',
        '',
        *light_rules,
    ]
    if dark_rules:
        lines += ['', '@media (prefers-color-scheme: dark) {']
        lines += [indent(rule) for rule in dark_rules]
        lines += ['}']
    return '\n'.join(lines) + '\n'


def main():
    html = INDEX.read_text(encoding='utf-8')
    config_js = (ROOT / 'js' / 'config.js').read_text(encoding='utf-8')
    icons = collect_icons(html, config_js)
    css = build_css(icons)
    OUTPUT.write_text(css, encoding='utf-8')
    print('wrote %s (%d icons)' % (OUTPUT.relative_to(ROOT), css.count('--icon-glow')))


if __name__ == '__main__':
    main()
