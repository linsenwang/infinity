#!/usr/bin/env python3
"""图标处理流水线：补边成正方形 → 缩到显示尺寸 → 存 WebP。

默认用白底把图标补成正方形：透明区域和不成比例留下的空隙都填白，不需要任何参数。
补边颜色、厚度可调，也可以用 --pad gradient 复现 icon_gen.ipynb 的补边算法
（用原图上下边缘的平均色生成垂直渐变背景）。

用法示例
--------
# 默认：140px WebP，白底补成正方形
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.webp

# 白底 + 四周各留 5% 的边（--scale 0.9）
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.webp --scale 0.9

# 换补边颜色
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.webp --border-color '#1a1a1a'

# 上下边缘渐变补边（icon_gen.ipynb 的做法），并整体上移 3.5%
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.webp --pad gradient --scale 0.9 --offset-y -0.035

# 只要透明背景的正方形
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.png --pad none

参数说明
--------
--size          输出画布边长（默认 140，即 CSS 显示尺寸 70px 的 2 倍）
--scale         图标占画布的比例（0~1，默认 1.0）；边框厚度 = (1 - scale) / 2 × 边长
--border-width  直接用像素指定边框厚度，优先于 --scale
--offset-x/y    图标相对画布中心的偏移，单位为画布边长的比例（同 icon_gen.ipynb）
--pad           补边方式：solid（纯色，默认）/ gradient（上下边缘渐变）/ none（透明）
--border-color  补边颜色，支持 #rgb / #rrggbb（默认 #ffffff，配合 --pad solid）
--quality       WebP / JPEG 质量（默认 90）
--backup-dir    写入前若输出文件已存在，先把它备份到这个目录
"""

import argparse
import os
import shutil
import sys

from PIL import Image


def load_image(path):
    """打开图片；带透明通道的保留 RGBA，其余转 RGB。"""
    image = Image.open(path)
    has_alpha = image.mode in ('RGBA', 'LA', 'PA') or (
        image.mode == 'P' and 'transparency' in image.info
    )
    return image.convert('RGBA' if has_alpha else 'RGB')


