"""Local browser setup for the configurable review toolkit. No model services."""
import csv
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import importlib.util
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from project_setup import validate

HERE = Path(__file__).resolve().parent
STATIC = HERE / 'setup_ui'
TOOLKIT_ROOT = HERE.parent.parent if (HERE.parent.parent/'toolkit.py').is_file() else None


def handoff_module():
    if TOOLKIT_ROOT is None:
        raise ValueError('Search/screening tools are not included in this standalone module.')
    spec=importlib.util.spec_from_file_location('review_handoff', TOOLKIT_ROOT/'handoff.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def handoff_check(raw):
    validate(raw.get('config'), 'review')
    project=local_path(raw.get('project'))
    module=handoff_module()
    rows, counts=module.collect(module.project_path(str(project)))
    out=local_path(raw.get('out'))
    config_path=out.with_name(out.name+'.project.json')
    if out.exists() or config_path.exists() or not out.parent.is_dir():
        raise ValueError('Choose a new review folder name inside an existing parent folder.')
    return dict(config=raw['config'], project=str(project), out=str(out), config_path=str(config_path), records=len(rows), counts=counts)


def local_path(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Choose a local file or folder.')
    value = value.strip().strip('"')
    if value.startswith(('\\\\', '//')) or re.match(r'^[a-z][a-z0-9+.-]*://', value, re.I):
        raise ValueError('Choose a path on a local drive, not a URL or network share.')
    result = Path(value).expanduser().resolve()
    if str(result).startswith(('\\\\', '//')):
        raise ValueError('Choose a local drive.')
    return result


def free_port(preferred=8799):
    for number in range(preferred, preferred + 50):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', number))
                return number
            except OSError:
                pass
    raise ValueError('No free review port found. Close an unused review server.')


def preflight(raw):
    config = validate(raw.get('config'), 'review')
    source, pdf_root, out = [local_path(raw.get(key)) for key in ('csv', 'pdf_root', 'out')]
    if not source.is_file() or source.suffix.lower() != '.csv':
        raise ValueError('Select a metadata CSV file.')
    if not pdf_root.is_dir():
        raise ValueError('Select the folder containing your PDFs.')
    if out.exists():
        raise ValueError('The review folder already exists. Use Open saved review, or choose a new folder name.')
    if not out.parent.is_dir():
        raise ValueError('The parent folder for the new review must already exist.')
    config_path = out.with_name(out.name + '.project.json')
    if config_path.exists():
        raise ValueError('A settings file already uses this review name. Choose a new review folder name.')
    with source.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if 'record_id' not in (reader.fieldnames or []) or not {'pdf_path', 'fulltext_local_pdf'}.intersection(reader.fieldnames or []):
            raise ValueError('CSV needs record_id and either pdf_path or fulltext_local_pdf columns.')
        rows = list(reader)
    ids = [row.get('record_id', '') for row in rows]
    if not rows or any(not re.fullmatch(r'[A-Za-z0-9_-]+', i) for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('CSV needs at least one paper and unique IDs using letters, digits, underscores or hyphens.')
    missing = []
    for row in rows:
        value = (row.get('fulltext_local_pdf') or row.get('pdf_path') or '').strip()
        try:
            if not value or value.startswith(('\\\\', '//')) or re.match(r'^[a-z][a-z0-9+.-]*://', value, re.I):
                raise ValueError()
            path = Path(value)
            path = local_path(str(path if path.is_absolute() else pdf_root / path))
            if not path.is_relative_to(pdf_root) or path.suffix.lower() != '.pdf' or not path.is_file():
                raise ValueError()
        except (ValueError, OSError):
            missing.append(row['record_id'])
    if missing:
        raise ValueError('PDF paths could not be matched inside the selected folder for: ' + ', '.join(missing[:12]) + (f' and {len(missing)-12} more' if len(missing)>12 else '') + '. Correct the CSV paths or PDF folder before creating the review.')
    return dict(config=config, csv=str(source), pdf_root=str(pdf_root), out=str(out), config_path=str(config_path), records=len(rows))


class SetupServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)
        self.job = {'status': 'idle', 'log': []}
        self.lock = threading.Lock()

    def begin(self, raw, resume=False, handoff=False):
        with self.lock:
            if self.job['status'] == 'running':
                raise ValueError('A review is already being prepared. Wait for it to finish.')
            if resume:
                run = local_path(raw.get('run'))
                if (run/'manifest.csv').is_file() and (run/'classification/catalog.csv').is_file():
                    data = {'out': str(run)}
                elif (run/'manifest.json').is_file() and (run/'classification/catalog.json').is_file():
                    target=run.with_name(run.name+'-csv')
                    if target.exists():raise ValueError('A CSV copy already exists. Select '+str(target)+' to open it, or choose a new migration folder with migrate_legacy.py.')
                    data={'out':str(target),'migration_source':str(run)}
                else:
                    raise ValueError('Choose a prepared review folder containing manifest.csv (or an older manifest.json).')
            else:
                data = handoff_check(raw) if handoff else preflight(raw)
                # Exclusive creation protects settings even if another window races this one.
                with Path(data['config_path']).open('x', encoding='utf-8') as stream:
                    json.dump(data['config'], stream, ensure_ascii=False, indent=2)
            self.job = {'status': 'running', 'log': [], 'out': data['out']}
            threading.Thread(target=self.prepare, args=(data, resume), daemon=True).start()
        return {'started': True}

    def command(self, args):
        lines = []
        with subprocess.Popen([sys.executable, *args], cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding='utf-8', errors='replace',
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
            for line in process.stdout:
                lines.append(line.rstrip())
                with self.lock:
                    self.job['log'] = lines[-15:]
            if process.wait():
                raise ValueError(lines[-1] if lines else 'Preparation failed. Check the input files and choose a new output folder to retry.')
        return lines

    def prepare(self, data, resume):
        try:
            if data.get('migration_source'):
                self.command([str(HERE/'migrate_legacy.py'),'--source',data['migration_source'],'--out',data['out']])
            if not resume:
                if 'project' in data:
                    self.command([str(TOOLKIT_ROOT/'handoff.py'), '--project', data['project'], '--config', data['config_path'], '--out', data['out']])
                else:
                    self.command([str(HERE/'prepare_review.py'), '--config', data['config_path'], '--csv', data['csv'], '--pdf-root', data['pdf_root'], '--out', data['out']])
            port = free_port()
            self.command([str(HERE/'launch.py'), '--run', data['out'], '--port', str(port)])
            with self.lock:
                self.job.update(status='complete', url=f'http://127.0.0.1:{port}/')
        except Exception as exc:
            with self.lock:
                self.job.update(status='error', error=str(exc))

    def search(self, raw):
        if TOOLKIT_ROOT is None:raise ValueError('Search tools unavailable.')
        with self.lock:
            if self.job['status']=='running':raise ValueError('Wait for the current task to finish.')
            if raw.get('project'):
                project=local_path(raw['project']);slug=None
                if not (project/'project.json').is_file():raise ValueError('Select a saved search project.')
            else:
                slug=raw.get('slug','');name=raw.get('name','').strip()
                if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',slug) or not name:raise ValueError('Enter a review name and a folder name using lowercase letters, numbers and hyphens.')
                project=TOOLKIT_ROOT/'projects'/slug
                if project.exists():raise ValueError('That search project already exists. Open it or choose another name.')
            self.job={'status':'running','log':[]}
        def worker():
            try:
                if slug:self.command([str(TOOLKIT_ROOT/'toolkit.py'),'init',slug,name])
                port=free_port(8765);url=f'http://127.0.0.1:{port}/setup.html'
                with (project/f'setup-server-{port}.log').open('ab') as log:
                    process=subprocess.Popen([sys.executable,str(TOOLKIT_ROOT/'toolkit.py'),'serve',str(project),'--port',str(port)],cwd=TOOLKIT_ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(url,timeout=1) as response:
                            if response.status==200:break
                    except OSError:
                        if process.poll() is not None:raise ValueError('The search interface could not start. Check its setup-server log.')
                        time.sleep(.15)
                else:raise ValueError('The search interface did not respond.')
                with self.lock:self.job.update(status='complete',url=url)
            except Exception as exc:
                with self.lock:self.job.update(status='error',error=str(exc))
        threading.Thread(target=worker,daemon=True).start()
        return {'started':True}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, value, code=200, content_type='application/json; charset=utf-8'):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self, token=False):
        host = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != host or self.headers.get('Origin', 'http://'+host) != 'http://'+host:
            self.send({'error': 'Only the local setup page can access this service.'}, 403)
            return False
        if self.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
            self.send({'error': 'Cross-origin access is not allowed.'}, 403)
            return False
        if token and not secrets.compare_digest(self.headers.get('X-Setup-Token', ''), self.server.token):
            self.send({'error': 'Reload the setup page and try again.'}, 403)
            return False
        return True

    def do_GET(self):
        parsed = urlsplit(self.path)
        if not self.allowed(parsed.path.startswith('/api/') and parsed.path != '/api/bootstrap'):
            return
        try:
            if parsed.path == '/api/bootstrap':
                data={'token': self.server.token, 'home': str(Path.home()), 'projects': str(Path.home()/'Documents'), 'csv_template': (HERE/'records_template.csv').read_text(encoding='utf-8-sig')}
                if TOOLKIT_ROOT:
                    data['search_projects']=[]
                    for path in sorted((TOOLKIT_ROOT/'projects').glob('*/project.json')):
                        if path.parent.name.startswith('_'):continue
                        try:data['search_projects'].append({'name':json.loads(path.read_text(encoding='utf-8-sig')).get('name',path.parent.name),'path':str(path.parent)})
                        except (ValueError,OSError):continue
                self.send(data)
            elif parsed.path == '/theme.css':
                self.send((HERE.parent/'ui/theme.css').read_bytes(), content_type='text/css; charset=utf-8')
            elif parsed.path == '/api/job':
                with self.server.lock:
                    self.send(self.server.job)
            elif parsed.path == '/api/browse':
                params = parse_qs(parsed.query)
                path = local_path(params.get('path', [str(Path.home())])[0])
                if not path.is_dir():
                    path = path.parent
                kind = params.get('kind', ['folder'])[0]
                files = []
                for entry in path.iterdir():
                    try:
                        if entry.name.startswith('.') or entry.is_symlink():
                            continue
                        directory = entry.is_dir()
                        if directory or (kind in ('csv', 'json') and entry.suffix.lower() == '.'+kind):
                            files.append({'name': entry.name, 'path': str(entry), 'directory': directory})
                    except OSError:
                        continue
                files.sort(key=lambda x: (not x['directory'], x['name'].lower()))
                drives = [f'{letter}:\\' for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if Path(f'{letter}:\\').exists()] if os.name == 'nt' else ['/']
                self.send({'path': str(path), 'parent': str(path.parent), 'entries': files, 'drives': drives})
            else:
                files = {'/': ('index.html', 'text/html; charset=utf-8'), '/setup.js': ('setup.js', 'text/javascript; charset=utf-8'), '/setup.css': ('setup.css', 'text/css; charset=utf-8')}
                if parsed.path not in files:
                    return self.send({'error': 'Not found'}, 404)
                name, mime = files[parsed.path]
                self.send((STATIC/name).read_bytes(), content_type=mime)
        except (ValueError, OSError) as exc:
            self.send({'error': str(exc)}, 400)

    def do_POST(self):
        if not self.allowed(True):
            return
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('JSON content required.')
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 1000000:
                raise ValueError('Invalid request size.')
            raw = json.loads(self.rfile.read(size))
            if not isinstance(raw, dict):
                raise ValueError('Expected an object.')
            if self.path == '/api/validate':
                validate(raw.get('config'), 'review')
                result = {'valid': True}
            elif self.path == '/api/check':
                data = preflight(raw)
                result = {'valid': True, 'records': data['records'], 'out': data['out']}
            elif self.path == '/api/create':
                result = self.server.begin(raw)
            elif self.path == '/api/resume':
                result = self.server.begin(raw, resume=True)
            elif self.path == '/api/handoff-check':
                data=handoff_check(raw)
                result={'valid':True,'records':data['records'],'counts':data['counts']}
            elif self.path == '/api/handoff':
                result=self.server.begin(raw,handoff=True)
            elif self.path == '/api/search':
                result=self.server.search(raw)
            else:
                return self.send({'error': 'Not found'}, 404)
            self.send(result)
        except (ValueError, OSError, TypeError, AttributeError, KeyError) as exc:
            self.send({'error': str(exc)}, 400)


def open_browser(url):
    try:
        if not webbrowser.open(url, new=2):
            print('The default browser could not be opened. Paste this URL into your browser: ' + url, flush=True)
    except Exception as exc:
        print('Browser launch failed: ' + str(exc) + '. Open ' + url + ' manually.', flush=True)


def main(no_browser=False, port=0):
    server = SetupServer(('127.0.0.1', port))
    url = f'http://127.0.0.1:{server.server_port}/'
    print('Project setup: ' + url, flush=True)
    if not no_browser:
        threading.Timer(.3, lambda: open_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
