# -*- coding: utf-8 -*-
"""
ICML 2026 全量论文 · 三级目录静态网页渲染
=========================================
输入：ICML2026_all_papers_CN.json（6,567 篇 + 中文六维度分析）
      若不存在，则只用 ICML2026_all_papers.json
输出：index.html

三级树状目录：
  一级（大类，ICML 官方一级方向，~8 个）
   └─ 二级（细分，LLM 标，~76 个）
       └─ 三级（仅对 11 个 ≥150 篇的肥桶切分，~66 个）

正文用嵌套 section，论文卡保留 Spotlight 徽章 + 中文六维度 + 完整摘要折叠。
"""

import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from urllib.parse import quote

INPUT_JSON      = "ICML2026_all_papers.json"
CN_OVERLAY_JSON = "ICML2026_all_papers_CN.json"
OUTPUT_HTML     = "index.html"

# GoatCounter 访问统计（隐私友好、无 cookie）。
# 想换成你自己的：去 https://www.goatcounter.com 免费注册，把下面这个 URL 改成
# 你的 <子域>.goatcounter.com，置空字符串则不启用统计。
GOATCOUNTER_URL = "https://icml2026-cn.goatcounter.com"

# 六维度
DIM_LABELS = [
    ("研究动机",     "🎯 研究动机"),
    ("解决问题",     "❓ 解决问题"),
    ("现象分析",     "🔍 现象分析"),
    ("主要方法",     "🛠️ 主要方法"),
    ("数据集与实验", "📊 数据与实验"),
    ("主要贡献",     "⭐ 主要贡献"),
]

# 兜底锚点
FLAT_KEY = "_FLAT_"

# 一级大类的固定展示顺序：按"方法 → 基础 → 应用/影响"分组，而不是按论文数。
# 没列在这里的大类会按论文数降序追加在后面（兜底）。
PRIMARY_ORDER_PREFERRED = [
    "深度学习",
    "强化学习",
    "通用机器学习",
    "优化",
    "概率方法",
    "理论",
    "应用",
    "社会议题 (对齐/安全/公平等)",
]


