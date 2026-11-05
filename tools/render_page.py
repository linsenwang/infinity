#!/usr/bin/env python3
r"""用无头 Chrome 把 index.html 按真实样式渲染成 PNG。

图标最终是放在页面里看的，单独看对照图容易误判：圆形裁切、底板边框、
深色模式的反转滤镜都会改变观感。这个工具直接截取 index.html：
CSS、脚本、字体、网格与圆形图标全部按浏览器实际布局渲染。

用法示例
--------
# 渲染当前页面（2x，浅色）
python3 tools/render_page.py -o page.png --theme light

# 渲染暗色模式
python3 tools/render_page.py -o page-dark.png --theme dark

# 用另一批图标渲染，不覆盖 web_icon：先输出到临时目录再截图
# 换个 --fill 再跑一遍，可以直接比对不同占比下的均匀度
python3 tools/optical_fit.py ori_icon -o /tmp/icons_070 --from-index index.html --fill 0.70
python3 tools/render_page.py --icons /tmp/icons_070 -o page-070.png --theme light

参数说明
--------
-o/--output  输出 PNG（默认 page.png）
--index      页面文件（默认 index.html）
--icons      图标目录：把页面里的 web_icon/* 换到这个目录，默认不改
--theme      light / dark / auto（默认 auto，跟随系统）
--width      视口宽度（默认 1400，页面此时是 8 列）
--height     视口高度（默认 1000）
--scale      设备像素比（默认 2，输出为视口的 2 倍）
--wait       截图前等待的虚拟时间，毫秒（默认 2000，覆盖入场动画）
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

CHROME_CANDIDATES = (
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
)


def find_chrome():
    override = os.environ.get('CHROME')
    if override and os.path.isfile(override):
        return override
    for path in CHROME_CANDIDATES:
        if os.path.isfile(path):
            return path
    for name in ('google-chrome', 'chromium', 'chrome'):
        path = shutil.which(name)
        if path:
            return path
    raise SystemExit('找不到 Chrome；可用环境变量 CHROME 指定可执行文件路径')


def substitute_icons(html, icon_dir):
    """把页面里 web_icon/xxx 的引用换成 icon_dir 下的同名文件。"""
    root = os.path.abspath(icon_dir)
    pattern = re.compile(r'(["\'])web_icon/([^"\']+)\.(webp|png|jpe?g)\1', re.I)

    def replace(match):
        name = f'{match.group(2)}.{match.group(3)}'
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            return match.group(0)
        return f'{match.group(1)}{path}{match.group(1)}'

    return pattern.sub(replace, html)


def build_page(index_path, icon_dir):
    """返回要截图的 HTML 路径；替换过图标时写一份临时页面。"""
    index_path = os.path.abspath(index_path)
    if not icon_dir:
        return index_path
    with open(index_path, encoding='utf-8') as file:
        html = file.read()
    html = substitute_icons(html, icon_dir)
    temp = os.path.join(os.path.dirname(index_path),
                        f'.render-{os.getpid()}.html')
    with open(temp, 'w', encoding='utf-8') as file:
        file.write(html)
    return temp


def render(index_path, output_path, theme, width, height, scale, wait):
    chrome = find_chrome()
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='render-page-') as profile:
        command = [
            chrome,
            '--headless=new',
            '--disable-gpu',
            '--hide-scrollbars',
            '--no-first-run',
            '--no-default-browser-check',
            f'--user-data-dir={profile}',
            f'--window-size={width},{height}',
            f'--force-device-scale-factor={scale}',
            f'--virtual-time-budget={wait}',
            f'--screenshot={output_path}',
        ]
        if theme == 'light':
            command.append('--blink-settings=preferredColorScheme=1')
        elif theme == 'dark':
            command.append('--force-dark-mode')
        command.append(open_url(index_path))
        result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.isfile(output_path):
        sys.stderr.write(result.stderr or 'Chrome 渲染失败\n')
        raise SystemExit(result.returncode or 1)
    return output_path


def open_url(path):
    from pathlib import Path
    return Path(path).resolve().as_uri()


def build_parser():
    parser = argparse.ArgumentParser(
        description='把 index.html 按真实样式渲染成 PNG',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(__doc__.split('参数说明', 1)[1].lstrip('\n-')
                if '参数说明' in __doc__ else None),
    )
    parser.add_argument('-o', '--output', default='page.png', help='输出 PNG（默认 page.png）')
    parser.add_argument('--index', default='index.html', help='页面文件（默认 index.html）')
    parser.add_argument('--icons', help='图标目录，替换页面里的 web_icon/ 引用')
    parser.add_argument('--theme', choices=('light', 'dark', 'auto'), default='auto',
                        help='配色（默认 auto，跟随系统）')
    parser.add_argument('--width', type=int, default=1400, help='视口宽度（默认 1400）')
    parser.add_argument('--height', type=int, default=1000, help='视口高度（默认 1000）')
    parser.add_argument('--scale', type=int, default=2, help='设备像素比（默认 2）')
    parser.add_argument('--wait', type=int, default=2000,
                        help='截图前等待的虚拟时间，毫秒（默认 2000）')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not os.path.isfile(args.index):
        raise SystemExit(f'找不到页面: {args.index}')
    if args.icons and not os.path.isdir(args.icons):
        raise SystemExit(f'找不到图标目录: {args.icons}')
    if args.width < 1 or args.height < 1 or args.scale < 1 or args.wait < 0:
        raise SystemExit('--width/--height/--scale 必须为正，--wait 不能为负')

    page = build_page(args.index, args.icons)
    try:
        path = render(page, args.output, args.theme, args.width, args.height,
                      args.scale, args.wait)
    finally:
        if page != os.path.abspath(args.index):
            os.remove(page)
    print(f'{path}  {args.width * args.scale}x{args.height * args.scale}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
