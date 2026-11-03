import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import requests

from telegram_bot import TelegramBot, TelegramError


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.bot = TelegramBot('fake-secret', 'http://localhost:5000', 'unused.txt')
        self.bot.call = Mock()
        self.bot.get_reply = Mock(return_value='Stok 29 unit')
        self.bot.typing = Mock(side_effect=lambda chat_id: nullcontext())

    def update(self, text='Stok keyboard?'):
        return {'update_id': 1, 'message': {'chat': {'id': 7, 'type': 'private'},
                'from': {'id': 7}, 'text': text}}

    def test_message_to_flask_and_back(self):
        self.bot.handle_update(self.update())
        self.bot.get_reply.assert_called_once_with('Stok keyboard?', session_id='telegram:7')
        self.assertEqual(self.bot.call.call_args.args[0], 'sendMessage')
        self.assertEqual(self.bot.call.call_args.args[1]['text'], 'Stok 29 unit')
        self.assertEqual(self.bot.call.call_args.args[1]['reply_markup'], {'remove_keyboard': True})
        self.bot.typing.assert_called_once_with(7)

    def test_help_does_not_call_model(self):
        self.bot.handle_update(self.update('/start'))
        self.bot.get_reply.assert_not_called()
        self.bot.call.assert_called_once()

    def test_access_and_group_filter(self):
        self.bot.allowed_users = {42}
        self.bot.handle_update(self.update())
        self.bot.call.assert_not_called()
        self.bot.allowed_users.clear()
        update = self.update()
        update['message']['chat']['type'] = 'group'
        self.bot.handle_update(update)
        self.bot.call.assert_not_called()

    def test_flask_failure_has_friendly_reply(self):
        bot = TelegramBot('secret', 'http://localhost:5000', 'unused.txt')
        bot.session = Mock()
        bot.session.post.side_effect = requests.ConnectionError('private detail')
        self.assertIn('belum bisa diakses', bot.get_reply('keyboard'))
        with self.assertRaises(TelegramError) as error:
            bot.call('getMe')
        self.assertNotIn('private detail', str(error.exception))

    def test_offset_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            self.bot.state_file = Path(folder) / 'state' / 'offset.txt'
            self.bot.save_offset(43)
            self.assertEqual(self.bot.state_file.read_text(), '43')


if __name__ == '__main__':
    unittest.main()
