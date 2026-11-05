#!/usr/bin/env python3
r"""手动标定每个图标的视觉大小。

起一个本地页面，按 index.html + js/config.js 里的引用列出全部图标，每个
图标右边有 -/+ 按钮，按 1% 步进调整主体视觉直径（Shift 点击为 0.2%）。
调好后点“复制参数”，得到每行的 name / 类型 / 手动值 / 自动值，直接发给
拟合脚本当作目标值用。

图标用和页面相同的圆形裁切与深色反色滤镜显示；手动值不做键线收敛，
按钮上的数字就是实际渲染出来的视觉直径，避免“点了没反应”。

用法示例
--------
python3 tools/lab.py                  # 默认 --fill 0.794，自动打开浏览器
python3 tools/lab.py --fill 0.55      # 从 0.55 的自动值开始
python3 tools/lab.py --no-browser     # 只打印地址

参数说明
--------
--fill       裸标志自动值的基准（默认 0.794），底板标志用 PLATE_TARGET
--size       生成画布边长（默认 140）
--index      页面文件（默认 index.html）
--port       端口（默认 0，自动挑一个空闲端口）
--no-browser 不自动打开浏览器
"""

import argparse
import io
import json
import os
import re
import sys
import tempfile
import threading
import webbrowser
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optical_fit as of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(tempfile.gettempdir(), 'optical-lab')
LOCK = threading.Lock()
ICONS = []
BY_STEM = {}
FILL = 0.794
SIZE = 140


def site_labels(index_path):
    """从 index.html 和 js/config.js 里取图标对应的站点名。"""
    root = os.path.dirname(os.path.abspath(index_path))
    labels = {}
    with open(index_path, encoding='utf-8') as file:
        html = file.read()
    pattern = r'<a[^>]*aria-label="([^"]+)"[^>]*>\s*<img[^>]*src="web_icon/([^"]+)"'
    for label, name in re.findall(pattern, html):
        labels.setdefault(os.path.basename(name), label)
    config = os.path.join(root, 'js', 'config.js')
    if os.path.isfile(config):
        with open(config, encoding='utf-8') as file:
            script = file.read()
        pair = r"name:\s*'([^']+)'[\s\S]{0,200}?icon:\s*'web_icon/([^']+)'"
        for label, name in re.findall(pair, script):
            labels.setdefault(os.path.basename(name), label)
    return labels


def auto_icon(source, stem):
    """按默认参数生成一次，返回自动视觉直径（和工具正常输出一致）。"""
    path = os.path.join(CACHE, f'{stem}__auto.webp')
    with redirect_stdout(io.StringIO()):
        result = of.fit(source, path, FILL, SIZE, 90)
    return path, (result.get('visual') or 0.0)


def prepare(index_path):
    os.makedirs(CACHE, exist_ok=True)
    sources = of.pick_sources(os.path.join(ROOT, 'ori_icon'))
    labels = site_labels(index_path)
    names = of.index_targets(index_path)
    icons = []
    for index, name in enumerate(names, 1):
        stem = os.path.splitext(name)[0].lower()
        source = sources.get(stem) or os.path.join(ROOT, 'web_icon', name)
        image = of.load_image(source)
        plate = of.is_plate_source(np.asarray(image).astype(np.float32))
        _, auto = auto_icon(source, stem)
        icons.append({
            'name': name,
            'stem': stem,
            'label': labels.get(name, os.path.splitext(name)[0]),
            'kind': 'plate' if plate else 'logo',
            'auto': round(auto, 3),
            'source': source,
        })
        print(f'  准备图标 {index}/{len(names)}', end='\r', flush=True)
    print(' ' * 40, end='\r')
    return icons


