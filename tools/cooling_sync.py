# -*- coding: utf-8 -*-
"""
Rewrite every published statement of the free-cancellation window from the
one place it is defined.

Widening the window from 30 minutes to 24 hours meant hand-editing nine files
in two languages. Five were missed, including terms.html and terms-experts.html
— so the site carried a contractual promise the code did not keep, and nothing
caught it. This is that job done by a script instead.

    python tools/cooling_sync.py --check     what is out of date (exit 1 if any)
    python tools/cooling_sync.py --write     bring it all in line

Pages carry markers around the text this owns:

    <!--cooling:sentence-->…anything…<!--/cooling-->

The text between them is replaced wholesale, so switching COOLING_OFF_SCHEME
and running --write updates every page at once. Nothing is fetched at runtime:
a contract should read the same offline, and a terms page whose clause depends
on a live API is a terms page that can render blank.

Run --check in CI and the drift that caused this cannot happen twice.
"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# The scheme table is plain data with no Django imports, so it can be read
# without booting the app — which keeps this usable in a bare CI step.
_COOLING = os.path.join(ROOT, 'backend', 'apps', 'bookings', 'cooling.py')
_ns = {}
_src = io.open(_COOLING, encoding='utf-8').read()
_src = _src.replace('from django.conf import settings', 'settings = None')
exec(compile(_src, _COOLING, 'exec'), _ns)          # noqa: S102 — our own file
SCHEMES = _ns['SCHEMES']
DEFAULT_SCHEME = _ns['DEFAULT_SCHEME']

FRONTEND = os.path.join(ROOT, 'frontend')

MARKER = re.compile(
    r'(<!--cooling:(?P<key>[a-z_]+)-->)(?P<body>.*?)(<!--/cooling-->)',
    re.DOTALL,
)


def scheme_name():
    """Whatever the backend would use, without importing Django settings."""
    return os.environ.get('COOLING_OFF_SCHEME') or DEFAULT_SCHEME


def render(key, lang, scheme):
    text = SCHEMES[scheme]['text'][lang]
    if key == 'rows':
        return ''.join('<li><strong>%s</strong>: %s</li>' % row for row in text['rows'])
    if key not in text:
        raise KeyError('No such cooling key: %s' % key)
    return text[key]


def page_lang(name):
    return 'ru' if name.endswith('_ru.html') else 'en'


def process(path, scheme, write):
    name = os.path.basename(path)
    lang = page_lang(name)
    original = io.open(path, encoding='utf-8', newline='').read()

    stale = []

    def repl(m):
        want = render(m.group('key'), lang, scheme)
        if m.group('body') != want:
            stale.append(m.group('key'))
        return m.group(1) + want + m.group(4)

    updated = MARKER.sub(repl, original)
    if stale and write:
        io.open(path, 'w', encoding='utf-8', newline='').write(updated)
    return stale


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true', help='report drift, change nothing')
    ap.add_argument('--write', action='store_true', help='rewrite the marked regions')
    args = ap.parse_args()
    if not (args.check or args.write):
        ap.error('pass --check or --write')

    scheme = scheme_name()
    if scheme not in SCHEMES:
        sys.exit('Unknown COOLING_OFF_SCHEME %r. Known: %s'
                 % (scheme, ', '.join(sorted(SCHEMES))))
    print('scheme: %s' % scheme)

    pages = sorted(f for f in os.listdir(FRONTEND) if f.endswith('.html'))
    touched = marked = 0
    for name in pages:
        path = os.path.join(FRONTEND, name)
        if '<!--cooling:' not in io.open(path, encoding='utf-8', newline='').read():
            continue
        marked += 1
        stale = process(path, scheme, args.write)
        if stale:
            touched += 1
            print('  %-28s %s  [%s]' % (name, 'updated' if args.write else 'STALE',
                                        ', '.join(sorted(set(stale)))))

    if not marked:
        sys.exit('No page carries a <!--cooling:...--> marker. Nothing to keep in step.')

    print('%d marked page(s), %d %s'
          % (marked, touched, 'updated' if args.write else 'out of date'))
    if args.check and touched:
        sys.exit(1)


if __name__ == '__main__':
    main()
