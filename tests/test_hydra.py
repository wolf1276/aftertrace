import io
import json
import unittest
from unittest.mock import patch

from hydra import Hydra, HydraError, decode


class HydraTests(unittest.TestCase):
    def test_types(self):
        self.assertIsNone(decode({"type": "null"}))
        self.assertEqual(decode({"type": "vertex_id", "value": 12}), 12)
        self.assertEqual(decode({"type": "list", "value": [
            {"type": "null"}, {"type": "integer", "value": 3}]}), [None, 3])

    def test_remote_requires_tls(self):
        with self.assertRaises(ValueError):
            Hydra("http://example.com", "secret")

    def test_cursor_is_consumed_even_when_unchanged(self):
        pages = [
            {"columns": ["id"], "rows": [[{"type": "vertex_id", "value": n}]],
             "next_cursor": 8 if n < 3 else None, "query_id": "q1"}
            for n in range(1, 4)
        ]
        with patch("hydra.urlopen", side_effect=[io.BytesIO(json.dumps(p).encode()) for p in pages]) as send:
            rows = Hydra("http://127.0.0.1:8443", "secret").query("query", {"src": 1})
        self.assertEqual(rows, [{"id": 1}, {"id": 2}, {"id": 3}])
        for call in send.call_args_list[1:]:
            body = json.loads(call.args[0].data)
            self.assertEqual(body["parameters"], {"src": 1})
            self.assertEqual(body["page_size"], 256)
            self.assertEqual(body["cursor"], 8)
            self.assertEqual(body["query_id"], "q1")

    def test_rejects_missing_result_envelope(self):
        with patch("hydra.urlopen", return_value=io.BytesIO(b'{}')):
            with self.assertRaises(HydraError):
                Hydra("http://localhost:8443", "secret").query("query")

    def test_mutation_empty_rows_are_success(self):
        with patch("hydra.urlopen", return_value=io.BytesIO(b'{"columns": [], "rows": []}')):
            self.assertEqual(Hydra("http://localhost:8443", "secret").query("query"), [])


if __name__ == "__main__":
    unittest.main()
