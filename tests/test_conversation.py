import unittest
import uuid
from unittest.mock import patch

from app import app
from database import connect_db


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.session = 'test:' + uuid.uuid4().hex
        self.other = 'test:' + uuid.uuid4().hex

    def tearDown(self):
        with connect_db() as conn:
            conn.execute('DELETE FROM chat_sessions WHERE session_id IN (%s, %s)',
                         (self.session, self.other))

    def send(self, text, session=None):
        response = self.client.post('/chat', json={
            'message': text, 'session_id': session or self.session})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def test_introduction_is_private_and_resettable(self):
        self.assertIn('Budi', self.send('Halo, namaku Budi')['reply'])
        self.assertIn('Budi', self.send('halo')['reply'])
        self.assertNotIn('Budi', self.send('halo', self.other)['reply'])
        self.send('/reset')
        self.assertNotIn('Budi', self.send('halo')['reply'])

    def test_followup_reads_live_stock(self):
        intent = {'action': 'search', 'query': 'keyboard', 'interpreter': 'test'}
        with patch('app.interpret_inventory_request', return_value=intent):
            result = self.send('Ada keyboard?')
        self.assertEqual(result['total'], 2)
        self.assertIn('lebih suka', result['reply'])
        result = self.send('yang putih')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['sku'], 'GDG-002')
        with connect_db() as conn:
            actual = conn.execute("SELECT stock FROM items WHERE sku = 'GDG-002'").fetchone()['stock']
        self.assertEqual(result['items'][0]['stock'], actual)
        self.assertEqual(self.send('berapa harganya')['items'][0]['sku'], 'GDG-002')
        self.assertEqual(self.send('1')['items'][0]['sku'], 'GDG-002')

    def test_reference_without_context_and_miss(self):
        self.assertIn('Barang yang mana', self.send('yang putih')['reply'])
        self.assertIn('belum tersedia', self.send('999')['reply'])
        self.assertIn('Sama-sama', self.send('terima kasih')['reply'])

    def test_categories_and_session_validation(self):
        self.assertIn('Aksesoris', self.send('Lihat kategori')['reply'])
        for value in ('', 123, 'a' * 121):
            self.assertEqual(self.client.post('/chat', json={
                'message': 'halo', 'session_id': value}).status_code, 400)

    def test_discovery_uses_history_and_explicit_budget(self):
        ask = {'action': 'ask', 'question': 'Keyboardnya untuk kerja atau gaming?',
               'query': 'keyboard', 'max_price_idr': 0}
        find = {'action': 'search', 'question': '', 'query': 'keyboard', 'max_price_idr': 300000}
        with patch('conversation.plan_conversation', side_effect=[ask, find]) as planner:
            first = self.send('Aku cari keyboard')
            self.assertEqual(first['source'], 'discovery')
            second = self.send('Buat kerja, budget 300 ribu')
        history = planner.call_args_list[1].args[1]
        self.assertTrue(any('kerja atau gaming' in turn['content'] for turn in history))
        self.assertEqual(second['total'], 1)
        self.assertEqual(second['items'][0]['sku'], 'GDG-002')
        self.assertLessEqual(second['items'][0]['price_idr'], 300000)

    def test_direct_stock_request_does_not_ask_discovery(self):
        intent = {'action': 'search', 'query': 'keyboard', 'interpreter': 'test'}
        with patch('app.interpret_inventory_request', return_value=intent), patch('conversation.plan_conversation') as plan:
            self.assertEqual(self.send('Berapa stok keyboard?')['total'], 2)
        plan.assert_not_called()

    def test_discovery_offline_falls_back_to_search(self):
        intent = {'action': 'search', 'query': 'keyboard', 'interpreter': 'test'}
        with patch('conversation.plan_conversation', return_value=None), patch('app.interpret_inventory_request', return_value=intent):
            self.assertEqual(self.send('Cari keyboard')['total'], 2)

    def test_catalog_question_is_answered_before_asking_preferences(self):
        questions = [
            'aku ingin bertanya terkait barang yang kamu jual, barang seperti apa?',
            'Di sini jualan apa?', 'Ada barang apa aja?', 'Apa saja yang kamu jual?',
        ]
        with patch('conversation.plan_conversation') as plan, patch('app.interpret_inventory_request') as interpret:
            for question in questions:
                result = self.send(question)
                self.assertEqual(result['source'], 'catalog')
                self.assertIn('Keyboard Mechanical Hitam', result['reply'])
                self.assertIn('Monitor', result['reply'])
                self.assertNotIn('Apakah kamu mencari', result['reply'])
        plan.assert_not_called()
        interpret.assert_not_called()

    def test_model_can_route_unfamiliar_catalog_wording(self):
        output = {'action': 'overview', 'question': '', 'query': '', 'max_price_idr': 0}
        with patch('conversation.plan_conversation', return_value=output):
            result = self.send('Boleh kenalan dulu sama koleksi tokonya?')
        self.assertEqual(result['source'], 'catalog')