def _norm(s):
    s = (s or "").strip()
    return s if s else "(未分类)"


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f6f8fa;color:#24292e;line-height:1.7}
.container{display:flex;min-height:100vh}
.sidebar{width:340px;background:#fff;border-right:1px solid #e1e4e8;padding:24px 18px;position:sticky;top:0;height:100vh;overflow-y:auto}
.sidebar .group-logo{display:block;width:100%;max-width:280px;margin:0 auto 14px;padding-bottom:14px;border-bottom:1px solid #eaecef}
.sidebar .group-logo img{display:block;width:100%;height:auto}
.sidebar h1{font-size:18px;margin-bottom:6px;color:#0366d6;line-height:1.3;font-weight:700}
.sidebar .sub{font-size:12px;color:#6a737d;margin-bottom:16px}
.sister-site{margin-bottom:14px}
.sister-site a{display:flex;align-items:center;gap:8px;padding:8px 12px;background:linear-gradient(135deg,#e7f3ff,#fff4f4);color:#0366d6;text-decoration:none;font-size:12px;font-weight:500;border-radius:6px;border:1px solid #d1e5fa;transition:all .15s}
.sister-site a:hover{background:linear-gradient(135deg,#d1e7ff,#ffe0e0);transform:translateY(-1px);box-shadow:0 2px 8px rgba(3,102,214,.15);border-color:#0366d6}
.sister-site .arrow{margin-left:auto;color:#0366d6;opacity:.6}
.sidebar input[type=search]{width:100%;padding:9px 12px;border:1px solid #d1d5da;border-radius:6px;margin-bottom:14px;font-size:13px;outline:none}
.sidebar input[type=search]:focus{border-color:#0366d6;box-shadow:0 0 0 2px rgba(3,102,214,.2)}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:16px}
.stat-box{background:#f6f8fa;padding:8px 10px;border-radius:6px;font-size:11px;color:#586069}
.stat-box b{color:#0366d6;font-size:14px;display:block}

/* 三级树状导航 */
.nav-tree{font-size:13px}
.nav-pri{margin-bottom:4px;border-radius:5px;overflow:hidden}
.nav-pri-head{display:flex;align-items:center;cursor:pointer;padding:7px 10px;background:#f6f8fa;border-radius:5px;font-weight:600;color:#24292e;user-select:none;transition:background .15s}
.nav-pri-head:hover{background:#e7f3ff}
.nav-pri-head .arrow{margin-right:6px;font-size:10px;color:#959da5;transition:transform .2s;flex-shrink:0;width:10px;text-align:center}
.nav-pri.expanded > .nav-pri-head .arrow{transform:rotate(90deg)}
.nav-pri-head .name{flex:1}
.nav-pri-head .count{color:#6a737d;font-size:11px;background:#eaecef;padding:2px 8px;border-radius:10px;font-weight:500}

.nav-sub-list{display:none;padding:4px 0 6px 16px}
.nav-pri.expanded > .nav-sub-list{display:block}

/* 二级：肥桶可展开（含三级），瘦桶直链 */
.nav-sub{margin:1px 0;border-radius:4px}
.nav-sub-head{display:flex;align-items:center;cursor:pointer;padding:5px 8px;color:#24292e;text-decoration:none;font-size:12.5px;font-weight:500;border-radius:4px;user-select:none;transition:background .15s}
.nav-sub-head:hover{background:#e7f3ff;color:#0366d6}
.nav-sub-head .arrow{margin-right:5px;font-size:9px;color:#959da5;transition:transform .2s;flex-shrink:0;width:8px;text-align:center}
.nav-sub.expanded > .nav-sub-head .arrow{transform:rotate(90deg)}
.nav-sub-head .name{flex:1}
.nav-sub-head .count{color:#959da5;font-size:11px;margin-left:6px}

.nav-thin{display:flex;align-items:center;padding:5px 8px 5px 13px;color:#586069;text-decoration:none;border-radius:4px;font-size:12.5px;margin-bottom:1px;transition:background .15s}
.nav-thin:hover{background:#f1f4f7;color:#0366d6}
.nav-thin .name{flex:1}
.nav-thin .count{color:#959da5;font-size:11px;margin-left:6px}

.nav-subsub-list{display:none;padding:2px 0 4px 18px}
.nav-sub.expanded > .nav-subsub-list{display:block}
.nav-subsub-list a{display:flex;align-items:center;padding:4px 8px;color:#586069;text-decoration:none;border-radius:3px;font-size:12px;margin-bottom:1px;transition:background .15s}
.nav-subsub-list a:hover{background:#f1f4f7;color:#0366d6}
.nav-subsub-list a .name{flex:1}
.nav-subsub-list a .count{color:#959da5;font-size:10.5px;margin-left:6px}

.main{flex:1;padding:32px 44px;max-width:calc(100% - 340px)}
.main-header{margin-bottom:32px;padding-bottom:18px;border-bottom:1px solid #e1e4e8}
.main-header h1{font-size:28px;margin-bottom:10px}
.main-header p{color:#586069;font-size:14px}

h2.pri-title{font-size:24px;color:#0366d6;border-bottom:2px solid #0366d6;padding-bottom:8px;margin:40px 0 12px;scroll-margin-top:20px}
h2.pri-title small{font-size:13px;color:#6a737d;font-weight:400;margin-left:8px}
h3.sub-title{font-size:18px;color:#24292e;border-left:4px solid #0366d6;padding:4px 12px;margin:24px 0 14px;scroll-margin-top:20px;background:#f6f8fa;border-radius:0 4px 4px 0}
h3.sub-title small{font-size:12px;color:#6a737d;font-weight:400;margin-left:8px}
h4.subsub-title{font-size:15px;color:#24292e;padding:3px 10px;margin:18px 0 10px;scroll-margin-top:20px;background:#eef4ff;border-left:3px solid #5b8def;border-radius:0 3px 3px 0;font-weight:600}
h4.subsub-title small{font-size:11.5px;color:#6a737d;font-weight:400;margin-left:6px}

.paper{background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:18px 22px;margin-bottom:14px;box-shadow:0 1px 2px rgba(0,0,0,.04);transition:box-shadow .15s;position:relative}
.paper:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}
.paper.tier-Oral{border-left:4px solid #d4a017;background:linear-gradient(to right, #fffaeb 0, #fff 80px)}
.paper.tier-Spotlight{border-left:4px solid #d4a017;background:linear-gradient(to right, #fffaeb 0, #fff 80px)}
.tier-badge{display:inline-block;font-weight:700;font-size:11px;padding:2px 9px;border-radius:10px;margin-right:6px;letter-spacing:.3px;vertical-align:middle}
.tier-badge.Oral{background:#fff4d4;color:#8a6500;border:1px solid #d4a017}
.tier-badge.Spotlight{background:#fff4d4;color:#8a6500;border:1px solid #d4a017}

.tier-summary{margin:18px 0;display:flex;gap:8px;flex-wrap:wrap}
.tier-chip{display:inline-flex;align-items:center;padding:5px 12px;border-radius:14px;font-size:12px;font-weight:600;cursor:pointer;user-select:none;border:1px solid transparent;transition:all .15s}
.tier-chip.all{background:#eaecef;color:#24292e}
.tier-chip.all.active{background:#0366d6;color:#fff}
.tier-chip.Oral{background:#fff4d4;color:#8a6500;border-color:#d4a017}
.tier-chip.Oral.active{background:#d4a017;color:#fff}
.tier-chip.Spotlight{background:#fff4d4;color:#8a6500;border-color:#d4a017}
.tier-chip.Spotlight.active{background:#d4a017;color:#fff}
.tier-chip:hover{transform:translateY(-1px)}

.paper-title{font-size:16px;font-weight:600;color:#24292e;margin-bottom:8px;line-height:1.45}
.paper-title a{color:inherit;text-decoration:none}
.paper-title a:hover{color:#0366d6;text-decoration:underline}
.paper-title .sidelink{margin-left:8px;color:#6a737d;font-size:11.5px;font-weight:500;text-decoration:none;background:#f1f3f5;padding:2px 8px;border-radius:10px;vertical-align:middle}
.paper-title .sidelink:hover{background:#e7f3ff;color:#0366d6}
.paper-meta{font-size:12px;color:#586069;margin-bottom:10px}
.paper-meta .badge{display:inline-block;background:#e7f3ff;color:#0366d6;padding:2px 8px;border-radius:10px;margin-right:5px;font-size:11px;font-weight:500}
.paper-meta .badge.sub{background:#eaecef;color:#24292e}
.paper-meta .badge.subsub{background:#eef4ff;color:#1f4dad}
.paper-meta .authors{color:#6a737d;font-size:11.5px;margin-top:4px;line-height:1.5}
.dim{margin:8px 0;font-size:13.5px;display:flex;gap:10px;align-items:flex-start}
.dim-label{flex-shrink:0;font-weight:600;color:#0366d6;width:96px;font-size:12.5px;padding-top:1px}
.dim-content{flex:1;color:#24292e}
.toggle-abs{font-size:12px;color:#0366d6;cursor:pointer;margin-top:10px;display:inline-block;user-select:none;padding:3px 8px;border-radius:4px}
.toggle-abs:hover{background:#e7f3ff}
.full-abs{display:none;margin-top:10px;padding:11px 14px;background:#f6f8fa;border-radius:5px;font-size:12.5px;color:#444;line-height:1.65;border-left:3px solid #d1d5da}
.paper.expanded .full-abs{display:block}
.paper.expanded .toggle-abs::before{content:"▾ "}
.paper:not(.expanded) .toggle-abs::before{content:"▸ "}
/* 提示条 */
.info-notice{background:#fffbea;border:1px solid #f9c513;border-radius:6px;padding:12px 18px;margin:18px 0 24px;font-size:13px;color:#735c0f;line-height:1.75}
.info-notice b{color:#5a4500}
.info-notice ul{margin:6px 0 0 22px;padding:0}
.info-notice li{margin:4px 0}
.info-notice code{background:#fff4d4;padding:1px 6px;border-radius:3px;color:#5a4500;font-size:12px}
.hidden{display:none !important}
.empty{text-align:center;color:#959da5;padding:40px;font-size:14px}
.no-cn{font-style:italic;color:#959da5}

/* 回到顶部浮动按钮 */
#back-to-top{position:fixed;bottom:32px;right:32px;width:48px;height:48px;border-radius:50%;background:#0366d6;color:#fff;border:none;font-size:22px;cursor:pointer;box-shadow:0 4px 12px rgba(3,102,214,.35);display:flex;align-items:center;justify-content:center;opacity:0;visibility:hidden;transform:translateY(8px);transition:all .25s ease;z-index:1000;line-height:1}
#back-to-top:hover{background:#0256b8;transform:translateY(-2px);box-shadow:0 6px 18px rgba(3,102,214,.45)}
#back-to-top.show{opacity:1;visibility:visible;transform:translateY(0)}
#back-to-top:focus{outline:2px solid #5b8def;outline-offset:2px}

@media(max-width:900px){
  .container{flex-direction:column}
  .sidebar{width:100%;height:auto;position:relative}
  .main{max-width:100%;padding:20px}
  .dim{flex-direction:column;gap:4px}
  .dim-label{width:auto}
}
"""


JS = """
const search=document.getElementById('search');
const papers=document.querySelectorAll('.paper');
const subsubSecs=document.querySelectorAll('section.subsub-sec');
const subSecs=document.querySelectorAll('section.sub-sec');
const priSecs=document.querySelectorAll('section.pri-sec');
const tierChips=document.querySelectorAll('.tier-chip');

let activeTier='__all__';

// L1 折叠：点击大类头部展开/收起 L2 列表
document.querySelectorAll('.nav-pri-head').forEach(h=>{
  h.addEventListener('click', e=>{
    if(e.target.closest('.nav-sub-list')) return;
    h.parentElement.classList.toggle('expanded');
  });
});

// L2 折叠（肥桶才有 nav-sub-head）：点击展开/收起 L3 列表
document.querySelectorAll('.nav-sub-head').forEach(h=>{
  h.addEventListener('click', e=>{
    if(e.target.closest('.nav-subsub-list')) return;
    h.parentElement.classList.toggle('expanded');
  });
});

function applyFilters(){
  const q=(search.value||'').trim().toLowerCase();
  papers.forEach(p=>{
    const t=p.dataset.search||'';
    const myTier=p.dataset.tier||'Poster';
    const matchSearch=!q || t.includes(q);
    const matchTier=(activeTier==='__all__') || (myTier===activeTier);
    p.classList.toggle('hidden', !(matchSearch && matchTier));
  });
  const filtering = q || activeTier!=='__all__';

  // 三级 section 计数 + 隐藏空 + 更新对应 nav-subsub-list 链接
  subsubSecs.forEach(s=>{
    const visible=s.querySelectorAll('.paper:not(.hidden)').length;
    s.classList.toggle('hidden', visible===0);
    const link=document.querySelector('.nav-subsub-list a[href="#'+s.id+'"]');
    if(link){
      const cnt=link.querySelector('.count');
      if(cnt) cnt.textContent='('+visible+')';
      link.classList.toggle('hidden', visible===0);
    }
  });

  // 二级 section
  subSecs.forEach(s=>{
    const visible=s.querySelectorAll('.paper:not(.hidden)').length;
    s.classList.toggle('hidden', visible===0);
    // nav 里二级有两种：肥桶 .nav-sub (含 head) 或瘦桶 .nav-thin
    const navSub=document.getElementById('nav-'+s.id);
    if(navSub){
      const cnt=navSub.querySelector('.count');
      if(cnt) cnt.textContent= navSub.classList.contains('nav-thin') ? '('+visible+')' : visible;
      navSub.classList.toggle('hidden', visible===0);
      if(filtering && visible>0 && navSub.classList.contains('nav-sub')) navSub.classList.add('expanded');
      if(!filtering && navSub.classList.contains('nav-sub')) navSub.classList.remove('expanded');
    }
  });

  // 一级 section
  priSecs.forEach(s=>{
    const visible=s.querySelectorAll('.paper:not(.hidden)').length;
    s.classList.toggle('hidden', visible===0);
    const prinav=document.getElementById('nav-'+s.id);
    if(prinav){
      const cnt=prinav.querySelector('.nav-pri-head .count');
      if(cnt) cnt.textContent=visible;
      prinav.classList.toggle('hidden', visible===0);
      if(filtering && visible>0) prinav.classList.add('expanded');
      if(!filtering) prinav.classList.remove('expanded');
    }
  });
}

search.addEventListener('input', applyFilters);
tierChips.forEach(chip=>{
  chip.addEventListener('click', ()=>{
    activeTier = chip.dataset.tier;
    tierChips.forEach(c => c.classList.toggle('active', c===chip));
    applyFilters();
  });
});

// 回到顶部
const backTop = document.getElementById('back-to-top');
const mainEl = document.querySelector('.main');
function checkScroll(){
  // 监听 window 和 main 容器两个滚动源（手机/桌面布局不同）
  const y = window.scrollY || document.documentElement.scrollTop || (mainEl ? mainEl.scrollTop : 0);
  backTop.classList.toggle('show', y > 400);
}
window.addEventListener('scroll', checkScroll, {passive:true});
if (mainEl) mainEl.addEventListener('scroll', checkScroll, {passive:true});
backTop.addEventListener('click', ()=>{
  window.scrollTo({top:0, behavior:'smooth'});
  if (mainEl) mainEl.scrollTo({top:0, behavior:'smooth'});
});
"""


def _anchor(*parts):
    return "-".join(quote(p, safe="") for p in parts)


def _sort_named(items):
    """按 (是否"其他", -数量, 名字) 排序；items 是 [(name, count)] 列表"""
    return sorted(items, key=lambda kv: (kv[0] == "其他" or kv[0].startswith("其他"), -kv[1], kv[0]))


def _render_paper(p):
    title = escape(p["title"])
    icml_url = p.get("url") or ""
    paper_url = p.get("paper_url") or ""
    gs_url = "https://scholar.google.com/scholar?q=" + quote(p["title"])
    title_href = escape(gs_url)
    side_links = []
    if paper_url:
        side_links.append(f'<a class="sidelink" href="{escape(paper_url)}" target="_blank">📝 OpenReview</a>')
    if icml_url:
        side_links.append(f'<a class="sidelink" href="{escape(icml_url)}" target="_blank">🌐 ICML</a>')
    side_link_html = "".join(side_links)

    primary_badge = escape(p.get("primary_area", "") or "")
    sub_badge = escape(p.get("category", "") or "")
    subsub = p.get("subcategory") or ""
    subsub_badge_html = f'<span class="badge subsub">{escape(subsub)}</span>' if subsub else ""

    authors = p.get("authors", []) or []
    authors_str = "、".join(authors[:8])
    if len(authors) > 8:
        authors_str += f" 等 {len(authors)} 人"
    authors_html = f'<div class="authors">👤 {escape(authors_str)}</div>' if authors_str else ""

    analysis = p.get("中文分析") or {}
    if analysis:
        dims = []
        for key, label in DIM_LABELS:
            val = analysis.get(key, "") or ""
            dims.append(
                f'<div class="dim"><span class="dim-label">{label}</span>'
                f'<div class="dim-content">{escape(val)}</div></div>'
            )
        dims_block = "".join(dims)
    else:
        dims_block = '<div class="dim no-cn">（中文六维度分析尚未生成）</div>'

    tier = (p.get("tier") or "Poster").strip()
    tier_badge_html = ""
    if tier == "Oral":
        tier_badge_html = '<span class="tier-badge Oral">🎤 Oral</span>'
    elif tier == "Spotlight":
        tier_badge_html = '<span class="tier-badge Spotlight">⭐ Spotlight</span>'
    paper_class = f"paper tier-{escape(tier)}"

    search_blob = (
        p["title"] + " " + " ".join(authors) + " "
        + p.get("primary_area", "") + " " + p.get("category", "") + " "
        + (p.get("subcategory") or "") + " " + tier + " "
        + (p.get("icml_subtopic_en", "") or "")
    ).lower()

    return f"""
<article class="{paper_class}" data-search="{escape(search_blob)}" data-tier="{escape(tier)}">
  <div class="paper-title">{tier_badge_html}<a href="{title_href}" target="_blank">{title}</a>{side_link_html}</div>
  <div class="paper-meta">
    {f'<span class="badge">{primary_badge}</span>' if primary_badge else ''}
    {f'<span class="badge sub">{sub_badge}</span>' if sub_badge else ''}
    {subsub_badge_html}
    {authors_html}
  </div>
  {dims_block}
  <span class="toggle-abs" onclick="this.parentElement.classList.toggle('expanded')">查看完整摘要 (Abstract)</span>
  <div class="full-abs">{escape(p.get('abstract','') or '')}</div>
</article>"""


def build():
    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    papers = data["papers"]

    # 叠加中文分析
    cn_map = {}
    if Path(CN_OVERLAY_JSON).exists():
        cn_data = json.loads(Path(CN_OVERLAY_JSON).read_text(encoding="utf-8"))
        cn_map = {p["id"]: p.get("中文分析") for p in cn_data.get("papers", []) if p.get("中文分析")}
    n_with_cn = 0
    for p in papers:
        p["primary_area"] = _norm(p.get("primary_area"))
        p["category"] = _norm(p.get("category"))
        if p["id"] in cn_map:
            p["中文分析"] = cn_map[p["id"]]
            n_with_cn += 1

    # 分组：pri → cat → (subcat or _FLAT_) → [papers]
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for p in papers:
        sub = p.get("subcategory")  # None or 空 → 瘦桶
        sub_key = sub if sub else FLAT_KEY
        grouped[p["primary_area"]][p["category"]][sub_key].append(p)

    # L1 顺序：优先用 PRIMARY_ORDER_PREFERRED 里固定的顺序，
    # 没列入的兜底按论文数降序追加在末尾。
    pri_count = Counter(p["primary_area"] for p in papers)
    seen = set()
    primary_order = []
    for name in PRIMARY_ORDER_PREFERRED:
        if name in pri_count and name not in seen:
            primary_order.append(name)
            seen.add(name)
    # 兜底
    for name, _ in pri_count.most_common():
        if name not in seen:
            primary_order.append(name)
            seen.add(name)

    total = len(papers)
    n_pri = len(primary_order)
    n_sub_total = sum(len(cats) for cats in grouped.values())
    n_subsub_total = 0
    for pa, cats in grouped.items():
        for cat, subs in cats.items():
            real = [k for k in subs if k != FLAT_KEY]
            n_subsub_total += len(real)
    tier_cnt = Counter(p.get("tier") or "Poster" for p in papers)
    n_oral = tier_cnt.get("Oral", 0)
    n_spotlight = tier_cnt.get("Spotlight", 0)

    # GoatCounter 统计代码
    if GOATCOUNTER_URL:
        gc_stats_html = (
            '<br><span id="visit-stats" style="display:none">'
            '👁 总访问 <b id="gc-pv" style="color:#0366d6"></b> 次　·　'
            '访客 <b id="gc-uv" style="color:#0366d6"></b> 人</span>'
        )
        gc_script_html = (
            f'<script data-goatcounter="{GOATCOUNTER_URL}/count" async src="//gc.zgo.at/count.js"></script>'
            '<script>'
            f'fetch("{GOATCOUNTER_URL}/counter/TOTAL.json")'
            '.then(r => r.json()).then(d => {'
            'const pv = document.getElementById("gc-pv");'
            'const uv = document.getElementById("gc-uv");'
            'const fmt = n => (n || "0").toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",");'
            'pv.textContent = fmt(d.count);'
            'uv.textContent = fmt(d.count_unique);'
            'document.getElementById("visit-stats").style.display = "inline";'
            '}).catch(()=>{});'
            '</script>'
        )
    else:
        gc_stats_html = ""
        gc_script_html = ""

    # ============ 侧边栏 nav HTML ============
    nav_html = []
    for pa in primary_order:
        cats = grouped[pa]
        pa_anchor = "pri-" + _anchor(pa)
        pa_count = sum(sum(len(ps) for ps in subs.values()) for subs in cats.values())

        # 二级排序：先按数量降序，"其他"放最后
        cat_items = [(c, sum(len(ps) for ps in subs.values())) for c, subs in cats.items()]
        cat_items = _sort_named(cat_items)

        sub_blocks = []
        for cat, ctot in cat_items:
            subs = cats[cat]
            sub_anchor = "sub-" + _anchor(pa, cat)
            real_subcats = [k for k in subs if k != FLAT_KEY]
            if not real_subcats:
                # 瘦桶：直链
                sub_blocks.append(
                    f'<a id="nav-{sub_anchor}" class="nav-thin" href="#{sub_anchor}">'
                    f'<span class="name">{escape(cat)}</span>'
                    f'<span class="count">({ctot})</span></a>'
                )
            else:
                # 肥桶：可展开，三级直链（若有待分则也作为一个三级）
                ss_items = [(s, len(ps)) for s, ps in subs.items() if s != FLAT_KEY]
                ss_items = _sort_named(ss_items)
                if FLAT_KEY in subs:
                    ss_items.append(("(待分)", len(subs[FLAT_KEY])))
                ss_links = []
                for s, sct in ss_items:
                    real_s = FLAT_KEY if s == "(待分)" else s
                    ss_anchor = "subsub-" + _anchor(pa, cat, real_s)
                    ss_links.append(
                        f'<a href="#{ss_anchor}">'
                        f'<span class="name">{escape(s)}</span>'
                        f'<span class="count">({sct})</span></a>'
                    )
                sub_blocks.append(f"""
<div id="nav-{sub_anchor}" class="nav-sub">
  <div class="nav-sub-head">
    <span class="arrow">▶</span>
    <span class="name">{escape(cat)}</span>
    <span class="count">{ctot}</span>
  </div>
  <div class="nav-subsub-list">{''.join(ss_links)}</div>
</div>""")

        nav_html.append(f"""
<div id="nav-{pa_anchor}" class="nav-pri">
  <div class="nav-pri-head">
    <span class="arrow">▶</span>
    <span class="name">{escape(pa)}</span>
    <span class="count">{pa_count}</span>
  </div>
  <div class="nav-sub-list">{''.join(sub_blocks)}</div>
</div>""")

    # ============ 正文 ============
    pri_secs = []
    for pa in primary_order:
        cats = grouped[pa]
        pa_anchor = "pri-" + _anchor(pa)
        pa_count = sum(sum(len(ps) for ps in subs.values()) for subs in cats.values())

        cat_items = [(c, sum(len(ps) for ps in subs.values())) for c, subs in cats.items()]
        cat_items = _sort_named(cat_items)

        sub_secs = []
        for cat, ctot in cat_items:
            subs = cats[cat]
            sub_anchor = "sub-" + _anchor(pa, cat)
            real_subcats = [k for k in subs if k != FLAT_KEY]
            if not real_subcats:
                # 瘦桶：直接列论文
                cards = "".join(_render_paper(p) for p in subs[FLAT_KEY])
                sub_secs.append(f"""
<section id="{sub_anchor}" class="sub-sec">
  <h3 class="sub-title">{escape(cat)}<small>{ctot} 篇</small></h3>
  {cards}
</section>""")
            else:
                # 肥桶：三级子 section
                ss_items = [(s, len(ps)) for s, ps in subs.items() if s != FLAT_KEY]
                ss_items = _sort_named(ss_items)
                subsub_html = []
                for s, sct in ss_items:
                    ss_anchor = "subsub-" + _anchor(pa, cat, s)
                    cards = "".join(_render_paper(p) for p in subs[s])
                    subsub_html.append(f"""
<section id="{ss_anchor}" class="subsub-sec">
  <h4 class="subsub-title">{escape(s)}<small>{sct} 篇</small></h4>
  {cards}
</section>""")
                if FLAT_KEY in subs:
                    ss_anchor = "subsub-" + _anchor(pa, cat, FLAT_KEY)
                    cards = "".join(_render_paper(p) for p in subs[FLAT_KEY])
                    subsub_html.append(f"""
<section id="{ss_anchor}" class="subsub-sec">
  <h4 class="subsub-title">(待分)<small>{len(subs[FLAT_KEY])} 篇</small></h4>
  {cards}
</section>""")
                sub_secs.append(f"""
<section id="{sub_anchor}" class="sub-sec">
  <h3 class="sub-title">{escape(cat)}<small>{ctot} 篇 · {len(ss_items) + (1 if FLAT_KEY in subs else 0)} 个三级</small></h3>
  {''.join(subsub_html)}
</section>""")

        pri_secs.append(f"""
<section id="{pa_anchor}" class="pri-sec">
  <h2 class="pri-title">{escape(pa)}<small>{pa_count} 篇 · {len(cat_items)} 个细分</small></h2>
  {''.join(sub_secs)}
</section>""")

    # ============ HTML ============
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ICML 2026 论文 · 中文导读（{total} 篇）</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <aside class="sidebar">
    <div class="group-logo"><img src="logo.png" alt="Reasoning and Learning Research Group"></div>
    <h1>ICML 2026 论文 · 中文导读</h1>
    <div class="sub">{total} 篇 · {n_pri} 个大类 · {n_sub_total} 个细分 · {n_subsub_total} 个三级</div>
    <div class="sister-site">
      <a href="https://jenniferzhao0531.github.io/ICLR2026-Guide-CN/" target="_blank">
        🔗 ICLR 2026 论文 · 中文导读
        <span class="arrow">→</span>
      </a>
    </div>
    <input type="search" id="search" placeholder="🔍 搜索标题 / 作者…">
    <div class="stat-grid">
      <div class="stat-box"><b>{total}</b>论文总数</div>
      <div class="stat-box"><b>{n_spotlight}</b>Spotlight</div>
    </div>
    <div style="font-size:12px;font-weight:600;color:#586069;margin-bottom:8px">📁 三级目录浏览</div>
    <div class="nav-tree">{''.join(nav_html)}</div>
    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #eaecef;font-size:11px;color:#959da5;line-height:1.6">
      📊 数据来源：<br>ICML 2026 官方虚拟会议站<br>
      （{total} 篇接收论文全部收录）<br><br>
      💡 标题点击跳 Google Scholar 按标题搜（OpenReview forum 现阶段非公开）。<br>
      💡 六维度由 LLM 基于 abstract 自动生成。<br>
      {gc_stats_html}
    </div>
    {gc_script_html}
  </aside>
  <main class="main">
    <div class="main-header">
      <h1>ICML 2026 论文 · 中文导读</h1>
      <p>从 ICML 官方会议站拉取 <b>{total}</b> 篇接收论文，按 <b>{n_pri} 一级 · {n_sub_total} 二级 · {n_subsub_total} 三级</b> 整理。每篇给出"研究动机 / 解决问题 / 现象分析 / 主要方法 / 数据集与实验 / 主要贡献"六个维度的中文分析。中文由 LLM 基于英文 abstract 自动生成，仅供快速浏览，建议结合原文。左侧导航点大类标题展开/收起。</p>
      <div class="tier-summary">
        <span class="tier-chip all active" data-tier="__all__">📚 全部 {total} 篇</span>
        {f'<span class="tier-chip Oral" data-tier="Oral">🎤 Oral {n_oral} 篇</span>' if n_oral > 0 else ''}
        {f'<span class="tier-chip Spotlight" data-tier="Spotlight">⭐ Spotlight {n_spotlight} 篇</span>' if n_spotlight > 0 else ''}
      </div>
      <div class="info-notice">
        💡 <b>关于论文链接的说明：</b>
        <ul>
          <li>点击<b>论文标题</b> → 跳转到 <b>Google Scholar</b> 按标题搜索的结果（通常第一条就能找到 arxiv 版本拿到 PDF）</li>
          <li>点击 <code>📝 OpenReview</code> → ICML 2026 的 OpenReview forum 在大会临近前是非公开的，<b>目前点击会提示无权限</b>，等会议公开后即可正常访问</li>
          <li>点击 <code>🌐 ICML</code> → ICML 官方会议站论文页，<b>目前仅有 abstract 和作者信息</b>，没有正文 PDF</li>
        </ul>
      </div>
    </div>
    {''.join(pri_secs)}
  </main>
</div>
<button id="back-to-top" aria-label="回到顶部" title="回到顶部">↑</button>
<script>{JS}</script>
</body>
</html>
"""

    Path(OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"✅ 已生成 {OUTPUT_HTML}（{total} 篇 · {n_pri} 大类 · {n_sub_total} 细分 · {n_subsub_total} 三级 · {n_with_cn} 篇带中文分析）")


if __name__ == "__main__":
    build()
