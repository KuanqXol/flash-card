import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add local path to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app import app, sanitize_word, slugify

class TestTTS(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_sanitize_word(self):
        self.assertEqual(sanitize_word("hello!"), "hello")
        self.assertEqual(sanitize_word("don't"), "dont")
        self.assertEqual(sanitize_word("word-dash"), "word-dash")
        self.assertEqual(sanitize_word("word space"), "word space")
        self.assertEqual(sanitize_word(""), "")

    def test_slugify(self):
        self.assertEqual(slugify("Hello"), "hello")
        self.assertEqual(slugify("word space"), "word_space")
        self.assertEqual(slugify("word-dash"), "word-dash")

    def test_tts_invalid_word(self):
        response = self.app.get('/api/tts?word=!!!')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'Invalid or empty word', response.data)

    @patch('gtts.gTTS')
    def test_tts_generation_success(self, mock_gtts):
        # Mock gTTS save method to create a dummy file
        mock_instance = MagicMock()
        mock_gtts.return_value = mock_instance
        
        # When save is called, create the dummy file
        def fake_save(filepath):
            with open(filepath, 'wb') as f:
                f.write(b'fake audio data')
        mock_instance.save.side_effect = fake_save

        response = self.app.get('/api/tts?word=hello-test-mock&speed=normal')
        
        # The endpoint should return 200 (since thread join is 2s and mock is immediate)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'audio/mpeg')
        self.assertEqual(response.data, b'fake audio data')
        
        # Clean up mock file
        mock_path = os.path.join('static', 'audio', 'hello-test-mock.mp3')
        if os.path.exists(mock_path):
            try:
                os.remove(mock_path)
            except Exception:
                pass

    def test_tts_cache_stats(self):
        response = self.app.get('/api/tts/cache-stats')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('total_files', data)
        self.assertIn('total_size_mb', data)

if __name__ == '__main__':
    unittest.main()
