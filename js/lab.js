/* 图标标定页（index-lab.html）
   每个站点图标右侧一列 +/−，按 1% 切换 web_icon/lab 下预渲染的视觉直径；
   左下角整体调 fill / plate，点中间的百分比回到自动值；
   右下角“重置大小”清掉本地微调，“复制缩放参数”导出 TSV 贴回给拟合脚本。
   清单由 tools/gen_lab.py 生成（js/lab-data.js），改了 optical_fit 后重跑即可。 */
(function () {
    'use strict';

    var DATA = window.INFINITY_LAB;
    if (!DATA || !DATA.icons) return;

    var ICONS = DATA.icons;
    var MIN = DATA.min;
    var MAX = DATA.max;
    var SIZE = DATA.size;

    // v7：三档尺寸（68% / 43% / 79%）联合拟合
    var KEY = 'infinity-lab-v7';
    var byName = {};
    ICONS.forEach(function (icon) { byName[icon.name] = icon; });

    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (error) { saved = {}; }

    var mounted = [];
    var toast = null;

    function store() {
        var diff = {};
        mounted.forEach(function (item) {
            if (item.value !== item.auto) diff[item.icon.name] = item.value;
        });
        try { localStorage.setItem(KEY, JSON.stringify(diff)); } catch (error) { /* 忽略 */ }
    }

    function scaleOf(item, value) {
        return value / 100 * SIZE / item.icon.optical;
    }

    function paint(item, value) {
        value = Math.max(MIN, Math.min(MAX, Math.round(value)));
        item.value = value;
        item.img.src = value === item.auto
            ? 'web_icon/' + item.icon.name
            : 'web_icon/lab/' + item.icon.stem + '/' + value + '.webp';
        item.label.textContent = value + '%';
        item.label.title = '自动 ' + item.auto + '%，点按还原';
        store();
    }

    function flash(text) {
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'lab-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = text;
        toast.classList.add('show');
        clearTimeout(flash.timer);
        flash.timer = setTimeout(function () { toast.classList.remove('show'); }, 1600);
    }

    function block(event) {
        event.preventDefault();
        event.stopPropagation();
    }

    Array.prototype.forEach.call(document.querySelectorAll('.sites > .site'), function (site) {
        var img = site.querySelector('img');
        if (!img) return;
        var name = (img.getAttribute('src') || '').split('/').pop();
        var icon = byName[name];
        if (!icon) return;

        var auto = Math.round(icon.auto * 100);
        var start = saved[name];
        if (typeof start !== 'number' || !isFinite(start)) start = auto;

        var ctl = document.createElement('div');
        ctl.className = 'lab-ctl';
        var up = document.createElement('button');
        up.type = 'button';
        up.textContent = '+';
        up.title = '放大 1%';
        var label = document.createElement('span');
        label.title = '自动 ' + auto + '%，点按还原';
        var down = document.createElement('button');
        down.type = 'button';
        down.textContent = '−';
        down.title = '缩小 1%';
        ctl.appendChild(up);
        ctl.appendChild(label);
        ctl.appendChild(down);
        site.appendChild(ctl);

        ['click', 'mousedown', 'pointerdown', 'dragstart'].forEach(function (type) {
            ctl.addEventListener(type, block);
        });

        var item = {
            icon: icon,
            img: img,
            label: label,
            site: site.getAttribute('aria-label') || '',
            auto: auto,
            value: auto
        };
        up.addEventListener('click', function () { paint(item, item.value + 1); });
        down.addEventListener('click', function () { paint(item, item.value - 1); });
        label.addEventListener('click', function () {
            paint(item, item.auto);
            flash('已还原为自动 ' + item.auto + '%');
        });

        mounted.push(item);
        paint(item, start);
    });

    var bar = document.createElement('div');
    bar.className = 'lab-bar';
    bar.innerHTML = '<span class="lab-note">图标标定：点 +/− 调视觉大小</span>' +
        '<button type="button" id="labCopy">复制缩放参数</button>' +
        '<button type="button" id="labReset">重置大小</button>';
    document.body.appendChild(bar);

    // 整体 fill / plate：一次把同类图标都调到同一个视觉直径，再逐个手调
    var group = {
        logo: Math.round(DATA.fill * 100),
        plate: Math.round(DATA.plate * 100)
    };
    var panel = document.createElement('div');
    panel.className = 'lab-fill';
    panel.innerHTML =
        '<div class="lab-fill-row" data-group="logo">' +
            '<span class="lab-fill-name">fill</span>' +
            '<button type="button" data-step="-1" title="所有 logo 一起缩小 1%">−</button>' +
            '<span class="lab-fill-val">68%</span>' +
            '<button type="button" data-step="1" title="所有 logo 一起放大 1%">+</button>' +
        '</div>' +
        '<div class="lab-fill-row" data-group="plate">' +
            '<span class="lab-fill-name">plate</span>' +
            '<button type="button" data-step="-1" title="所有底板标志一起缩小 1%">−</button>' +
            '<span class="lab-fill-val">65%</span>' +
            '<button type="button" data-step="1" title="所有底板标志一起放大 1%">+</button>' +
        '</div>' +
        '<div class="lab-fill-hint">先整体调，再逐个 +/− 手调</div>';
    document.body.appendChild(panel);

    function paintGroup() {
        Array.prototype.forEach.call(panel.querySelectorAll('.lab-fill-row'), function (row) {
            row.querySelector('.lab-fill-val').textContent =
                group[row.getAttribute('data-group')] + '%';
        });
    }

    function applyGroup(kind, value) {
        value = Math.max(MIN, Math.min(MAX, value));
        group[kind] = value;
        mounted.forEach(function (item) {
            if (Boolean(item.icon.plate) === (kind === 'plate')) paint(item, value);
        });
        paintGroup();
        flash('已把 ' + (kind === 'plate' ? '底板' : 'logo') + ' 全部调到 ' + value + '%');
    }

    Array.prototype.forEach.call(panel.querySelectorAll('.lab-fill-row'), function (row) {
        var kind = row.getAttribute('data-group');
        Array.prototype.forEach.call(row.querySelectorAll('button'), function (button) {
            button.addEventListener('click', function () {
                applyGroup(kind, group[kind] + Number(button.getAttribute('data-step')));
            });
        });
    });
    paintGroup();

    function exportText() {
        var lines = [
            '# infinity icon calibration  fill=' + DATA.fill.toFixed(3) +
                '  plate=' + DATA.plate.toFixed(3) +
                '  reach=' + DATA.reach.toFixed(3) +
                '  plate_reach=' + DATA.plate_reach.toFixed(3) +
                '  thin=' + DATA.thin.toFixed(3) +
                '  thin_scale=' + DATA.thin_scale.toFixed(3) +
                '  thin_ref=' + DATA.thin_ref.toFixed(3) +
                '  plate_thin=' + DATA.plate_thin.toFixed(3) +
                '  plate_thin_scale=' + DATA.plate_thin_scale.toFixed(3) +
                '  width_ratio=' + DATA.width_ratio.toFixed(3) +
                '  size=' + SIZE,
            '# scale = 源图（底板取标志层）的缩放倍数',
            '# name\tkind\tvisual\tauto\tscale\tsite'
        ];
        mounted.forEach(function (item) {
            lines.push([
                item.icon.name,
                item.icon.plate ? 'plate' : 'logo',
                (item.value / 100).toFixed(3),
                item.icon.auto.toFixed(3),
                scaleOf(item, item.value).toFixed(3),
                item.site
            ].join('\t'));
        });
        return lines.join('\n');
    }

    document.getElementById('labCopy').addEventListener('click', function () {
        var text = exportText();
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                flash('已复制 ' + mounted.length + ' 个图标');
            }, function () {
                window.prompt('复制参数：', text);
            });
        } else {
            window.prompt('复制参数：', text);
        }
    });

    document.getElementById('labReset').addEventListener('click', function () {
        try { localStorage.removeItem(KEY); } catch (error) { /* 忽略 */ }
        mounted.forEach(function (item) { paint(item, item.auto); });
        group.logo = Math.round(DATA.fill * 100);
        group.plate = Math.round(DATA.plate * 100);
        paintGroup();
        flash('已重置为自动大小');
    });
})();