def render(icon, value):
    """按指定视觉直径渲染；value 与自动值一致时直接用自动图，保证初始观感相同。"""
    if abs(value - icon['auto']) < 0.0005:
        return os.path.join(CACHE, f"{icon['stem']}__auto.webp")
    path = os.path.join(CACHE, f"{icon['stem']}__{value:.3f}.webp")
    with LOCK:
        if not os.path.exists(path):
            with redirect_stdout(io.StringIO()):
                of.fit(icon['source'], path, FILL, SIZE, 90,
                       target=value, limits=False)
    return path


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>图标标定</title>
<style>
  * { box-sizing: border-box; }
  :root {
    color-scheme: light dark;
    --bg: #ffffff; --fg: #1d1d1f; --muted: #86868b;
    --line: rgba(0, 0, 0, 0.12); --btn: rgba(0, 0, 0, 0.04);
    --btn-hover: rgba(0, 0, 0, 0.09); --accent: #007aff;
    --tile-bg: #ffffff; --tile-ring: rgba(0, 0, 0, 0.08);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #1b1b1d; --fg: #e6e6e8; --muted: #8e8e93;
      --line: rgba(255, 255, 255, 0.14); --btn: rgba(255, 255, 255, 0.06);
      --btn-hover: rgba(255, 255, 255, 0.13); --accent: #4c9aff;
      --tile-ring: rgba(0, 0, 0, 0.25);
    }
  }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font: 13px/1.4 -apple-system, BlinkMacSystemFont, "PingFang SC", system-ui, sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap;
    gap: 10px; align-items: center; padding: 10px 18px;
    background: var(--bg); border-bottom: 1px solid var(--line);
  }
  header h1 { margin: 0 4px 0 0; font-size: 14px; font-weight: 600; }
  header .hint { color: var(--muted); }
  header .spacer { flex: 1; }
  button {
    font: inherit; color: inherit; background: var(--btn); border: 1px solid var(--line);
    border-radius: 8px; padding: 5px 10px; cursor: pointer;
  }
  button:hover { background: var(--btn-hover); }
  button:active { transform: translateY(1px); }
  button.primary { background: var(--accent); border-color: transparent; color: #fff; }
  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(192px, 1fr));
    gap: 4px; padding: 14px 18px 40px; max-width: 1360px; margin: 0 auto;
  }
  .cell {
    display: grid; grid-template-columns: 74px 34px; grid-template-rows: 74px auto;
    gap: 7px 10px; padding: 10px; border-radius: 14px;
  }
  .cell:hover { background: var(--btn); }
  .art {
    width: 74px; height: 74px; display: block; border-radius: 50%;
    background: var(--tile-bg); outline: 1px solid var(--tile-ring);
    outline-offset: -1px; -webkit-user-drag: none;
  }
  @media (prefers-color-scheme: dark) { .art { filter: invert(88%) hue-rotate(180deg); } }
  .side { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; }
  .side .step { width: 30px; padding: 1px 0; line-height: 16px; text-align: center; }
  .val { font-variant-numeric: tabular-nums; font-size: 11px; color: var(--muted); }
  .meta { grid-column: 1 / -1; min-width: 0; }
  .meta b {
    display: block; font-weight: 500; font-size: 12px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .meta span { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .toast {
    position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%);
    background: var(--fg); color: var(--bg); padding: 8px 14px; border-radius: 999px;
    font-size: 12px; opacity: 0; transition: opacity 0.2s; pointer-events: none;
  }
  .toast.show { opacity: 1; }
  dialog { border: 1px solid var(--line); border-radius: 12px; background: var(--bg);
    color: var(--fg); width: min(720px, 92vw); }
  dialog textarea { width: 100%; height: 320px; font: 12px/1.5 ui-monospace, monospace;
    background: var(--btn); color: inherit; border: 1px solid var(--line);
    border-radius: 8px; padding: 8px; resize: vertical; }
</style>
</head>
<body>
<header>
  <h1>图标标定</h1>
  <span class="hint" id="hint"></span>
  <span class="spacer"></span>
  <button id="copy" class="primary">复制参数</button>
  <button id="reset">全部还原</button>
</header>
<div class="grid" id="grid"></div>
<div class="toast" id="toast"></div>
<dialog id="fallback">
  <p>自动复制被浏览器拦住了，选中下面文本复制：</p>
  <textarea id="fallbackText" readonly></textarea>
</dialog>
<script>
const DATA = __DATA__;
const ICONS = DATA.icons;
const AUTO = new Map(ICONS.map(i => [i.name, i.auto]));
const BY_NAME = new Map(ICONS.map(i => [i.name, i]));
const KEY = 'optical-lab:' + DATA.fill;
const state = new Map(ICONS.map(i => [i.name, i.auto]));
const nodes = new Map();

try {
  const saved = JSON.parse(localStorage.getItem(KEY) || '{}');
  for (const [name, value] of Object.entries(saved)) {
    if (BY_NAME.has(name) && Number.isFinite(value)) state.set(name, value);
  }
} catch (e) { /* 忽略损坏的本地记录 */ }

document.getElementById('hint').textContent =
  `裸标志 fill ${DATA.fill.toFixed(2)} · 底板 ${DATA.plate.toFixed(2)} · ` +
  `点 +/− 按 1% 调，Shift 点击 0.2%`;

const grid = document.getElementById('grid');
const toast = document.getElementById('toast');

function iconUrl(icon, value) {
  return `/icon?name=${encodeURIComponent(icon.stem)}&v=${value.toFixed(3)}`;
}

function save() {
  const diff = {};
  for (const [name, value] of state) {
    if (Math.abs(value - AUTO.get(name)) > 1e-9) diff[name] = Number(value.toFixed(3));
  }
  localStorage.setItem(KEY, JSON.stringify(diff));
}

function paint(icon, value) {
  value = Math.round(value * 1000) / 1000;
  state.set(icon.name, value);
  const node = nodes.get(icon.name);
  node.img.src = iconUrl(icon, value);
  node.val.textContent = (value * 100).toFixed(1) + '%';
  const delta = value - AUTO.get(icon.name);
  node.note.textContent = delta
    ? `自动 ${(AUTO.get(icon.name) * 100).toFixed(1)}%  ${delta > 0 ? '+' : ''}${(delta * 100).toFixed(1)}`
    : '自动';
  save();
}

for (const icon of ICONS) {
  const cell = document.createElement('div');
  cell.className = 'cell';

  const img = document.createElement('img');
  img.className = 'art';
  img.alt = icon.label;
  img.decoding = 'async';

  const side = document.createElement('div');
  side.className = 'side';
  const up = document.createElement('button');
  up.className = 'step';
  up.textContent = '+';
  up.title = '放大 1%（Shift 为 0.2%）';
  const val = document.createElement('div');
  val.className = 'val';
  const down = document.createElement('button');
  down.className = 'step';
  down.textContent = '−';
  down.title = '缩小 1%（Shift 为 0.2%）';
  side.append(up, val, down);

  const meta = document.createElement('div');
  meta.className = 'meta';
  const name = document.createElement('b');
  name.textContent = icon.label;
  const note = document.createElement('span');
  meta.append(name, note);

  cell.append(img, side, meta);
  grid.append(cell);
  nodes.set(icon.name, { img, val, note });

  const nudge = (step) => {
    const next = Math.min(0.95, Math.max(0.20, state.get(icon.name) + step));
    paint(icon, next);
  };
  up.addEventListener('click', (event) => nudge(event.shiftKey ? 0.002 : 0.01));
  down.addEventListener('click', (event) => nudge(event.shiftKey ? -0.002 : -0.01));
  paint(icon, state.get(icon.name));
}

document.getElementById('reset').addEventListener('click', () => {
  for (const icon of ICONS) paint(icon, AUTO.get(icon.name));
  showToast('已还原到自动值');
});

function exportText() {
  const lines = [
    `# 图标标定  fill=${DATA.fill.toFixed(2)}  size=${DATA.size}`,
    '# name\tkind\tmanual\tauto',
  ];
  for (const icon of ICONS) {
    lines.push([
      icon.name,
      icon.kind,
      state.get(icon.name).toFixed(3),
      icon.auto.toFixed(3),
    ].join('\t'));
  }
  return lines.join('\n');
}

document.getElementById('copy').addEventListener('click', async () => {
  const text = exportText();
  try {
    await navigator.clipboard.writeText(text);
    showToast(`已复制 ${ICONS.length} 个图标，直接粘给模型`);
  } catch (e) {
    const dialog = document.getElementById('fallback');
    document.getElementById('fallbackText').value = text;
    dialog.showModal();
    document.getElementById('fallbackText').select();
  }
});

let toastTimer = 0;
function showToast(text) {
  toast.textContent = text;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 1800);
}
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/':
            return self.page()
        if parsed.path == '/icon':
            return self.icon(parse_qs(parsed.query))
        self.send_error(404)

    def page(self):
        data = {
            'fill': FILL,
            'plate': of.PLATE_TARGET,
            'size': SIZE,
            'icons': [{k: v for k, v in icon.items() if k != 'source'} for icon in ICONS],
        }
        html = PAGE.replace('__DATA__', json.dumps(data, ensure_ascii=False))
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def icon(self, query):
        stem = query.get('name', [''])[0]
        icon = BY_STEM.get(stem)
        if icon is None:
            return self.send_error(404)
        try:
            value = float(query.get('v', ['0'])[0])
        except ValueError:
            return self.send_error(400)
        path = render(icon, min(0.95, max(0.20, value)))
        with open(path, 'rb') as file:
            body = file.read()
        self.send_response(200)
        self.send_header('Content-Type', 'image/webp')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def main(argv=None):
    global ICONS, BY_STEM, FILL, SIZE
    parser = argparse.ArgumentParser(
        description='手动标定每个图标的视觉大小',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(__doc__.split('用法示例', 1)[1].lstrip('\n-')
                if '用法示例' in __doc__ else None),
    )
    parser.add_argument('--fill', type=float, default=0.794,
                        help='裸标志自动值的基准（默认 0.794）')
    parser.add_argument('--size', type=int, default=140, help='生成画布边长（默认 140）')
    parser.add_argument('--index', default=os.path.join(ROOT, 'index.html'),
                        help='页面文件（默认 index.html）')
    parser.add_argument('--port', type=int, default=0,
                        help='端口（默认 0，自动挑一个空闲端口）')
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    args = parser.parse_args(argv)

    FILL = args.fill
    SIZE = args.size
    print('准备图标…')
    ICONS = prepare(os.path.abspath(args.index))
    BY_STEM = {icon['stem']: icon for icon in ICONS}
    print(f'共 {len(ICONS)} 个图标，缓存目录 {CACHE}')

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    port = server.server_address[1]
    url = f'http://127.0.0.1:{port}/'
    print(f'打开 {url}  （Ctrl+C 结束）')
    if not args.no_browser:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
