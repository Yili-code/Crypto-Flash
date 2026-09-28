import importlib.util
from datetime import date
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('pipeline', Path(__file__).parents[1] / 'pipeline.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PipelineTests(unittest.TestCase):
    def test_selection_removes_seen_duplicate_and_stale(self):
        a = p.signal('HN', 1, 'Automate invoices', 'https://example.com', published='2026-09-21T00:00:00Z')
        b = p.signal('DEV', 2, 'Automate invoices!', 'https://example.org', published='2026-09-21T00:00:00Z')
        c = p.signal('HN', 3, 'Old item', 'https://example.net', published='2020-01-01T00:00:00Z')
        d = p.signal('DEV', 4, 'New customer problem', 'https://example.com/new')
        context = {'issues': [{'signals': [d]}], 'feedback': []}
        selected = p.select([a, b, c, d], context, date(2026, 9, 21))
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['id'], a['id'])

    def test_preferences_keep_unfamiliar_slot(self):
        items = [p.signal('HN', 1, 'Workflow one', 'https://example.com/a'),
                 p.signal('DEV', 2, 'Workflow two', 'https://example.com/b'),
                 p.signal('Product Hunt', 3, 'Education student', 'https://example.com/c')]
        result = p.select(items, {'feedback': [{'topic': '工作流程', 'reaction': 'research'}]}, date(2026, 9, 21))
        self.assertEqual(len(result), 3)
        self.assertEqual(result[2]['topic'], '生活與學習')
        self.assertTrue(result[2]['exploration'])

    def test_weekly_follows_interest_and_deduplicates(self):
        a = p.signal('HN', 1, 'Education', 'https://example.com/a')
        b = p.signal('DEV', 2, 'Workflow', 'https://example.com/b')
        chosen = p.weekly({'issues': [{'signals': [a, b, a]}], 'feedback': [
            {'topic': a['topic'], 'reaction': 'research', 'saved': 1}]})
        self.assertEqual([s['id'] for s in chosen], [a['id']])


if __name__ == '__main__':
    unittest.main()
