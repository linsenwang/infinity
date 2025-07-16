// 全局函数，在页面加载时调用
function startKeyDetection() {
    // 将变量定义在函数作用域内
    const pressedKeys = [];
    const keyMapping = {
        'do': 'https://www.douban.com/',
        'zl': 'https://z-library.sk/',
        'yo': 'https://www.youtube.com/',
        'yh': 'https://www.youtube.com/feed/history',
        'bi': 'https://t.bilibili.com/',
        'an': 'https://annas-archive.org/',
        'mp': 'https://mp.weixin.qq.com/',
        'gi': 'https://github.com/',
        'zh': 'https://www.zhihu.com/people/kvxjr369f',
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
        'gm': 'https://mail.google.com/mail/u/0/#inbox',
        'wj': 'https://www.youtube.com/results?search_query=%E7%8E%8B%E5%B1%80',
        '12': 'http://127.0.0.1:8096/',
        'cs': 'https://csdiy.wiki/',
        '22': 'https://www.youtube.com/playlist?list=PLoROMvodv4rOaMFbaqxPDoLWjDaRAdP9D',
        'tr': 'https://translate.google.com/',
        'kp': 'https://www.youtube.com/@AndrejKarpathy',
        'ka': 'https://x.com/karminski3',
        'jd': 'https://www.jd.com/',
    };
    let timeout; // 用于存储定时器的引用

    const keyHandler = function(event) {
        const target = event.target;

        // 1. 如果当前焦点在输入框或文本区域，则跳过所有处理
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
            return;
        }

        // --- 如果代码执行到这里，说明是有效的快捷键输入 ---

        // 2. 重置超时定时器
        // 只有在有效的按键上才重置定时器
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            pressedKeys.length = 0; // 清空数组
            console.log('超时，清空按键序列');
        }, 800); // 超时时间可以根据喜好调整，例如 800ms

        const key = event.key.toLowerCase();

        // 防止连续输入同一个键，例如 'gg'。如果需要支持'gg'这样的组合，请注释掉此行
        // if (pressedKeys.length > 0 && pressedKeys[pressedKeys.length - 1] === key) return;

        // 3. 添加按键到数组并处理
        pressedKeys.push(key);
        console.log(`按下的键序列: ${pressedKeys.join('')}`);

        // 限制数组长度，例如最多记录最近的3个键
        if (pressedKeys.length > 3) {
            pressedKeys.shift();
        }

        // 4. 检查组合键是否匹配
        const recentKeys = pressedKeys.join('');
        // 从后往前检查，优先匹配更长的快捷键，例如 'go' 和 'goo'
        for (let i = 0; i < recentKeys.length; i++) {
            const combination = recentKeys.slice(i); // 例如 "ghc" -> "ghc", "hc", "c"
            if (keyMapping[combination]) {
                console.log(`匹配成功: ${combination} -> ${keyMapping[combination]}`);
                window.location.href = keyMapping[combination];
                pressedKeys.length = 0; // 导航后清空数组
                clearTimeout(timeout);  // 清除定时器，因为已经执行了操作
                return;
            }
        }
    };

    // 只需要一个事件监听器
    document.addEventListener('keydown', keyHandler);
}

// 页面加载完成后开始检测
window.onload = startKeyDetection;

const wrapper = document.getElementById('searchWrapper');
const input = document.getElementById('searchInput');

wrapper.addEventListener('mouseenter', () => {
  // 等待动画出现后聚焦
  setTimeout(() => {
    input.focus();
  }, 100);
});

wrapper.addEventListener('mouseleave', () => {
  // 鼠标移出时取消焦点
  input.blur();
});