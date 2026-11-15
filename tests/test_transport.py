import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from hydra import Hydra, HydraError, NoRedirect, decode


class TransportTests(unittest.TestCase):
    def client(self):
        return Hydra('http://127.0.0.1:18443', 'test-secret')

    def test_http_errors_are_sanitized(self):
        for status in (401, 422, 500, 302):
            with self.subTest(status=status), patch('hydra.urlopen', side_effect=HTTPError('test-secret', status, 'test-secret', {}, io.BytesIO(b'test-secret'))):
                with self.assertRaises(HydraError) as caught:
                    self.client().query('MATCH sensitive')
                self.assertIn(str(status), str(caught.exception))
                self.assertNotIn('test-secret', str(caught.exception))

    def test_failure_never_retries_or_returns_partial_rows(self):
        first = {'columns': ['id'], 'rows': [[{'type': 'vertex_id', 'value': 1}]], 'query_id': 'q', 'next_cursor': 5}
        with patch('hydra.urlopen', side_effect=[io.BytesIO(json.dumps(first).encode()), URLError('test-secret')]) as send:
            with self.assertRaises(HydraError):
                self.client().query('query')
            self.assertEqual(send.call_count, 2)

    def test_invalid_json_and_envelopes(self):
        for value in (b'not json', b'[]', b'null', b'{"error":{"message":"secret"}}', b'{"columns":["x"],"rows":[[]]}'):
            with self.subTest(value=value), patch('hydra.urlopen', return_value=io.BytesIO(value)):
                with self.assertRaises(HydraError):
                    self.client().query('query')

    def test_timeout_is_sanitized(self):
        with patch('hydra.urlopen', side_effect=TimeoutError('test-secret')):
            with self.assertRaises(HydraError) as caught:
                self.client().query('query')
            self.assertNotIn('test-secret', str(caught.exception))

    def test_bookmark_and_namespace(self):
        client = self.client()
        payload = b'{"columns":[],"rows":[],"bookmark":"sgk:test"}'
        with patch('hydra.urlopen', side_effect=[io.BytesIO(payload), io.BytesIO(payload)]) as send:
            client.query('write')
            client.query('read')
        request = send.call_args.args[0]
        self.assertEqual(json.loads(request.data)['bookmark'], 'sgk:test')
        self.assertEqual(request.get_header('X-graph-namespace'), 'default')

    def test_rejects_column_changes(self):
        first = {'columns': ['id'], 'rows': [], 'query_id': 'q', 'next_cursor': 1}
        last = {'columns': ['other'], 'rows': []}
        with patch('hydra.urlopen', side_effect=[io.BytesIO(json.dumps(p).encode()) for p in (first, last)]):
            with self.assertRaises(HydraError):
                self.client().query('query')

    def test_new_queries_get_unique_ids(self):
        payload = b'{"columns":[],"rows":[]}'
        with patch('hydra.urlopen', side_effect=[io.BytesIO(payload), io.BytesIO(payload)]) as send:
            self.client().query('write')
            self.client().query('write')
        ids = [json.loads(call.args[0].data)['query_id'] for call in send.call_args_list]
        self.assertTrue(all(value.startswith('aftertrace-') for value in ids))
        self.assertNotEqual(*ids)

    def test_no_bearer_redirect(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example'))

    def test_malformed_cells(self):
        for cell in (None, {}, {'type': 'string'}, {'type': 'list', 'value': 3}):
            with self.subTest(cell=cell), self.assertRaises(HydraError):
                decode(cell)

    def test_validation(self):
        for endpoint in ('ftp://localhost', 'https://u:p@example.com', 'http://example.com', 'https://example.com?token=secret'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                Hydra(endpoint, 'test-secret')
        with self.assertRaises(ValueError):
            self.client().query('query', [])
        with self.assertRaises(ValueError):
            Hydra('https://example.com', 'secret\r\nInjected: value')


if __name__ == '__main__':
    unittest.main()
