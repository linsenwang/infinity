// 全局配置：搜索引擎的唯一数据源
// index.html 和 js/search.js 都从这里取数据，不再各自维护一份 URL 表
window.INFINITY_CONFIG = {
    // 搜索框回车时使用的引擎，对应下面 searchEngines 的 key
    defaultEngine: 'bilibili',

    // 搜索引擎：key 为标识符
    // url 为查询前缀，实际请求为 url + encodeURIComponent(关键词)
    // 带 icon 的引擎会渲染成搜索框下方的按钮，显示顺序见 searchButtons
    searchEngines: {
        douban: {
            name: '豆瓣',
            url: 'https://www.douban.com/search?cat=1001&q=',
            icon: 'web_icon/icon-1h9qu2pjo4erf7nyvrdhiut0t3p.webp'
        },
        youtube: {
            name: 'YouTube',
            url: 'https://www.youtube.com/results?search_query=',
            icon: 'web_icon/youtube.webp'
        },
        goodreads: {
            name: 'Goodreads',
            url: 'https://www.goodreads.com/search?q=',
            icon: 'web_icon/goodreads.webp'
        },
        zlib: {
            name: 'Z-Library',
            url: 'https://z-lib.fm/s/',
            icon: 'web_icon/icon-1hmp4ecnvaeh5sqtmolvvtyq33r.webp'
        },
        jd: {
            name: '京东',
            url: 'https://search.jd.com/Search?keyword=',
            icon: 'web_icon/jd.webp'
        },
        zhihu: {
            name: '知乎',
            url: 'https://www.zhihu.com/search?type=content&q=',
            icon: 'web_icon/icon-1hht7hv1igpf4w4lfyqc3cuvkyn.webp'
        },
        taobao: {
            name: '淘宝',
            url: 'https://s.taobao.com/search?q=',
            icon: 'web_icon/taobao.webp'
        },
        bilibili: {
            name: 'Bilibili',
            url: 'https://search.bilibili.com/all?keyword=',
            icon: 'web_icon/b-favicon-l.webp'
        },
        // 以下引擎没有按钮，仅作为搜索引擎备用（也可直接填 defaultEngine）
        google: {
            name: 'Google',
            url: 'https://www.google.com/search?q='
        },
        bing: {
            name: 'Bing',
            url: 'https://www.bing.com/search?q='
        },
        baidu: {
            name: '百度',
            url: 'https://www.baidu.com/s?wd='
        }
    },

    // 搜索按钮的显示顺序，元素为 searchEngines 的 key
    searchButtons: [
        'douban',
        'youtube',
        'goodreads',
        'zlib',
        'jd',
        'zhihu',
        'taobao',
        'bilibili'
    ]
};