def edge_average_color(image, row):
    """取第 row 行的平均色，作为渐变背景的一端。"""
    rgb = image.convert('RGB')
    width, _ = rgb.size
    pixels = rgb.load()
    r = g = b = 0
    for x in range(width):
        pr, pg, pb = pixels[x, row]
        r += pr
        g += pg
        b += pb
    return (r // width, g // width, b // width)


def gradient_background(size, top_color, bottom_color):
    """自上而下从 top_color 渐变到 bottom_color 的正方形画布。"""
    canvas = Image.new('RGB', (size, size))
    pixels = canvas.load()
    for y in range(size):
        t = y / (size - 1) if size > 1 else 0.5
        row_color = tuple(
            round((1 - t) * top_color[i] + t * bottom_color[i]) for i in range(3)
        )
        for x in range(size):
            pixels[x, y] = row_color
    return canvas


def parse_color(value):
    """解析 #rgb / #rrggbb 颜色。"""
    text = value.lstrip('#')
    if len(text) == 3:
        text = ''.join(c * 2 for c in text)
    if len(text) != 6:
        raise argparse.ArgumentTypeError(f'颜色格式不对: {value}，应为 #rgb 或 #rrggbb')
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def build_background(size, pad, source, border_color):
    """按补边方式生成正方形背景画布。"""
    if pad == 'gradient':
        top = edge_average_color(source, 0)
        bottom = edge_average_color(source, source.height - 1)
        return gradient_background(size, top, bottom)
    if pad == 'solid':
        return Image.new('RGB', (size, size), border_color)
    return Image.new('RGBA', (size, size), (0, 0, 0, 0))


def process(source_path, output_path, args):
    source = load_image(source_path)

    # 边框厚度：--border-width 优先，否则由 --scale 换算
    if args.border_width is not None:
        border = args.border_width
    else:
        border = round((1 - args.scale) * args.size / 2)
    border = max(0, min(border, (args.size - 1) // 2))
    inner = max(1, args.size - 2 * border)

    icon = source.copy()
    icon.thumbnail((inner, inner), Image.LANCZOS)   # 等比缩放到 inner 见方的框内
    icon_w, icon_h = icon.size

    canvas = build_background(args.size, args.pad, source, args.border_color)
    x = (args.size - icon_w) // 2 + round(args.offset_x * args.size)
    y = (args.size - icon_h) // 2 + round(args.offset_y * args.size)

    if icon.mode == 'RGBA':
        canvas.paste(icon, (x, y), icon.getchannel('A'))
    else:
        canvas.paste(icon, (x, y))

    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    if args.backup_dir and os.path.isfile(output_path):
        os.makedirs(args.backup_dir, exist_ok=True)
        shutil.copy2(output_path, os.path.join(args.backup_dir, os.path.basename(output_path)))

    ext = os.path.splitext(output_path)[1].lower()
    if ext == '.webp':
        canvas.save(output_path, 'WEBP', quality=args.quality, method=6)
    elif ext in ('.jpg', '.jpeg'):
        # JPEG 不支持透明，透明区域填白
        flat = canvas if canvas.mode == 'RGB' else Image.alpha_composite(
            Image.new('RGBA', canvas.size, (255, 255, 255, 255)), canvas).convert('RGB')
        flat.save(output_path, 'JPEG', quality=args.quality)
    else:
        canvas.save(output_path)

    before = os.path.getsize(source_path)
    after = os.path.getsize(output_path)
    geom = f'{icon_w}x{icon_h} + {border}px 边框' if border else f'{icon_w}x{icon_h} 无边框'
    print(f'{source_path}  {source.width}x{source.height} {before / 1024:.1f}KB')
    print(f'  -> {output_path}  {canvas.width}x{canvas.height} {after / 1024:.1f}KB'
          f'  ({geom}, pad={args.pad}, 压缩到 {after / before * 100:.0f}%)')


def build_parser():
    parser = argparse.ArgumentParser(
        description='图标处理流水线：补边成正方形 → 缩到显示尺寸 → 存 WebP',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split('用法示例', 1)[1] if '用法示例' in __doc__ else None,
    )
    parser.add_argument('input', help='输入图片路径')
    parser.add_argument('-o', '--output',
                        help='输出路径（默认与输入同目录同名，扩展名换成 .webp）')
    parser.add_argument('--size', type=int, default=140, help='输出画布边长（默认 140）')
    parser.add_argument('--scale', type=float, default=1.0,
                        help='图标占画布的比例，0~1（默认 1.0，即不留边）')
    parser.add_argument('--border-width', type=int, default=None,
                        help='边框厚度（像素），优先于 --scale')
    parser.add_argument('--offset-x', type=float, default=0.0,
                        help='水平偏移，单位为画布边长比例（默认 0）')
    parser.add_argument('--offset-y', type=float, default=0.0,
                        help='垂直偏移，单位为画布边长比例（默认 0）')
    parser.add_argument('--pad', choices=('gradient', 'solid', 'none'), default='solid',
                        help='补边方式（默认 solid，即白底补边）')
    parser.add_argument('--border-color', type=parse_color, default=(255, 255, 255),
                        help="补边颜色，如 #fff（默认 #ffffff，配合 --pad solid）")
    parser.add_argument('--quality', type=int, default=90, help='WebP/JPEG 质量（默认 90）')
    parser.add_argument('--backup-dir', default=None,
                        help='写入前把已存在的输出文件备份到该目录')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not os.path.isfile(args.input):
        parser.error(f'输入文件不存在: {args.input}')
    if not 0 < args.scale <= 1:
        parser.error('--scale 必须在 (0, 1] 之间')
    if args.border_width is not None and args.border_width < 0:
        parser.error('--border-width 不能为负')
    if args.size < 1:
        parser.error('--size 必须 >= 1')

    output = args.output
    if output is None:
        output = os.path.splitext(args.input)[0] + '.webp'

    process(args.input, output, args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
