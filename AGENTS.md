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
- **架构**: 模块化 ES6 模块
- **样式**: CSS 变量 + Flexbox/Grid 布局
- **图标处理**: Python + Pillow (PIL) + Jupyter Notebook
- **版本控制**: Git

## 文件结构

```
.
├── index.html                 # 主页面（骨架结构）
├── infinity.css               # 主样式表，包含响应式布局
├── js/                        # JavaScript 模块目录
│   ├── app.js                 # 应用入口，初始化所有模块
│   ├── config.js              # 配置数据（搜索引擎、网站、快捷键）
│   ├── search.js              # 搜索功能管理器
│   ├── keyboard.js            # 键盘快捷键管理器
│   └── renderer.js            # UI 渲染模块
├── icon_gen.ipynb             # 图标处理 Jupyter Notebook
├── .gitignore                 # Git 忽略规则
├── web_icon/                  # 网页使用的图标（正方形，已处理）
│   ├── yanan.png              # 页面 favicon
│   ├── icon-*.png             # 各站点图标
│   └── ...
└── ori_icon/                  # 原始图标（未处理，被 gitignore 忽略）
    └── ...
```

## 代码组织

### HTML (index.html)
- 简化为骨架结构，只包含容器元素
- 通过 ES6 模块引入 JavaScript
- 所有内容由 JS 动态生成

### JavaScript 模块

#### js/config.js
集中管理所有配置数据：
- `searchEngines`: 搜索引擎配置
- `sites`: 网站图标配置
- `keyMapping`: 快捷键映射
- `defaultEngine`: 默认搜索引擎

#### js/search.js
`SearchManager` 类：
- 管理搜索输入框
- 处理搜索按钮点击
- 绑定回车键搜索

#### js/keyboard.js
`KeyboardManager` 类：
- 全局键盘事件监听
- 双字母快捷键检测
- 超时处理（800ms）

#### js/renderer.js
渲染函数集合：
- `renderSearchButtons()`: 渲染搜索按钮
- `renderSiteIcons()`: 渲染网站图标
- 支持下拉菜单的图标渲染

#### js/app.js
主应用类：
- 初始化所有管理器
- 协调各模块工作
- 应用入口点

### CSS (infinity.css)
- **CSS 变量**: `:root` 定义主题色彩
- **深色/浅色模式**: `prefers-color-scheme` 媒体查询
- **响应式断点**: 1500px、1200px、900px、800px、600px、400px
- **下拉菜单**: 支持悬停显示子菜单

## 开发规范

### 添加搜索引擎
在 `js/config.js` 的 `searchEngines` 对象中添加：
```javascript
engineName: {
    name: '显示名称',
    icon: 'web_icon/icon.png',
    url: 'https://example.com/search?q='
}
```

### 添加网站图标
在 `js/config.js` 的 `sites` 数组中添加：
```javascript
{
    name: '网站名称',
    url: 'https://example.com/',
    icon: 'web_icon/icon.png',
    bgColor: 'rgba(255,255,255,1)'  // 可选
}
```

### 添加下拉菜单
在网站配置中添加 `dropdown` 属性：
```javascript
{
    name: 'X (Twitter)',
    url: 'https://x.com/user',
    icon: 'web_icon/x.png',
    bgColor: 'rgba(255,255,255,1)',
    dropdown: [
        { name: 'dotey', url: 'https://x.com/dotey' }
    ]
}
```

### 添加快捷键
在 `js/config.js` 的 `keyMapping` 对象中添加：
```javascript
'xx': 'https://example.com/',  // xx 为双字母组合
```

### 图标处理流程
1. 将原始图标放入 `ori_icon/` 目录
2. 使用 `icon_gen.ipynb` 处理图标
3. 输出到 `web_icon/` 目录
4. 在 `js/config.js` 中引用

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

1. **ES6 模块**: 项目使用 ES6 模块，需要通过 HTTP 服务器访问，不能直接用 `file://` 协议打开
2. **图标路径**: 所有图标引用使用相对路径 `web_icon/xxx.png`
3. **快捷键超时**: 按键序列 800ms 后自动清空

---

*重构后的项目采用模块化架构，数据与视图分离，更易于维护和扩展。*
