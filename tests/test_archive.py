import base64
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer

from loucks_history.__main__ import connect, handler_for, prepare


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        prepare(self.directory)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.directory))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        body = json.dumps(data) if data is not None else None
        merged = {'Content-Type': 'application/json'}
        merged.update(headers or {})
        conn.request(method, path, body, merged)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def post(self, path, data):
        status, _, raw = self.request('POST', path, data)
        return status, json.loads(raw)

    def test_family_relationships_persist(self):
        status, parent = self.post('/api/people', {'name': 'Test Ancestor', 'born': '1900-01-02'})
        self.assertEqual(status, 201)
        status, child = self.post('/api/people', {'name': 'Test Descendant', 'parent1': parent['id']})
        self.assertEqual(status, 201)
        prepare(self.directory)  # Reinitialization must retain existing records.
        status, _, raw = self.request('GET', '/api/archive')
        self.assertEqual(status, 200)
        people = json.loads(raw)['people']
        self.assertEqual(len(people), 2)
        self.assertEqual(next(p for p in people if p['id'] == child['id'])['parent1'], parent['id'])
        with connect(self.directory) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM people').fetchone()[0], 2)

    def test_document_upload_download_preserves_original(self):
        _, person = self.post('/api/people', {'name': 'Test Person'})
        content = b'Original family research\x00\xff'
        status, document = self.post('/api/documents', {'title': 'Research notes', 'filename': '../notes.txt',
            'category': 'Research', 'person_id': person['id'], 'content': base64.b64encode(content).decode()})
        self.assertEqual(status, 201)
        status, headers, raw = self.request('GET', '/api/documents/' + document['id'])
        self.assertEqual(status, 200)
        self.assertEqual(raw, content)
        self.assertEqual(headers['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertEqual(list((self.directory / 'documents').iterdir()), [self.directory / 'documents' / document['id']])
        self.assertFalse((self.directory / 'notes.txt').exists())

    def test_bad_records_do_not_write(self):
        for record in ({'name': ''}, {'name': 'Test', 'born': 'not-a-date'},
                       {'name': 'Test', 'born': '2000-01-01', 'died': '1900-01-01'},
                       {'name': 'Test', 'parent1': 'missing'}):
            self.assertEqual(self.post('/api/people', record)[0], 400)
        self.assertEqual(json.loads(self.request('GET', '/api/archive')[2])['people'], [])

    def test_invalid_upload_does_not_create_file(self):
        for content in ('', 'not base64!'):
            status, _ = self.post('/api/documents', {'title':'Bad upload', 'filename':'x', 'category':'Other', 'content':content})
            self.assertEqual(status, 400)
        self.assertEqual(list((self.directory / 'documents').iterdir()), [])

    def test_cross_origin_and_host_rejected(self):
        status, _, _ = self.request('POST', '/api/people', {'name':'Test'}, {'Origin':'https://example.com'})
        self.assertEqual(status, 403)
        self.assertEqual(self.request('GET', '/api/archive', headers={'Host':'example.com'})[0], 403)
        self.assertEqual(self.request('POST','/api/people', {'name':'Test'}, {'Content-Type':'text/plain'})[0], 400)

    def test_ui_and_missing_routes(self):
        for path, expected in (('/',b'Loucks History'),('/app.js',b'/api/archive'),('/style.css',b'--paper')):
            status, headers, raw = self.request('GET', path)
            self.assertEqual(status, 200)
            self.assertIn(expected, raw)
            self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.request('GET', '/api/documents/missing')[0], 404)
        self.assertEqual(self.request('GET', '/../../README.md')[0], 404)


if __name__ == '__main__':
    unittest.main()
