"""Integration tests: jalankan setelah docker compose up dan init_db.py."""

import unittest
from unittest.mock import patch

import psycopg

from app import app
from chatbot import ChatbotError, interpret_inventory_request
from init_db import init_db


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_seed_is_repeatable(self):
        inserted, total = init_db()
        self.assertEqual(inserted, 0)
        self.assertGreaterEqual(total, 20)

    def test_greeting_does_not_wait_for_ollama_or_database(self):
        with patch('app.interpret_inventory_request') as interpret, patch('inventory.connect_db') as connect:
            for text in ('halo', 'Halo!', 'hai bot', 'Selamat pagi'):
                response = self.client.post('/chat', json={'message': text})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['source'], 'greeting')
            interpret.assert_not_called()
            connect.assert_not_called()

    def test_search_and_detail(self):
        result = self.client.get('/api/items?q=KEYBOARD').json
        self.assertEqual(result['total'], 2)
        self.assertEqual(self.client.get('/api/items/GDG-001').json['item']['sku'], 'GDG-001')
        self.assertEqual(self.client.get('/api/items/unknown').status_code, 404)

    def test_pagination(self):
        first = self.client.get('/api/items?limit=2&offset=0').json
        second = self.client.get('/api/items?limit=2&offset=2').json
        self.assertEqual(len(first['items']), 2)
        self.assertNotEqual(first['items'][0]['sku'], second['items'][0]['sku'])

    def test_sql_input_is_data(self):
        response = self.client.get('/api/items', query_string={'q': "'; DROP TABLE items; --"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['total'], 0)
        self.assertEqual(self.client.get('/health/db').status_code, 200)

    def test_validation(self):
        for path in ('/api/items?limit=0', '/api/items?offset=-1', '/api/items?limit=abc'):
            self.assertEqual(self.client.get(path).status_code, 400)
        for data in ({}, {'message': ''}, {'message': 42}):
            self.assertEqual(self.client.post('/chat', json=data).status_code, 400)

    def test_database_unavailable(self):
        with patch('inventory.connect_db', side_effect=psycopg.OperationalError('private detail')):
            response = self.client.get('/api/items')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private detail', str(response.json))

    def test_stock_answer_matches_database_and_out_of_stock(self):
        for sku in ('GDG-001', 'GDG-004'):
            item = self.client.get(f'/api/items/{sku}').json['item']
            intent = {'action': 'search', 'query': sku, 'interpreter': 'test'}
            with patch('app.interpret_inventory_request', return_value=intent):
                response = self.client.post('/chat', json={'message': f'Stok {sku} berapa?'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['items'][0], item)
            expected = f"{item['stock']} {item['unit']}" if item['stock'] else 'habis (0)'
            self.assertIn(expected, response.json['reply'])

    def test_unknown_product(self):
        intent = {'action': 'search', 'query': 'unicorn', 'interpreter': 'test'}
        with patch('app.interpret_inventory_request', return_value=intent):
            result = self.client.post('/chat', json={'message': 'Ada unicorn?'}).json
        self.assertEqual(result['total'], 0)
        self.assertIn('tidak ditemukan', result['reply'])

    def test_ollama_failure_uses_keyword_fallback(self):
        with patch('chatbot.generate_reply', side_effect=ChatbotError('offline')):
            intent = interpret_inventory_request('Berapa stok keyboard?')
        self.assertEqual(intent['query'], 'keyboard')
        self.assertEqual(intent['interpreter'], 'keyword_fallback')


if __name__ == '__main__':
    unittest.main()
