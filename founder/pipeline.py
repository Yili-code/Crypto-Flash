"""Daily research pipeline. Standard library only; credentials are environment-only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

TAIPEI = timezone(timedelta(hours=8))
TOPICS = {
    '工作流程': ('workflow', 'automat', 'productivity', 'spreadsheet', 'email'),
    '開發工具': ('developer', 'code', 'debug', 'api', 'programming', 'github'),
    'AI 應用': (' ai ', 'llm', 'agent', 'model', 'gpt'),
    '客戶與營運': ('customer', 'business', 'invoice', 'sales', 'marketing', 'saas'),
    '生活與學習': ('learn', 'education', 'health', 'travel', 'family', 'student'),
}


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))).strip()


def topic(title):
    value = ' ' + title.lower() + ' '
    return max(TOPICS, key=lambda t: sum(w in value for w in TOPICS[t])) if any(
        w in value for words in TOPICS.values() for w in words) else '其他探索'


def request(url, data=None, token=None, raw=False):
    headers = {'User-Agent': 'FounderMorning/0.1 (personal research)', 'Accept': 'application/json, application/atom+xml'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    payload = None
    if data is not None:
        payload = json.dumps(data, ensure_ascii=False).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=100 if '/analyze' in url else 25) as response:
        content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError('Response too large')
        return content if raw else json.loads(content)


def signal(source, identity, title, url, excerpt='', published=None, author=None):
    return {'id': source + ':' + str(identity), 'source': source, 'title': clean(title)[:500],
            'url': url, 'excerpt': clean(excerpt)[:3500], 'topic': topic(title + ' ' + clean(excerpt)[:500]),
            'published': published, 'author': author, 'fetched': datetime.now(timezone.utc).isoformat()}


def hn(kind):
    base = 'https://hacker-news.firebaseio.com/v0/'
    ids = request(base + kind + 'stories.json')[:10]

    def item(identity):
        entry = request(base + f'item/{identity}.json')
        if not entry or entry.get('deleted') or entry.get('dead'):
            return None
        url = f'https://news.ycombinator.com/item?id={identity}'
        s = signal('HN', identity, entry.get('title', ''), url, entry.get('text', ''),
                   datetime.fromtimestamp(entry['time'], timezone.utc).isoformat(), entry.get('by'))
        s['category'] = kind
        s['discussion_ids'] = entry.get('kids', [])[:3]
        s['product_url'] = entry.get('url')
        return s

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [s for s in pool.map(item, ids) if s]


def dev():
    entries = request('https://dev.to/api/articles?per_page=15&top=3')
    return [signal('DEV', e['id'], e['title'], e['url'], e.get('description'),
                   e.get('published_at'), e.get('user', {}).get('name')) for e in entries]


def producthunt():
    root = ET.fromstring(request('https://www.producthunt.com/feed', raw=True))
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    output = []
    for e in root.findall('a:entry', ns)[:20]:
        link = next((x.attrib['href'] for x in e.findall('a:link', ns)
                     if x.attrib.get('rel', 'alternate') == 'alternate'), '')
        if not link.startswith('https://'):
            continue
        output.append(signal('Product Hunt', hashlib.sha256(link.encode()).hexdigest()[:16],
                             e.findtext('a:title', '', ns), link, e.findtext('a:content', '', ns),
                             e.findtext('a:published', None, ns) or e.findtext('a:updated', None, ns),
                             e.findtext('a:author/a:name', None, ns)))
    return output


def select(candidates, context, date):
    seen = {s['id'] for issue in context.get('issues', []) for s in issue['signals']}
    weights = {}
    for f in context.get('feedback', []):
        weights[f['topic']] = weights.get(f['topic'], 0) + {'interested': 1, 'research': 2, 'skip': -1}.get(f['reaction'], 0)
    unique = {}
    for s in candidates:
        if s['id'] in seen:
            continue
        if s.get('published'):
            try:
                if datetime.fromisoformat(s['published'].replace('Z', '+00:00')).date() < date - timedelta(days=7):
                    continue
            except ValueError:
                continue
        key = re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', s['title'].lower())
        unique.setdefault(key, s)
    values = list(unique.values())
    # Stable daily shuffle breaks permanent source/order bias without rewarding popularity.
    values.sort(key=lambda s: (min(4, max(-4, weights.get(s['topic'], 0))),
                              hashlib.sha256((date.isoformat()+s['id']).encode()).hexdigest()), reverse=True)
    chosen = []
    for s in values:
        if len(chosen) == 2:
            break
        if not chosen or s['source'] != chosen[0]['source']:
            chosen.append(s)
    remaining = [s for s in values if s not in chosen]
    if remaining:
        unfamiliar = min(remaining, key=lambda s: (weights.get(s['topic'], 0), s['topic'] in {c['topic'] for c in chosen}))
        unfamiliar['exploration'] = True
        chosen.append(unfamiliar)
    return chosen


def weekly(context):
    feedback = context.get('feedback', [])
    interested = [f for f in feedback if f['reaction'] in ('research', 'interested') or f['saved']]
    pool = [s for issue in context.get('issues', []) for s in issue['signals']]
    if not pool:
        return []
    focus = interested[0]['topic'] if interested else pool[0]['topic']
    chosen = []
    for s in pool:
        if s['topic'] == focus and s['id'] not in {c['id'] for c in chosen}:
            chosen.append(dict(s))
    return chosen[:3]


def enrich(signals):
    for s in signals:
        quotes = []
        for identity in s.pop('discussion_ids', []):
            try:
                c = request(f'https://hacker-news.firebaseio.com/v0/item/{identity}.json')
                if c and not c.get('deleted') and not c.get('dead'):
                    quotes.append({'text': clean(c.get('text', ''))[:1000], 'author': c.get('by'),
                                   'url': f'https://news.ycombinator.com/item?id={identity}'})
            except (OSError, ValueError):
                continue
        if quotes:
            s['comments'] = quotes


def run(args):
    target = os.environ.get('FOUNDER_URL', '').rstrip('/')
    token = os.environ.get('FOUNDER_JOB_TOKEN', '')
    if not args.local_output and (not target.startswith('https://') or not token):
        raise SystemExit('Set FOUNDER_URL (https) and FOUNDER_JOB_TOKEN, or use --local-output.')
    context = request(target + '/internal/context', token=token) if target and token else {'issues': [], 'feedback': []}
    date = datetime.now(TAIPEI).date()
    existing = next((i for i in context['issues'] if i['date'] == date.isoformat()), None)
    if existing and not args.local_output:
        print('Existing issue; checking delivery only.')
        if args.send:
            print(request(target + '/internal/deliver', {'date': date.isoformat()}, token))
        return
    candidates, sources = [], []
    for name, fetcher in [('HN Ask', lambda: hn('ask')), ('HN Show', lambda: hn('show')),
                          ('Product Hunt', producthunt), ('DEV', dev)]:
        try:
            entries = fetcher()
            candidates.extend(entries)
            sources.append({'name': name, 'ok': True, 'count': len(entries)})
        except (OSError, ValueError, KeyError, ET.ParseError):
            sources.append({'name': name, 'ok': False, 'count': 0})
    if not any(s['ok'] for s in sources):
        raise SystemExit('All sources unavailable; no issue saved. A later run can recover.')
    is_weekly = date.weekday() == 6 or args.weekly
    chosen = weekly(context) if is_weekly else []
    if not chosen:
        chosen = select(candidates, context, date)
    enrich(chosen)
    # Previously generated weekly cards must never be presented as a fresh successful analysis.
    for s in chosen:
        s.pop('analysis', None)
    issue = {'date': date.isoformat(), 'kind': 'weekly' if is_weekly else 'daily',
             'headline': '從一個問題，找到下一個值得驗證的假設。' if is_weekly else '今天，從三個線索開始。',
             'signals': chosen, 'sources': sources, 'status': 'source_only',
             'created': datetime.now(timezone.utc).isoformat()}
    if chosen and target and token:
        try:
            result = request(target + '/internal/analyze', {'signals': chosen, 'kind': issue['kind']}, token)
            cards = {c['id']: c for c in result['cards']}
            for s in chosen:
                s['analysis'] = cards[s['id']]
            issue['status'] = 'analyzed'
        except (OSError, ValueError, KeyError):
            print('AI unavailable or invalid; preserving sources without fabricated analysis.')
    if not chosen:
        issue['status'] = 'empty'
        issue['headline'] = '今天沒有足夠的新線索，回顧收藏也是進展。'
    if args.local_output:
        output = Path(args.local_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(issue, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        request(target + '/internal/issues', issue, token)
        if args.send:
            print(request(target + '/internal/deliver', {'date': date.isoformat()}, token))
    print(f"Prepared {issue['kind']} issue: {len(chosen)} signals, {issue['status']}; sources: {sources}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-output', help='Write a private local preview; does not publish or send')
    parser.add_argument('--send', action='store_true', help='Send the prepared issue to the configured Telegram chat')
    parser.add_argument('--weekly', action='store_true', help='Generate a weekly report for testing')
    run(parser.parse_args())
