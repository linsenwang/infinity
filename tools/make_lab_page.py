#!/usr/bin/env python3
r"""从 index.html 生成图标标定页 index-lab.html。

标定页只是正式页的一份副本，多了 css/lab.css 和 js/lab.js。正式页增删图标
后重跑一次这个脚本即可，不用手工维护两份 HTML：

  python3 tools/make_lab_page.py

生成后打开 index-lab.html，调完复制参数；正式页 index.html 不受影响。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, 'index.html')
LAB = os.path.join(ROOT, 'index-lab.html')

INJECT = """    <!-- 图标标定页：与 index.html 相同的网格，额外加载 lab.css / lab.js -->
    <link rel="stylesheet" href="css/lab.css">
    <script src="js/lab-data.js" defer></script>
    <script src="js/lab.js" defer></script>
"""


def main():
    if not os.path.isfile(INDEX):
        raise SystemExit(f'找不到 {INDEX}')
    html = open(INDEX, encoding='utf-8').read()
    if 'css/lab.css' in html or 'js/lab.js' in html:
        raise SystemExit('index.html 里已经有标定代码了，先把它们去掉再生成')
    if '</head>' not in html:
        raise SystemExit('index.html 里找不到 </head>')

    html = html.replace('<title>New Tab</title>', '<title>图标标定</title>', 1)
    html = html.replace('</head>', INJECT + '</head>', 1)
    open(LAB, 'w', encoding='utf-8').write(html)

    missing = [path for path in ('css/lab.css', 'js/lab.js', 'js/lab-data.js')
               if not os.path.isfile(os.path.join(ROOT, path))]
    if missing:
        print('缺少文件：' + ', '.join(missing))
        print('先跑 python3 tools/gen_lab.py 生成 js/lab-data.js')
    print(f'已生成 {LAB}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
