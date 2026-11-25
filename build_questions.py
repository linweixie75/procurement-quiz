"""把政府電子採購網下載的「全部題庫.doc」(實際是 RTF) 轉成題庫資料，並嵌進 site/index.html。

用法: python build_questions.py <全部題庫.doc路徑>
"""
import hashlib, json, re, sys
from pathlib import Path


def rtf_to_text(raw: str) -> str:
    out = []
    tok = re.compile(
        r"\\u(-?\d+) ?(?:\\'[0-9a-f]{2}|\?)?"
        r"|\\(par|cell|row)\b ?"
        r"|\\'([0-9a-f]{2})"
        r"|\\[a-zA-Z]+-?\d* ?"
        r"|\\."
        r"|[{}\r\n]"
        r"|([^\\{}\r\n]+)")
    for m in tok.finditer(raw):
        if m.group(1):
            n = int(m.group(1)); out.append(chr(n if n >= 0 else n + 65536))
        elif m.group(2) == 'par': out.append('\n')
        elif m.group(2) == 'cell': out.append('\t')
        elif m.group(2) == 'row': out.append('\n')
        elif m.group(4): out.append(m.group(4))
    return ''.join(out)


OPT = re.compile(r'[(（]([1-4])[)）]')


def split_options(text):
    """從題目文字尾端往回找 (4)(3)(2)(1)，回傳 (題幹, [選項1..4]) 或 None。"""
    end = len(text); cuts = []
    for k in '4321':
        idx = None
        for m in OPT.finditer(text, 0, end):
            if m.group(1) == k: idx = m
        if idx is None: return None
        cuts.append(idx); end = idx.start()
    cuts.reverse()
    stem = text[:cuts[0].start()].strip()
    opts = []
    for i, m in enumerate(cuts):
        stop = cuts[i + 1].start() if i < 3 else len(text)
        opts.append(text[m.end():stop].strip())
    return stem, opts


WEB_HEAD = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d6b66">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="採購刷題">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-180.png">
<link rel="icon" href="icon-192.png">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
__HEADEXTRA__
</head>
<body>
"""

WEB_TAIL = """
<script>if ('serviceWorker' in navigator) addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));</script>
</body>
</html>
"""

MANIFEST = {
    "name": "採購法規刷題本", "short_name": "採購刷題", "lang": "zh-Hant",
    "start_url": "./", "scope": "./", "display": "standalone",
    "background_color": "#f3f4f1", "theme_color": "#0d6b66",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
}

SW = """// 離線快取：頁面先上網抓新版，沒網路時用上次存的版本
const CACHE = 'pq-__VER__';
const FILES = ['./', 'index.html', 'manifest.webmanifest', 'icon-180.png', 'icon-192.png', 'icon-512.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES))); self.skipWaiting(); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('pq-') && k !== CACHE && k !== 'pq-fonts').map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.origin === location.origin) {
    if (r.mode === 'navigate') {
      e.respondWith(fetch(r).then(res => { const c = res.clone(); caches.open(CACHE).then(ca => ca.put('./', c)); return res; })
        .catch(() => caches.match('./').then(m => m || caches.match('index.html'))));
    } else {
      e.respondWith(caches.match(r).then(m => m || fetch(r)));
    }
  } else if (u.hostname.endsWith('fonts.googleapis.com') || u.hostname.endsWith('fonts.gstatic.com')) {
    e.respondWith(caches.match(r).then(m => m || fetch(r).then(res => { const c = res.clone(); caches.open('pq-fonts').then(ca => ca.put(r, c)); return res; })));
  }
});
"""


def build_web(page, out):
    """產生可放上 GitHub Pages 的網站：完整 HTML、manifest、離線快取。"""
    out.mkdir(exist_ok=True)
    # 把 <title> 和字型連結移進 <head>
    extra = []
    for pat in (r'<title>.*?</title>\n?', r'<meta name="claude:[^>]*>\n?', r'<link rel="preconnect"[^>]*>\n?', r'<link rel="stylesheet"[^>]*>\n?'):
        m = re.search(pat, page)
        if m:
            if 'claude:' not in m.group(0): extra.append(m.group(0).strip())
            page = page.replace(m.group(0), '', 1)
    html = WEB_HEAD.replace('__HEADEXTRA__', '\n'.join(extra)) + page + WEB_TAIL
    (out / 'index.html').write_text(html, encoding='utf-8')
    (out / 'manifest.webmanifest').write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=1), encoding='utf-8')
    ver = hashlib.sha1(html.encode()).hexdigest()[:10]
    (out / 'sw.js').write_text(SW.replace('__VER__', ver), encoding='utf-8')
    (out / '.nojekyll').write_text('', encoding='utf-8')


def main(src):
    text = rtf_to_text(Path(src).read_text(encoding='latin-1'))
    date = re.search(r'資料產生日期：([\d/]+)', text)
    cats, qs, problems = [], [], []
    cat = kind = None
    for line in text.split('\n'):
        cells = [c.strip() for c in line.split('\t')]
        cells = [c for c in cells if c != ''] if len(cells) > 1 else cells
        if len(cells) == 1:
            s = cells[0].strip()
            if not s or s.startswith(';') : continue
            if s in ('選擇題', '是非題'): kind = 'mc' if s == '選擇題' else 'tf'
            else:
                cat = s
                if cat not in cats: cats.append(cat)
            continue
        if cells[0] == '編號': continue
        if not cells[0].isdigit():
            problems.append(line); continue
        no, ans, body = cells[0], cells[1], cells[2]
        law = cells[3] if len(cells) > 3 else ''
        q = {'c': cats.index(cat), 't': kind, 'n': int(no), 'a': ans}
        if kind == 'mc':
            sp = split_options(body)
            if not sp or ans not in '1234':
                problems.append(line); continue
            q['q'], q['o'] = sp
        else:
            if ans not in 'OX':
                problems.append(line); continue
            q['q'] = body
        if law: q['l'] = law
        # 用題目內容做 ID，題庫重新編號時答題紀錄仍能對應
        q['id'] = hashlib.sha1((cat + kind + body).encode()).hexdigest()[:10]
        qs.append(q)
    ids = [q['id'] for q in qs]
    assert len(ids) == len(set(ids)), '重複 ID'
    out = {'date': date.group(1) if date else '', 'cats': cats, 'qs': qs}
    here = Path(__file__).parent / 'site'
    data = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    (here / 'questions.json').write_text(data, encoding='utf-8')
    # 題庫直接嵌進網頁（app.html 是範本，index.html 是要發布的成品）
    tpl = (here / 'app.html').read_text(encoding='utf-8')
    assert tpl.count('__QDATA__') == 1
    page = tpl.replace('__QDATA__', data.replace('<', '\\u003c'))
    (here / 'index.html').write_text(page, encoding='utf-8')
    build_web(page, Path(__file__).parent / 'docs')
    print(f"題庫日期 {out['date']}，{len(cats)} 類，{len(qs)} 題"
          f"（選擇 {sum(q['t']=='mc' for q in qs)}、是非 {sum(q['t']=='tf' for q in qs)}）")
    for p in problems: print('無法解析:', p[:120])


if __name__ == '__main__':
    main(sys.argv[1])
