// 页面行为：双字母快捷键、搜索框悬停聚焦、图标下拉菜单
(function () {
    'use strict';

    // 快捷键：值为目标地址，key 为两个字母/数字
    const keyMapping = {
        'do': 'https://www.douban.com/',
        'zl': 'https://z-library.sk/',
        'yo': 'https://www.youtube.com/',
        'yh': 'https://www.youtube.com/feed/history',
        'bi': 'https://t.bilibili.com/',
        'an': 'https://annas-archive.org/',
        'mp': 'https://mp.weixin.qq.com/',
        'gi': 'https://github.com/',
        // 'zh': 'https://www.zhihu.com/people/kvxjr369f',
        // 'if': 'https://www.iflyrec.com/html/addMachineOrder.html',
        // 'il': 'https://huiji.iflyrec.com/list',
        'rt': 'file:///Users/yangqian/Library/CloudStorage/OneDrive-Personal/033_webD/infinity_project/txtReader.html',
        'ch': 'https://www.chatgpt.com/',
        'tw': 'https://tingwu.aliyun.com/folders/0',
        'af': 'https://afdian.com/a/q9adg?tab=feed',
        'ds': 'https://ds100.org/sp22/',
        'fr': 'http://47.120.35.57:8080/',
        // 'tx': 'http://47.120.35.57:8081/',
        'tx': 'http://localhost:3000/',
        'ge': 'https://aistudio.google.com/prompts/new_chat',
        'li': 'https://space.bilibili.com/1567748478/lists/32744?type=season',
        'lm': 'https://space.bilibili.com/1567748478',
        'gm': 'https://mail.google.com/mail/u/0/#inbox',
        'wj': 'https://www.youtube.com/results?search_query=%E7%8E%8B%E5%B1%80',
        '12': 'http://127.0.0.1:8096/',
        'cs': 'https://csdiy.wiki/',
        '22': 'https://www.youtube.com/playlist?list=PLoROMvodv4rOaMFbaqxPDoLWjDaRAdP9D',
        'tr': 'https://translate.google.com/',
        'kp': 'https://www.youtube.com/@AndrejKarpathy',
        'ka': 'https://x.com/karminski3',
        'jd': 'https://www.jd.com/',
        'sc': 'https://www.youtube.com/@scottmanley',
        'ys': 'https://www.youtube.com/feed/subscriptions',
        'co': 'https://t.coros.com/',
        // 'it': 'https://www.ithome.com/blog/',
        '47': 'http://47.120.35.57:3000/',
        'ta': 'https://console.tailscale.com/admin/users',
        'iv': 'file:///Users/yangqian/Downloads/image-viewer/image-viewer.html',
    };

    // 下拉菜单：key 为图标容器 id，菜单由 CSS :hover / :focus-within 控制显隐
    const dropdowns = {
        'x-dropdown': [
            { name: 'dotey', url: 'https://x.com/dotey' },
        ],
    };

    const SEQUENCE_TIMEOUT = 800; // 按键序列 800ms 后清空

    function renderDropdowns() {
        for (const id in dropdowns) {
            const container = document.getElementById(id);
            if (!container) continue;

            const menu = container.querySelector('.dropdown-menu');
            if (!menu) continue;

            dropdowns[id].forEach(function (item) {
                const link = document.createElement('a');
                link.href = item.url;
                link.textContent = item.name;
                menu.appendChild(link);
            });
        }
    }

    function startKeyDetection() {
        const pressedKeys = [];
        let timer;

        document.addEventListener('keydown', function (event) {
            const target = event.target;

            // 焦点在输入框 / 可编辑区域时不参与快捷键
            if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
                // 搜索框内再按 / 取消聚焦
                if (target.id === 'searchInput' && event.key === '/' &&
                    !event.metaKey && !event.ctrlKey && !event.altKey && !event.isComposing) {
                    event.preventDefault();
                    target.blur();
                }
                return;
            }

            // ⌘/⌃/⌥ 组合键不参与
            if (event.metaKey || event.ctrlKey || event.altKey) {
                return;
            }

            // “/” 直接聚焦搜索框
            if (event.key === '/') {
                const input = document.getElementById('searchInput');
                if (input) {
                    event.preventDefault();
                    input.focus();
                    input.select();
                }
                return;
            }

            // 忽略 Shift、方向键等非字符键
            const key = event.key.toLowerCase();
            if (key.length !== 1) return;

            clearTimeout(timer);
            timer = setTimeout(function () {
                pressedKeys.length = 0;
            }, SEQUENCE_TIMEOUT);

            pressedKeys.push(key);
            if (pressedKeys.length > 3) {
                pressedKeys.shift();
            }

            // 从前往后匹配：只有序列末尾的组合会触发
            const recentKeys = pressedKeys.join('');
            for (let i = 0; i < recentKeys.length; i++) {
                const combination = recentKeys.slice(i);
                if (keyMapping[combination]) {
                    window.location.href = keyMapping[combination];
                    pressedKeys.length = 0;
                    clearTimeout(timer);
                    return;
                }
            }
        });
    }

    function initSearchFocus() {
        const wrapper = document.getElementById('searchWrapper');
        const input = document.getElementById('searchInput');
        if (!wrapper || !input) return;

        // 鼠标移到搜索区时直接聚焦，方便立刻输入
        wrapper.addEventListener('mouseenter', function () {
            input.focus();
        });

        // 移出后失焦，这样双字母快捷键可以继续工作
        wrapper.addEventListener('mouseleave', function () {
            input.blur();
        });
    }

    // 按当前列数重排固定图标：txtReader 组在行首，彩云在左下，ChatGPT 在右下区域
    function initPinnedSite() {
        const grid = document.querySelector('.sites');
        const pinned = document.getElementById('txt-reader');
        if (!grid || !pinned) return;

        // txtReader 和紧随其后的 X、OpenRouter 作为一组固定在行首
        const cluster = [
            pinned,
            document.getElementById('x-dropdown'),
            document.getElementById('openrouter-site')
        ].filter(Boolean);

        const caiyun = document.getElementById('caiyun-site');
        const chatgpt = document.getElementById('chatgpt-site');

        const baseOrder = Array.from(grid.children);
        const baseIndex = baseOrder.indexOf(pinned);
        if (baseIndex < 0) return;

        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
        let lastCols = 0;
        let lastRects = null;
        let frame = 0;
        let firstRun = true;

        function measure() {
            const rects = new Map();
            Array.from(grid.children).forEach(function (el) {
                rects.set(el, el.getBoundingClientRect());
            });
            return rects;
        }

        // 列数变化时，所有图标从上一轮的坐标滑到新坐标（FLIP）
        function animateFrom(fromRects, toRects) {
            if (!fromRects || reduceMotion.matches) return;

            toRects.forEach(function (last, el) {
                const first = fromRects.get(el);
                if (!first) return;

                const dx = first.left - last.left;
                const dy = first.top - last.top;
                if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;

                el.animate(
                    [
                        { transform: 'translate(' + dx + 'px, ' + dy + 'px)' },
                        { transform: 'translate(0, 0)' }
                    ],
                    { duration: 320, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)' }
                );
            });
        }

        function arrange() {
            frame = 0;

            const template = getComputedStyle(grid).gridTemplateColumns;
            const cols = template === 'none'
                ? 1
                : template.split(/\s+/).filter(Boolean).length;

            if (cols === lastCols) {
                lastRects = measure();
                return;
            }
            lastCols = cols;

            // 所在行的下一行第一列（8 列时即第三行）
            const rowStart = (Math.floor(baseIndex / cols) + 1) * cols;

            const total = baseOrder.length;
            const lastRowStart = (Math.ceil(total / cols) - 1) * cols;
            const lastRowCount = total - lastRowStart;

            // 末行放不下 ChatGPT 时，退到上一完整行的同一列
            const chatStart = lastRowCount >= 5 ? lastRowStart : lastRowStart - cols;
            const chatIndex = chatStart + Math.min(4, cols - 1);

            const fixed = new Set(cluster);
            if (caiyun) fixed.add(caiyun);
            if (chatgpt) fixed.add(chatgpt);

            const slots = new Array(total).fill(null);

            function place(el, index) {
                if (!el) return;

                let i = Math.max(0, Math.min(index, total - 1));
                while (i < total && slots[i]) i++;
                if (i >= total) {
                    i = Math.max(0, Math.min(index, total - 1));
                    while (i >= 0 && slots[i]) i--;
                }
                if (i >= 0) slots[i] = el;
            }

            place(pinned, rowStart);
            place(cluster[1], rowStart + 1);
            place(cluster[2], rowStart + 2);
            place(caiyun, lastRowStart);
            place(chatgpt, chatIndex);

            let next = 0;
            for (let i = 0; i < total; i++) {
                if (slots[i]) continue;
                while (next < total && fixed.has(baseOrder[next])) next++;
                if (next < total) slots[i] = baseOrder[next++];
            }

            slots.forEach(function (el) {
                grid.appendChild(el);
            });

            const rects = measure();
            if (!firstRun) animateFrom(lastRects, rects);
            firstRun = false;
            lastRects = rects;
        }

        function schedule() {
            if (frame) return;
            frame = requestAnimationFrame(arrange);
        }

        arrange();
        window.addEventListener('load', schedule);
        window.addEventListener('resize', schedule, { passive: true });
    }

    function init() {
        renderDropdowns();
        startKeyDetection();
        initSearchFocus();
        initPinnedSite();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
