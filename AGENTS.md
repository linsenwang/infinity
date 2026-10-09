# Infinity - 个人浏览器起始页

## 项目概述

Infinity 是一个个性化的浏览器起始页（New Tab 页面），提供快速搜索和多站点导航功能。项目采用纯前端技术栈（HTML/CSS/JavaScript），无需构建工具，可直接在浏览器中打开运行。

主要功能包括：
- 集成多个搜索引擎的统一搜索框
- 常用网站图标网格，支持一键访问
- 键盘快捷键系统（双字母组合快速跳转）
- 下拉菜单支持（用于聚合相关链接）
- 深色/浅色模式自适应
- 响应式布局，适配不同屏幕尺寸

## 技术栈

- **前端框架**: 原生 HTML5 + CSS3 + ES6+ JavaScript
- **架构**: 经典 `<script>` 标签（非 ES6 模块），配置集中在全局对象 `window.INFINITY_CONFIG`
- **样式**: CSS 变量 + Flexbox/Grid 布局
- **图标处理**: Python + Pillow (PIL) + Jupyter Notebook
- **版本控制**: Git

## 文件结构

```
.
├── index.html                 # 主页面：骨架 + 站点图标 + 下拉菜单配置
├── infinity.css               # 主样式表，包含响应式布局
├── script.js                  # 键盘快捷键 + 搜索框悬停聚焦
├── js/                        # JavaScript 模块目录
│   ├── config.js              # 配置数据（搜索引擎、默认引擎、按钮顺序）
│   └── search.js              # 搜索按钮渲染 + 搜索跳转
├── icon_gen.ipynb             # 图标处理 Jupyter Notebook（交互式调补边参数）
├── icon_pipeline.py           # 图标流水线：补边成正方形 → 缩到 140px → 存 WebP
├── .gitignore                 # Git 忽略规则
├── web_icon/                  # 网页使用的图标（140px 正方形 WebP）
│   ├── yanan.png              # 页面 favicon（保持 PNG）
│   ├── icon-*.webp            # 各站点图标
│   └── ...
└── ori_icon/                  # 原始图标与压缩前备份（被 gitignore 忽略）
    └── ...
```

> 说明：`js/app.js`、`js/keyboard.js`、`js/renderer.js` 目前**并不存在**。键盘逻辑仍在 `script.js`，站点图标与下拉菜单配置仍写在 `index.html` 里——模块化只完成了搜索引擎这一部分。

## 代码组织

### HTML (index.html)
- `head` 里内联了 `.dropdown` 相关样式；`body` 是站点图标网格（`<a><img>` 未闭合的简写）
- 站点图标、下拉菜单数据仍硬编码在 HTML 中
- 底部内联脚本按配置渲染 X 图标的下拉菜单

### JavaScript 模块

#### js/config.js
全局配置对象 `window.INFINITY_CONFIG`，搜索相关的唯一数据源：
- `searchEngines`: 搜索引擎（`name` / `url` 查询前缀 / 可选 `icon`）
- `searchButtons`: 搜索按钮显示顺序（元素为 `searchEngines` 的 key）
- `defaultEngine`: 回车搜索使用的引擎

#### js/search.js
搜索功能（IIFE，无类）：
- `renderSearchButtons()`: 依据 `searchButtons` 动态生成搜索按钮
- `search(engineKey)`: 跳转到 `engine.url + encodeURIComponent(关键词)`
- 监听搜索框回车走 `defaultEngine`，空输入不跳转

#### script.js
- `startKeyDetection()`: 全局键盘监听、双字母快捷键、800ms 超时
- 输入框/可编辑区域内、以及带 ⌘/⌃/⌥ 的按键组合都不参与匹配
- 搜索框悬停时自动聚焦

### CSS (infinity.css)
- **CSS 变量**: `:root` 定义主题色彩
- **深色/浅色模式**: `prefers-color-scheme` 媒体查询
- **响应式断点**: 1500px、1200px、900px、800px、600px、400px
- **下拉菜单**: 支持悬停显示子菜单

## 开发规范

### 添加搜索引擎
只需改 `js/config.js` 一处：在 `searchEngines` 里加条目；想让它出现在搜索框下方，再把 key 加进 `searchButtons`。
```javascript
// js/config.js -> INFINITY_CONFIG.searchEngines
engineName: {
    name: '显示名称',
    url: 'https://example.com/search?q=',   // 查询前缀
    icon: 'web_icon/icon.webp'              // 可选：有 icon 才会渲染成按钮
}
```

