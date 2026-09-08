import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

spec = importlib.util.spec_from_file_location('sync_scholar', Path(__file__).parents[1] / 'scripts/sync_scholar.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

def row(article='paper1', year='2025', title='A &amp; B', author='Y Wang, E Blåsten', venue='Journal 10 (2), 12–20'):
    return f'''<tr class="gsc_a_tr"><td><a class="gsc_a_at" href="/citations?view_op=view_citation&amp;citation_for_view={sync.PROFILE_ID}:{article}">{title}</a><div class="gs_gray">{author}</div><div class="gs_gray">{venue}<span class="gs_oph">, {year}</span></div></td><td class="gsc_a_y"><span>{year}</span></td></tr>'''

def profile(rows, complete=True, name='Yuliang Wang'):
    disabled = ' disabled' if complete else ''
    return f'<div id="gsc_prf_in">{name}</div><table>{rows}</table><button id="gsc_bpf_more"{disabled}>Show more</button>'

class ScholarSyncTests(unittest.TestCase):
    def test_metadata_and_newest_first(self):
        data = sync.parse_profile(profile(row('old', '2013') + row('new', '2026', venue='arXiv preprint arXiv:2601.00001')))
        self.assertEqual([p['year'] for p in data], [2026, 2013])
        self.assertEqual(data[0]['title'], 'A & B')
        self.assertEqual(data[0]['authors'], 'Y Wang, E Blåsten')
        self.assertEqual(data[0]['venue'], 'arXiv preprint arXiv:2601.00001')
        self.assertEqual(data[0]['kind'], 'Preprint')
        self.assertIn('citation_for_view=Qv2IRBkAAAAJ%3Anew', data[0]['scholar_url'])

    def test_absent_year_is_preserved(self):
        self.assertEqual(sync.parse_profile(profile(row(year='')))[0]['year'], 0)

    def test_challenge_or_wrong_profile_is_rejected(self):
        for html in ['<html>Please solve this CAPTCHA</html>', profile(row(), name='Another Person')]:
            with self.subTest(html=html), self.assertRaises(sync.InvalidProfile):
                sync.parse_profile(html)

    def test_empty_incomplete_or_duplicate_result_is_rejected(self):
        for html in [profile(''), profile(row(), complete=False), profile(row() + row())]:
            with self.subTest(html=html), self.assertRaises(sync.InvalidProfile):
                sync.parse_profile(html)

    def test_external_or_other_owner_link_is_rejected(self):
        for html in [profile(row()).replace('/citations?', 'https://example.com/citations?'), profile(row()).replace(sync.PROFILE_ID, 'AnotherUser')]:
            with self.subTest(html=html), self.assertRaises(sync.InvalidProfile):
                sync.parse_profile(html)

    def test_bad_year_or_missing_metadata_is_rejected(self):
        for html in [profile(row(year='soon')), profile(row(title='')), profile(row(author=''))]:
            with self.subTest(html=html), self.assertRaises(sync.InvalidProfile):
                sync.parse_profile(html)

    def test_large_loss_keeps_saved_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'publications.json'
            initial = profile(''.join(row(str(i)) for i in range(10)))
            sync.refresh(output, initial)
            original = output.read_bytes()
            with self.assertRaises(sync.InvalidProfile):
                sync.refresh(output, profile(row()))
            self.assertEqual(output.read_bytes(), original)

    def test_blocked_or_network_failure_keeps_saved_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'publications.json'
            sync.refresh(output, profile(row()))
            original = output.read_bytes()
            with self.assertRaises(sync.InvalidProfile):
                sync.refresh(output, '<html>Request blocked</html>')
            with patch.object(sync, 'urlopen', side_effect=URLError('unavailable')):
                with self.assertRaises(URLError):
                    sync.refresh(output)
            self.assertEqual(output.read_bytes(), original)

    def test_new_and_modified_publication_replaces_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'publications.json'
            sync.refresh(output, profile(row()))
            sync.refresh(output, profile(row(title='Updated title') + row('new', '2026')))
            result = json.loads(output.read_text())
            self.assertEqual(len(result['publications']), 2)
            self.assertEqual(result['publications'][1]['title'], 'Updated title')

if __name__ == '__main__':
    unittest.main()
