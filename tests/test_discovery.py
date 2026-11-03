import json
import unittest
from unittest.mock import patch

from discovery import plan_conversation


class DiscoveryTests(unittest.TestCase):
    def test_overview_allows_empty_query(self):
        output = {'action': 'overview', 'question': '', 'query': '', 'max_price_idr': 0}
        with patch('discovery.generate_reply', return_value=json.dumps(output)):
            result = plan_conversation('Boleh tahu produknya?', [], [])
        self.assertEqual(result['action'], 'overview')

    def test_does_not_invent_product_variant(self):
        output = {'action': 'search', 'question': '',
                  'query': 'Keyboard Mechanical Hitam', 'max_price_idr': 300000}
        history = [{'role': 'user', 'content': 'Aku cari keyboard'}]
        with patch('discovery.generate_reply', return_value=json.dumps(output)):
            result = plan_conversation('Buat kerja, budget 300 ribu', history, [])
        self.assertEqual(result['query'], 'keyboard')

    def test_explicit_variant_is_preserved(self):
        output = {'action': 'search', 'question': '',
                  'query': 'keyboard wireless', 'max_price_idr': 0}
        with patch('discovery.generate_reply', return_value=json.dumps(output)):
            result = plan_conversation('Aku cari keyboard wireless', [], [])
        self.assertEqual(result['query'], 'keyboard wireless')
