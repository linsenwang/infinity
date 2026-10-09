// 搜索功能：URL 与按钮都来自 js/config.js，避免多处维护同一份引擎表
(function () {
    const config = window.INFINITY_CONFIG;

    // 按关键词跳转到指定引擎（engineKey 为 config.searchEngines 的 key）
    function search(engineKey) {
        const engine = config.searchEngines[engineKey];
        const input = document.getElementById('searchInput');
        if (!engine || !input) return;

        const keyword = input.value.trim();
        if (keyword === '') return;

        window.location.href = engine.url + encodeURIComponent(keyword);
    }

    // 按 config.searchButtons 的顺序渲染搜索按钮
    function renderSearchButtons() {
        const container = document.getElementById('buttonContainer');
        if (!container) return;

        config.searchButtons.forEach(function (engineKey) {
            const engine = config.searchEngines[engineKey];
            if (!engine || !engine.icon) return;

            const button = document.createElement('button');
            button.className = 'search-button';
            button.title = engine.name;
            button.addEventListener('click', function () {
                search(engineKey);
            });

            const img = document.createElement('img');
            img.src = engine.icon;
            img.alt = engine.name;
            img.width = 32;
            img.height = 32;

            button.appendChild(img);
            container.appendChild(button);
        });
    }

    function init() {
        renderSearchButtons();

        const input = document.getElementById('searchInput');
        if (!input) return;

        input.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' && !event.isComposing) {
                event.preventDefault();
                search(config.defaultEngine);
            }
        });
    }

    document.addEventListener('DOMContentLoaded', init);
})();
