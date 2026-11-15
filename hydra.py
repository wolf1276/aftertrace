"""HydraDB HTTP transport. No automatic retries: cursors consume pages."""

import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class HydraError(RuntimeError):
    """Sanitized connection/protocol error; never includes credentials or raw bodies."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward a bearer token to another endpoint.


_opener = build_opener(NoRedirect)
urlopen = _opener.open


def decode(cell):
    if not isinstance(cell, dict) or not isinstance(cell.get('type'), str):
        raise HydraError('Invalid HydraDB typed cell')
    if cell['type'] == 'null':
        return None
    if 'value' not in cell:
        raise HydraError('HydraDB cell is missing its value')
    value = cell['value']
    if cell['type'] == 'list':
        if not isinstance(value, list):
            raise HydraError('Invalid HydraDB list cell')
        return [decode(item) for item in value]
    return value


class Hydra:
    def __init__(self, endpoint, token, graph='default', cell='cell-0', timeout=15, namespace='default'):
        url = urlsplit(endpoint)
        if url.scheme not in ('http', 'https') or not url.hostname:
            raise ValueError('Expected an HTTP(S) HydraDB endpoint')
        if url.username or url.password or url.query or url.fragment:
            raise ValueError('Endpoint must not contain credentials, query, or fragment')
        if url.scheme == 'http' and url.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('Remote HydraDB connections require HTTPS')
        if not token or not graph or not cell or not namespace:
            raise ValueError('Token, graph, cell, and namespace are required')
        if any(ch in token + namespace for ch in '\r\n'):
            raise ValueError('Invalid authentication or namespace header')
        if timeout <= 0:
            raise ValueError('Timeout must be positive')
        self.url = endpoint.rstrip('/') + '/v1/graphs/' + quote(graph, safe='') + '/query'
        self.token, self.cell, self.timeout = token, cell, timeout
        self.namespace = namespace
        self.bookmark = None

    def query(self, query, parameters=None):
        if not isinstance(query, str) or not query.strip():
            raise ValueError('Query is required')
        if parameters is not None and not isinstance(parameters, dict):
            raise ValueError('Parameters must be a mapping')
        # Server-generated counters restart; unique IDs prevent durable mutation conflicts.
        body = {'cell_id': self.cell, 'query': query,
                'query_id': 'aftertrace-' + uuid.uuid4().hex,
                'parameters': parameters or {}, 'page_size': 256}
        if self.bookmark:
            body['bookmark'] = self.bookmark
        rows, columns = [], None
        bookmark = None
        for _ in range(1000):
            request = Request(self.url, data=json.dumps(body).encode(), headers={
                'Authorization': 'Bearer ' + self.token,
                'X-Graph-Namespace': self.namespace,
                'Content-Type': 'application/json',
            })
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
            except HTTPError as exc:
                status = exc.code
                exc.close()
                raise HydraError(f'HydraDB HTTP {status}; scan was not retried') from None
            except (URLError, TimeoutError, OSError):
                raise HydraError('HydraDB connection failed or timed out; scan was not retried') from None
            except (ValueError, UnicodeError):
                raise HydraError('HydraDB returned invalid JSON') from None
            if not isinstance(payload, dict):
                raise HydraError('Invalid HydraDB result envelope')
            if 'error' in payload:
                raise HydraError('HydraDB rejected the query')
            if not isinstance(payload.get('rows'), list) or not isinstance(payload.get('columns'), list):
                raise HydraError('Invalid HydraDB result envelope')
            current = payload['columns']
            if not all(isinstance(c, str) for c in current) or len(set(current)) != len(current):
                raise HydraError('Invalid HydraDB result columns')
            if columns is not None and columns != current:
                raise HydraError('HydraDB columns changed during pagination')
            columns = current
            for row in payload['rows']:
                if not isinstance(row, list) or len(row) != len(columns):
                    raise HydraError('HydraDB result column mismatch')
                rows.append(dict(zip(columns, map(decode, row))))
            if payload.get('bookmark') is not None:
                bookmark = payload['bookmark']
                if not isinstance(bookmark, str):
                    raise HydraError('Invalid HydraDB bookmark')
            if payload.get('next_cursor') is None:
                if bookmark:
                    self.bookmark = bookmark
                return rows
            if not isinstance(payload.get('query_id'), str) or not payload['query_id']:
                raise HydraError('Paginated result is missing query_id')
            body.update(cursor=payload['next_cursor'], query_id=payload['query_id'])
        raise HydraError('Query exceeded the client page budget')