### 添加站点图标
站点图标目前仍写在 `index.html` 的 `<div class="body">` 里，照现有写法追加一行：
```html
<a href="https://example.com/"><img width="70" height="70" src="web_icon/icon.webp">
```
`<a>` 不闭合是现有约定；`width`/`height` 属性用于预留布局、避免加载期抖动。

### 添加下拉菜单
在 `index.html` 底部内联脚本的 `dropdowns` 对象里加一项，key 对应图标容器上的 `id`：
```javascript
'x-dropdown': [
    { name: 'dotey', url: 'https://x.com/dotey' }
]
```

### 添加快捷键
在 `script.js` 的 `keyMapping` 对象中添加：
```javascript
'xx': 'https://example.com/',  // xx 为双字母组合
```
注意：「字母组合」的匹配对象是按键序列的**任意后缀**（只保留最近 3 个键，800ms 内有效），所以选组合时要避开日常输入里常见的字母对。

### 图标处理流程
1. 原始图标放入 `ori_icon/`
2. 用 `icon_pipeline.py` 一步完成「补边成正方形 → 缩到 140px（显示尺寸 70px 的 2 倍）→ 存 WebP」；默认就是白底补边，不用带参数
3. 覆盖已有图标前先备份（整份 `web_icon/` 拷到 `ori_icon/web_icon_backup_before_compress_<日期>/`，或用脚本的 `--backup-dir`）
4. 在 `index.html` / `js/config.js` 中引用 `.webp` 路径（favicon `yanan.png` 保持 PNG）

```bash
# 默认：白底补边，透明区域和空隙都填白
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.webp

# 白底 + 四周各留 5% 的边；换补边颜色同理
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.webp --scale 0.9
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.webp --border-color '#1a1a1a'

# 上下边缘渐变补边（icon_gen.ipynb 的算法）
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.webp --pad gradient --scale 0.9 --offset-y -0.035

# 只要透明背景的正方形
python3 icon_pipeline.py ori_icon/x.png -o web_icon/x.png --pad none
```

全部参数见 `python3 icon_pipeline.py --help`：`--size`（默认 140）、`--scale`、`--border-width`、
`--offset-x` / `--offset-y`（单位为画布边长比例）、`--pad solid|gradient|none`（默认 `solid`）、
`--border-color`（默认 `#ffffff`）、`--quality`（默认 90）、`--backup-dir`。

## 构建与部署

### 本地开发
项目为纯静态页面，无需构建步骤：
```bash
# 直接打开
open index.html

# 或使用本地服务器
python -m http.server 8000
npx serve .
```

### 部署
将以下文件部署到任意静态托管服务：
- `index.html`
- `infinity.css`
- `js/` 目录
- `web_icon/` 目录

## 浏览器支持

- 现代浏览器（Chrome、Firefox、Safari、Edge）
- 支持 ES6 模块
- 响应式设计支持移动端和桌面端

## 依赖说明

### 运行时依赖
无外部运行时依赖，所有功能基于原生 Web API。

### 开发依赖
- Python 3.x + Pillow (PIL) - 用于图标处理
- Jupyter - 用于运行图标处理脚本

安装开发依赖：
```bash
pip install pillow jupyter
```

## 快捷键列表

| 快捷键 | 目标网站 |
|--------|----------|
| do | 豆瓣 |
| zl | Z-Library |
| yo | YouTube 订阅 |
| yh | YouTube 历史 |
| bi | Bilibili |
| an | Anna's Archive |
| mp | 微信公众号平台 |
| gi | GitHub |
| zh | 知乎 |
| ch | ChatGPT |
| tw | 阿里云听悟 |
| af | 爱发电 |
| ds | DS100 课程 |
| fr | 本地服务 (47.120.35.57:8080) |
| tx | 本地 txtReader (localhost:3000) |
| ge | Google AI Studio |
| gm | Gmail |
| tr | Google 翻译 |
| cs | CS DIY |
| ... | ... |

## 注意事项

1. **脚本加载**: 全部是经典 `<script defer>`，按 `config.js → search.js → script.js` 顺序执行；因此可以直接用 `file://` 打开，不依赖 HTTP 服务器
2. **图标路径**: 所有图标引用使用相对路径 `web_icon/xxx.webp`（favicon `yanan.png` 除外）
3. **快捷键超时**: 按键序列 800ms 后自动清空；带 ⌘/⌃/⌥ 的按键会被忽略，不计入序列
4. **搜索配置只在一处**: 搜索引擎的 URL / 图标只在 `js/config.js` 维护，不要在 HTML 里另写一份

---

*模块化只完成了搜索引擎这一部分：`js/config.js` 是搜索配置的唯一数据源，站点图标与键盘逻辑仍分别在 `index.html` 和 `script.js` 中。*
