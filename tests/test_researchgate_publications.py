import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('update_rg', Path(__file__).parents[1] / 'scripts/update_researchgate_publications.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

def snapshot(count=1):
    return {'profile_url': sync.PROFILE_URL, 'author': 'Yuliang Wang', 'source_complete': True, 'profile_count': count,
            'publications': [{'title': f'Publication {i}', 'authors': ['Peijun Li', 'Yuliang Wang'], 'venue': 'Test Journal 1, 1–10',
                              'year': 2025, 'kind': 'Article', 'researchgate_url': f'https://www.researchgate.net/publication/{100+i}_Publication',
                              'article_url': f'https://doi.org/10.1234/article{i}', 'sources': [f'https://doi.org/10.1234/article{i}']} for i in range(count)]}

class ResearchGateTests(unittest.TestCase):
    def test_new_and_corrected_entries_are_saved_in_year_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.json'
            sync.update(snapshot(), path)
            candidate = snapshot(2)
            candidate['publications'][0]['title'] = 'Corrected title'
            candidate['publications'][1]['year'] = 2026
            sync.update(candidate, path)
            result = json.loads(path.read_text())
            self.assertEqual([p['year'] for p in result['publications']], [2026, 2025])
            self.assertEqual(result['publications'][1]['title'], 'Corrected title')

    def test_arxiv_preprint_and_unicode_authors(self):
        candidate = snapshot()
        paper = candidate['publications'][0]
        paper.update(kind='Preprint', article_url='https://arxiv.org/abs/2601.00427')
        paper['authors'].insert(0, 'Emilia Blåsten')
        self.assertEqual(sync.validate(candidate)['publications'][0]['authors'][0], 'Emilia Blåsten')

    def test_incomplete_or_wrong_profile_rejected(self):
        for key, value in [('profile_url', 'https://www.researchgate.net/profile/Other'), ('author', 'Other Wang'), ('source_complete', False), ('profile_count', 2)]:
            with self.subTest(key=key), self.assertRaises(sync.InvalidSnapshot):
                sync.validate(dict(snapshot(), **{key: value}))

    def test_invalid_article_targets_rejected(self):
        for url in ['javascript:alert(1)', 'https://doi.org.evil.test/10.1234/a', 'https://doi.org/invalid', 'https://arxiv.org/pdf/2601.00427']:
            candidate = snapshot()
            candidate['publications'][0]['article_url'] = url
            with self.subTest(url=url), self.assertRaises(sync.InvalidSnapshot):
                sync.validate(candidate)

    def test_duplicate_ids_or_dois_rejected(self):
        for key in ['researchgate_url', 'article_url']:
            candidate = snapshot(2)
            candidate['publications'][1][key] = candidate['publications'][0][key]
            with self.subTest(key=key), self.assertRaises(sync.InvalidSnapshot):
                sync.validate(candidate)

    def test_missing_or_truncated_authors_rejected(self):
        for authors in [[], ['Someone Else'], ['Yuliang Wang', '[...]']]:
            candidate = snapshot()
            candidate['publications'][0]['authors'] = authors
            with self.subTest(authors=authors), self.assertRaises(sync.InvalidSnapshot):
                sync.validate(candidate)

    def test_mass_removals_cannot_hide_behind_same_count(self):
        original = sync.validate(snapshot(10))
        candidate = snapshot(10)
        for i in range(3):
            candidate['publications'][i]['researchgate_url'] = f'https://www.researchgate.net/publication/{200+i}_New'
        with self.assertRaises(sync.InvalidSnapshot):
            sync.validate(candidate, original)

    def test_failed_review_preserves_last_good_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'data.json'
            sync.update(snapshot(), path)
            before = path.read_bytes()
            candidate = snapshot()
            candidate['publications'][0]['sources'] = []
            with self.assertRaises(sync.InvalidSnapshot):
                sync.update(candidate, path)
            self.assertEqual(before, path.read_bytes())

if __name__ == '__main__':
    unittest.main()
