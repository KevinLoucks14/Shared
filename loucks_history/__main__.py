import argparse
import base64
import binascii
import json
import mimetypes
import os
import sqlite3
import uuid
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

STATIC = Path(__file__).parent / 'static'
MAX_UPLOAD = 15 * 1024 * 1024


def connect(directory):
    db = sqlite3.connect(directory / 'archive.sqlite3')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    (directory / 'documents').mkdir(exist_ok=True, mode=0o700)
    with connect(directory) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, born TEXT NOT NULL DEFAULT '',
            died TEXT NOT NULL DEFAULT '', birthplace TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', parent1 TEXT REFERENCES people(id),
            parent2 TEXT REFERENCES people(id)
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
            category TEXT NOT NULL, person_id TEXT REFERENCES people(id),
            notes TEXT NOT NULL DEFAULT '', size INTEGER NOT NULL,
            created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ''')


def handler_for(directory):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Keep private names, filenames, and URLs out of access logs.
            pass

        def send(self, status, body, content_type='application/json', extra=None):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            host = self.headers.get('Host', '')
            if host not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                self.send(403, {'error': 'Use the local archive address.'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + host:
                self.send(403, {'error': 'Cross-origin requests are blocked.'})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path = urlparse(self.path).path
            if path == '/api/archive':
                with connect(directory) as db:
                    self.send(200, {
                        'people': [dict(r) for r in db.execute('SELECT * FROM people ORDER BY name COLLATE NOCASE')],
                        'documents': [dict(r) for r in db.execute('SELECT * FROM documents ORDER BY created DESC, rowid DESC')],
                    })
                return
            if path.startswith('/api/documents/'):
                document_id = path.rsplit('/', 1)[-1]
                with connect(directory) as db:
                    row = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
                if row is None:
                    self.send(404, {'error': 'Document not found.'})
                    return
                filename = row['filename'].replace('"', '').replace('\\', '_')
                self.send(200, (directory / 'documents' / row['id']).read_bytes(),
                          'application/octet-stream', {'Content-Disposition': f'attachment; filename="document"; filename*=UTF-8\'\'{quote(filename)}'})
                return
            files = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
            if path not in files:
                self.send(404, {'error': 'Not found.'})
                return
            file = STATIC / files[path]
            self.send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'text/plain')

        def do_POST(self):
            if not self.allowed():
                return
            try:
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('Send application/json.')
                size = int(self.headers.get('Content-Length', '0'))
                if size <= 0 or size > MAX_UPLOAD * 4 // 3 + 65536:
                    raise ValueError('Request too large. Maximum file size is 15 MB.')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Invalid request.')
                with connect(directory) as db:
                    if self.path == '/api/people':
                        name = self.field(data, 'name', 200, required=True)
                        born, died = (self.field(data, k, 10) for k in ('born', 'died'))
                        for value in (born, died):
                            if value:
                                date.fromisoformat(value)
                        if born and died and born > died:
                            raise ValueError('Death date must follow birth date.')
                        parents = [self.field(data, k, 32) or None for k in ('parent1', 'parent2')]
                        if parents[0] and parents[0] == parents[1]:
                            raise ValueError('Choose two different parents.')
                        identifier = uuid.uuid4().hex
                        db.execute('INSERT INTO people VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                                   (identifier, name, born, died, self.field(data, 'birthplace', 300),
                                    self.field(data, 'notes', 20000), *parents))
                    elif self.path == '/api/documents':
                        title = self.field(data, 'title', 300, required=True)
                        filename = self.field(data, 'filename', 250, required=True)
                        category = self.field(data, 'category', 40, required=True)
                        if category not in ['Photograph', 'Certificate', 'Letter', 'Research', 'Other']:
                            raise ValueError('Choose a document category.')
                        raw = base64.b64decode(self.field(data, 'content', MAX_UPLOAD * 4 // 3), validate=True)
                        if not raw or len(raw) > MAX_UPLOAD:
                            raise ValueError('Choose a nonempty file up to 15 MB.')
                        person = self.field(data, 'person_id', 32) or None
                        if person and not db.execute('SELECT id FROM people WHERE id=?', (person,)).fetchone():
                            raise ValueError('Family member not found.')
                        notes = self.field(data, 'notes', 20000)
                        identifier = uuid.uuid4().hex
                        target = directory / 'documents' / identifier
                        with target.open('xb') as stream:
                            stream.write(raw)
                        try:
                            db.execute('INSERT INTO documents (id,title,filename,category,person_id,notes,size) VALUES (?,?,?,?,?,?,?)',
                                       (identifier, title, filename, category, person, notes, len(raw)))
                            db.commit()
                        except Exception:
                            target.unlink(missing_ok=True)
                            raise
                    else:
                        self.send(404, {'error': 'Not found.'})
                        return
                self.send(201, {'id': identifier})
            except (ValueError, TypeError, binascii.Error, sqlite3.IntegrityError) as exc:
                message = 'Choose an existing family member.' if isinstance(exc, sqlite3.IntegrityError) else str(exc)
                self.send(400, {'error': message or 'Invalid request.'})

        @staticmethod
        def field(data, key, maximum, required=False):
            value = data.get(key, '')
            if not isinstance(value, str):
                raise ValueError(f'Invalid {key}.')
            value = value.strip()
            if len(value) > maximum or (required and not value):
                raise ValueError(f'{key.capitalize()} is required and must be at most {maximum} characters.')
            return value
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Run the local Loucks History archive.')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('LOUCKS_DATA_DIR', '.history-data')))
    args = parser.parse_args()
    directory = args.data_dir.resolve()
    prepare(directory)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(directory))
    print(f'Loucks History running locally on port {args.port}. Data directory: {directory}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
