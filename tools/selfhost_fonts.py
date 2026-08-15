"""
Self-host the webfonts.

Google Fonts is the only third-party request the site makes. Every visitor's IP
is disclosed to Google on every page load, which German courts have held
breaches the GDPR, and it costs a DNS lookup plus a TLS handshake to a second
origin before any text can render.

Twelve slightly different Google URLs exist across the 57 pages. They are
merged into one local stylesheet, so a page that used to fetch its own
combination now shares a single cached file.

The Cyrillic subsets are downloaded along with the Latin ones — the Russian
pages need them, and dropping them to save bytes would silently degrade every
_ru page to a system fallback. unicode-range is preserved, so a browser still
only downloads the subsets it actually needs.
"""
import io, os, re, sys, urllib.request

FRONTEND = 'c:/Users/deadv/Downloads/tour_pj/main/frontend'
FONT_DIR = os.path.join(FRONTEND, 'fonts')
# A modern UA makes Google serve woff2; an old one gets ttf and quadruples size.
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode('utf-8')


def main():
    os.makedirs(FONT_DIR, exist_ok=True)

    urls = set()
    for name in os.listdir(FRONTEND):
        if not name.endswith('.html'):
            continue
        html = io.open(os.path.join(FRONTEND, name), encoding='utf-8', newline='').read()
        urls.update(re.findall(r'https://fonts\.googleapis\.com/css2\?[^"\']+', html))
    print('distinct Google Fonts URLs found:', len(urls))

    blocks, seen_src = [], {}
    for url in sorted(urls):
        css = fetch(url.replace('&amp;', '&'))
        for block in re.findall(r'@font-face\s*\{[^}]*\}', css):
            src = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", block)
            if not src:
                continue
            # The site is English and Russian only. A Vietnamese subset would
            # never be fetched thanks to unicode-range, but it still ships 8
            # files in the repo for nothing. Regenerating re-adds it if the
            # content ever needs it.
            urange = re.search(r'unicode-range:([^;]+)', block)
            if urange and '1EA0' in urange.group(1):
                continue
            remote = src.group(1)
            if remote not in seen_src:
                fname = remote.rsplit('/', 1)[-1].split('?')[0]
                fam = re.search(r"font-family:\s*'([^']+)'", block)
                fname = (fam.group(1).replace(' ', '') + '-' + fname) if fam else fname
                path = os.path.join(FONT_DIR, fname)
                if not os.path.exists(path):
                    open(path, 'wb').write(fetch(remote, binary=True))
                seen_src[remote] = fname
                blocks.append(block.replace(remote, 'fonts/' + fname))
    print('font files:', len(seen_src))

    header = (
        '/* Self-hosted webfonts — generated, do not hand-edit.\n'
        ' *\n'
        ' * Was https://fonts.googleapis.com on all 57 pages, the only third-party\n'
        ' * request the site made: every visitor IP disclosed to Google, plus a DNS\n'
        ' * lookup and TLS handshake to a second origin before any text could render.\n'
        ' *\n'
        ' * Cyrillic subsets are included because the _ru pages need them, and\n'
        ' * unicode-range is preserved so a browser still fetches only what it uses.\n'
        ' *\n'
        ' * Regenerate with tools/selfhost_fonts.py if a family or weight changes.\n'
        ' */\n\n'
    )
    css_out = header + '\n'.join(b.strip() + '\n' for b in blocks)
    io.open(os.path.join(FRONTEND, 'fonts.css'), 'w', encoding='utf-8', newline='\n').write(css_out)

    total = sum(os.path.getsize(os.path.join(FONT_DIR, f)) for f in os.listdir(FONT_DIR))
    print('fonts.css: %d faces, %.1f KB of woff2 total' % (len(blocks), total / 1024))


if __name__ == '__main__':
    sys.exit(main())
