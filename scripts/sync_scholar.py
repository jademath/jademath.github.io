#!/usr/bin/env python3
"""Refresh a complete public Scholar profile without replacing good data on failure."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

PROFILE_ID = 'Qv2IRBkAAAAJ'
PROFILE_URL = 'https://scholar.google.com/citations?user=' + PROFILE_ID + '&hl=en'
FETCH_URL = PROFILE_URL + '&pagesize=100'
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '_data/scholar_publications.json'
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

class InvalidProfile(ValueError):
    pass

class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or []), []
    def has_class(self, name):
        return name in self.attrs.get('class', '').split()
    def find_all(self, predicate):
        found = [self] if predicate(self) else []
        for child in self.children:
            if isinstance(child, Node):
                found.extend(child.find_all(predicate))
        return found
    def text(self, omit_classes=()):
        if any(self.has_class(x) for x in omit_classes):
            return ''
        return ''.join(c.text(omit_classes) if isinstance(c, Node) else c for c in self.children)

class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('root')
        self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        self.stack[-1].children.append(data)

def clean(text):
    text = unicodedata.normalize('NFC', text)
    text = re.sub('[\u200e\u200f\u202a-\u202e\ufeff]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def only(nodes, description):
    if len(nodes) != 1:
        raise InvalidProfile('Missing or ambiguous ' + description)
    return nodes[0]

def parse_profile(html):
    document = Document()
    document.feed(html)
    root = document.root
    name = only(root.find_all(lambda n: n.attrs.get('id') == 'gsc_prf_in'), 'profile name')
    if clean(name.text()) != 'Yuliang Wang':
        raise InvalidProfile('Scholar profile identity does not match Yuliang Wang')
    more = only(root.find_all(lambda n: n.attrs.get('id') == 'gsc_bpf_more'), 'pagination control')
    if 'disabled' not in more.attrs:
        raise InvalidProfile('Scholar returned an incomplete list; existing publications were preserved')
    rows = root.find_all(lambda n: n.tag == 'tr' and n.has_class('gsc_a_tr'))
    if not rows:
        raise InvalidProfile('No publications returned; existing publications were preserved')
    publications, seen = [], set()
    for row in rows:
        title_node = only(row.find_all(lambda n: n.tag == 'a' and n.has_class('gsc_a_at')), 'article title')
        href = title_node.attrs.get('href', '')
        parsed = urlparse(href)
        if parsed.netloc not in ('', 'scholar.google.com') or parsed.path != '/citations':
            raise InvalidProfile('Unexpected article link')
        params = parse_qs(parsed.query)
        article_id = params.get('citation_for_view', [''])[0]
        if not re.fullmatch(re.escape(PROFILE_ID) + r':[A-Za-z0-9_-]+', article_id):
            raise InvalidProfile('Article does not belong to the requested Scholar profile')
        if article_id in seen:
            raise InvalidProfile('Duplicate Scholar article ID')
        seen.add(article_id)
        details = row.find_all(lambda n: n.has_class('gs_gray'))
        if len(details) != 2:
            raise InvalidProfile('Article author/venue fields changed')
        title, authors = clean(title_node.text()), clean(details[0].text())
        venue = clean(details[1].text(omit_classes=('gs_oph',)))
        year_node = only(row.find_all(lambda n: n.has_class('gsc_a_y')), 'article year')
        year_text = clean(year_node.text())
        if year_text and not re.fullmatch(r'\d{4}', year_text):
            raise InvalidProfile('Invalid publication year')
        year = int(year_text) if year_text else 0
        if year and not 1800 <= year <= datetime.now(timezone.utc).year + 2:
            raise InvalidProfile('Publication year outside expected range')
        if not title or not authors or len(title) > 2000 or len(authors) > 4000 or len(venue) > 2000:
            raise InvalidProfile('Incomplete or invalid publication metadata')
        kind = 'Preprint' if 'arxiv' in venue.lower() else ('Thesis' if 'thesis' in venue.lower() else '')
        source = 'https://scholar.google.com/citations?' + urlencode({'view_op': 'view_citation', 'hl': 'en', 'user': PROFILE_ID, 'citation_for_view': article_id})
        publications.append({'id': article_id, 'title': title, 'authors': authors, 'venue': venue, 'year': year, 'kind': kind, 'scholar_url': source})
    publications.sort(key=lambda p: (-p['year'], p['title'].casefold(), p['id']))
    return publications

def make_snapshot(publications, previous=None, checked_at=None):
    if previous and previous.get('profile_id') != PROFILE_ID:
        raise InvalidProfile('Existing data belongs to a different Scholar profile')
    old = (previous or {}).get('publications', [])
    if old and len(publications) < len(old) * 0.8:
        raise InvalidProfile('More than 20% of entries disappeared; existing publications were preserved for review')
    now = checked_at or datetime.now(timezone.utc)
    checked = now.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    changed = not previous or old != publications
    return {'profile_id': PROFILE_ID, 'profile_url': PROFILE_URL, 'author': 'Yuliang Wang', 'checked_on': checked, 'updated_on': checked if changed else previous['updated_on'], 'publications': publications}

def refresh(output=OUTPUT, html=None):
    # Only one public-profile request. No pagination, proxies, or CAPTCHA bypass.
    if html is None:
        request = Request(FETCH_URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; ScholarPublicationSync/1.0; +https://jademath.github.io/publications/)', 'Accept-Language': 'en-US,en;q=0.9'})
        with urlopen(request, timeout=30) as response:
            if response.status != 200 or urlparse(response.url).netloc != 'scholar.google.com':
                raise InvalidProfile('Unexpected Scholar response')
            payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise InvalidProfile('Scholar response exceeded expected size')
            html = payload.decode('utf-8')
    publications = parse_profile(html)
    previous = json.loads(output.read_text()) if output.exists() else None
    snapshot = make_snapshot(publications, previous)
    encoded = json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.read_text() != encoded:
        temporary = output.with_suffix('.json.tmp')
        temporary.write_text(encoded)
        temporary.replace(output)
    print(f"Verified {len(publications)} publications; checked {snapshot['checked_on']}")
    return snapshot

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, help='Use an already downloaded profile for an initial import or offline validation')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        refresh(args.output, args.html.read_text() if args.html else None)
    except Exception as error:
        print(f'Scholar update failed; the saved publication list was not changed: {error}', file=sys.stderr)
        sys.exit(1)
