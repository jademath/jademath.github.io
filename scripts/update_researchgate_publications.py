#!/usr/bin/env python3
"""Validate a source-reviewed ResearchGate snapshot before replacing website data.

The weekly Codex task gathers public bibliographic evidence. This script does not
scrape ResearchGate or claim that syntactic validation verifies a DOI's metadata.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlparse

PROFILE_URL = 'https://www.researchgate.net/profile/Yuliang-Wang-19/research'
OUTPUT = Path(__file__).resolve().parents[1] / '_data/researchgate_publications.json'

class InvalidSnapshot(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise InvalidSnapshot(message)

def clean(value):
    require(isinstance(value, str), 'Expected text metadata')
    value = ' '.join(unicodedata.normalize('NFC', value).split())
    require(0 < len(value) <= 2000, 'Empty or oversized metadata')
    return value

def valid_url(value):
    require(isinstance(value, str), 'Expected a URL')
    parsed = urlparse(value)
    require(parsed.scheme == 'https' and parsed.netloc and not parsed.username
            and not parsed.password and not any(c.isspace() for c in value), 'Invalid HTTPS URL')
    return parsed

def validate(candidate, previous=None):
    require(candidate.get('profile_url') == PROFILE_URL and candidate.get('author') == 'Yuliang Wang', 'Wrong ResearchGate profile')
    require(candidate.get('source_complete') is True, 'Incomplete source profile')
    entries = candidate.get('publications')
    count = candidate.get('profile_count')
    require(isinstance(entries, list) and entries and type(count) is int and count == len(entries), 'Publication count does not match the complete profile')
    publications, ids, links = [], set(), set()
    for entry in entries:
        rg_url = clean(entry['researchgate_url'])
        rg = valid_url(rg_url)
        match = re.fullmatch(r'/publication/(\d+)(?:_[^/?#]+)?/?', rg.path)
        require(rg.netloc == 'www.researchgate.net' and match and not rg.query and not rg.fragment, 'Invalid ResearchGate article URL')
        identifier = match.group(1)
        require(identifier not in ids, 'Duplicate ResearchGate article')
        ids.add(identifier)
        authors = entry['authors']
        require(isinstance(authors, list) and authors, 'Missing authors')
        authors = [clean(author) for author in authors]
        require('Yuliang Wang' in authors or 'Y Wang' in authors, 'Profile author is missing from author list')
        require(not any('...' in author or '…' in author or '[' in author for author in authors), 'Truncated author list')
        year = entry['year']
        require(type(year) is int and 1800 <= year <= datetime.now(timezone.utc).year + 2, 'Invalid publication year')
        kind = entry.get('kind', 'Article')
        require(kind in ('Article', 'Preprint'), 'Unknown publication type')
        article_url = clean(entry['article_url'])
        article = valid_url(article_url)
        require(not article.query and not article.fragment, 'Article link must be canonical')
        if kind == 'Preprint':
            require(article.netloc == 'arxiv.org' and re.fullmatch(r'/abs/(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?', article.path), 'Preprint must link to an arXiv abstract page')
        else:
            require(article.netloc == 'doi.org' and re.fullmatch(r'/10\.\d{4,9}/\S+', article.path), 'Journal article must link to its DOI')
        require(article_url.casefold() not in links, 'Duplicate DOI or arXiv link')
        links.add(article_url.casefold())
        sources = entry.get('sources')
        require(isinstance(sources, list) and sources, 'Missing bibliographic evidence URLs')
        for source in sources:
            valid_url(source)
        publications.append({'id': identifier, 'title': clean(entry['title']), 'authors': authors,
                             'venue': clean(entry['venue']), 'year': year, 'kind': kind,
                             'researchgate_url': rg_url, 'article_url': article_url,
                             'sources': sorted(set(sources))})
    publications.sort(key=lambda p: (-p['year'], p['title'].casefold(), p['id']))
    if previous:
        require(previous.get('profile_url') == PROFILE_URL, 'Existing snapshot has a different source')
        old_ids = {p['id'] for p in previous['publications']}
        removed = old_ids - ids
        require(len(removed) <= len(old_ids) * 0.2, 'More than 20% of prior publications disappeared; preserve the existing list for review')
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    changed = not previous or previous['publications'] != publications
    return {'profile_url': PROFILE_URL, 'author': 'Yuliang Wang', 'source_complete': True,
            'profile_count': count, 'checked_on': today,
            'updated_on': today if changed else previous['updated_on'], 'publications': publications}

def update(candidate, output=OUTPUT):
    previous = json.loads(output.read_text(encoding='utf-8')) if output.exists() else None
    result = validate(candidate, previous)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.read_text(encoding='utf-8') != encoded:
        temporary = output.with_suffix('.json.tmp')
        temporary.write_text(encoded, encoding='utf-8')
        temporary.replace(output)
    print(f"Validated {len(result['publications'])} ResearchGate publications")
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path, help='Complete snapshot reviewed against public ResearchGate and DOI/arXiv sources')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    try:
        update(json.loads(args.input.read_text(encoding='utf-8')), args.output)
    except Exception as error:
        print(f'Publication update stopped; the saved list was not changed: {error}', file=sys.stderr)
        sys.exit(1)
