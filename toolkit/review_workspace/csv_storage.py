"""Local CSV records with atomic replacement, revision checks and complete history.

Review data are typed CSV columns, not an SQL database. A canonical history file
is the commit point; current-state CSVs are derived views and can be rebuilt.
"""
from __future__ import annotations
import csv, hashlib, io, json, os, tempfile, threading, time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

csv.field_size_limit(64 * 1024 * 1024)
_LOCKS = {}; _LOCK_GUARD = threading.Lock()

class StorageError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message); self.status=status


def flatten(value, path=''):
    """Reversible typed columns keep strings (including formula-like text) exact."""
    if isinstance(value,dict):
        yield 'object|'+path, ''
        for k,v in value.items():
            if not isinstance(k,str): raise StorageError('Record keys must be text.')
            key=k.replace('~','~0').replace('/','~1')
            yield from flatten(v,path+'/'+key)
    elif isinstance(value,list):
        yield 'array|'+path, str(len(value))
        for i,v in enumerate(value): yield from flatten(v,path+'/'+str(i))
    elif value is None: yield 'null|'+path,''
    elif isinstance(value,bool): yield 'bool|'+path,'true' if value else 'false'
    elif isinstance(value,int): yield 'int|'+path,str(value)
    elif isinstance(value,float): yield 'float|'+path,repr(value)
    elif isinstance(value,str):
        # Escape every string consistently for spreadsheet safety; decode exactly.
        yield 'text|'+path,"'"+value
    else: raise StorageError('Unsupported record value.')


def inflate(row):
    values={}; kinds={}
    for header,raw in row.items():
        if '|' not in header or raw is None or raw=='':continue
        kind,path=header.split('|',1);kinds[path]=kind
        if kind=='object':v={}
        elif kind=='array':v=[None]*int(raw)
        elif kind=='null':v=None
        elif kind=='bool':
            if raw not in ('true','false'):raise ValueError('Invalid boolean')
            v=raw=='true'
        elif kind=='int':v=int(raw)
        elif kind=='float':v=float(raw)
        elif kind=='text':
            if not raw.startswith("'"):raise ValueError('Invalid text encoding')
            v=raw[1:]
        else:raise ValueError('Invalid column type')
        if path in values:raise ValueError('Duplicate typed path')
        values[path]=v
    for path in sorted(values,key=lambda x:x.count('/')):
        if not path:continue
        parent,_,key=path.rpartition('/');key=key.replace('~1','/').replace('~0','~')
        target=values[parent]
        if isinstance(target,list):target[int(key)]=values[path]
        else:target[key]=values[path]
    return values['']


def encode(rows):
    flat=[]; columns=[];seen=set()
    for value in rows:
        row=dict(flatten(value))
        # Nonempty markers distinguish empty objects/null from absent columns.
        for k in row:
            if k.startswith(('object|','null|')):row[k]='1'
        flat.append(row)
        for k in row:
            if k not in seen:seen.add(k);columns.append(k)
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=columns or ['object|'])
    writer.writeheader();writer.writerows(flat)
    return ('\ufeff'+out.getvalue()).encode('utf-8')


def decode(raw):
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''),strict=True)
        if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames):raise ValueError('Invalid headers')
        result=[]
        for row in reader:
            if None in row or None in row.values():raise ValueError('Incomplete CSV row')
            result.append(inflate(row))
        return result
    except (ValueError,KeyError,TypeError,IndexError,csv.Error,UnicodeError) as e:
        raise StorageError('CSV is damaged or was edited outside the toolkit. Restore its backup or import corrected records.') from e


def atomic_write(path, raw, backup=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if backup and path.exists():atomic_write(path.with_name(path.stem+'.backup.csv'),path.read_bytes())
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def write_object(path, value):atomic_write(path,encode([value]))
def read_object(path):
    rows=decode(Path(path).read_bytes())
    if len(rows)!=1:raise StorageError('Expected exactly one CSV document.')
    return rows[0]


@contextmanager
def file_lock(path, timeout=15):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    key=str(path.resolve())
    with _LOCK_GUARD:lock=_LOCKS.setdefault(key,threading.RLock())
    if not lock.acquire(timeout=timeout):raise StorageError('Another save is in progress. Please try again.')
    handle=None;locked=False
    try:
        handle=path.open('a+b');handle.seek(0,2)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        deadline=time.monotonic()+timeout
        while True:
            try:
                handle.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                locked=True;break
            except OSError:
                if time.monotonic()>=deadline:raise StorageError('Another process is saving this review. Try again.')
                time.sleep(.04)
        yield
    finally:
        if handle:
            if locked:
                handle.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
            handle.close()
        lock.release()


class CsvJournal:
    """One canonical CSV, one row per saved revision. No uncommitted snapshots."""
    def __init__(self,root,name,id_key='id',event_key='event'):
        self.root=Path(root);self.path=self.root/(name+'.csv');self.current_path=self.root/(name+'_current.csv')
        self.lock_path=self.root/('.'+name+'.lock');self.id_key=id_key;self.event_key=event_key
        self._stamp=None;self._events=[];self._current={};self.root.mkdir(parents=True,exist_ok=True)
        with file_lock(self.lock_path):
            if not self.path.exists():atomic_write(self.path,encode([]))
            self._load();self._snapshot()
    @property
    def stamp(self):
        st=self.path.stat();return (st.st_mtime_ns,st.st_size)
    def _load(self):
        stamp=self.stamp
        if stamp==self._stamp:return
        events=decode(self.path.read_bytes());current={};last_event=0
        for row in events:
            checksum=row.pop('_checksum',None)
            raw=json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
            if checksum!=hashlib.sha256(raw).hexdigest():raise StorageError('CSV revision checksum does not match. Use the backup or import edits through the interface.')
            ident=row.get(self.id_key);revision=row.get('revision');event=row.get(self.event_key)
            if not isinstance(ident,str) or not ident or type(revision)!=int or revision<1 or type(event)!=int or event<=last_event:raise StorageError('Invalid CSV revision history.')
            if ident in current and revision<=current[ident]['revision']:raise StorageError('CSV revision history is not increasing.')
            current[ident]=dict(row);last_event=event
        self._events=events;self._current=current;self._stamp=stamp
    def _snapshot(self):
        rows=[]
        for row in self._current.values():
            r=dict(row);r.pop(self.event_key,None);rows.append(r)
        raw=encode(rows)
        if not self.current_path.exists() or self.current_path.read_bytes()!=raw:atomic_write(self.current_path,raw)
    def states(self):
        with file_lock(self.lock_path):
            self._load();rows=deepcopy(self._current)
            for row in rows.values():row.pop(self.event_key,None)
            return rows
    def history(self,ident=None):
        with file_lock(self.lock_path):
            self._load();return deepcopy([r for r in self._events if ident is None or r[self.id_key]==ident])
    def save(self,row,expected_revision):
        ident=row[self.id_key]
        with file_lock(self.lock_path):
            self._load();actual=self._current.get(ident,{}).get('revision',0)
            if type(expected_revision)!=int or expected_revision!=actual:raise StorageError('This record changed in another window. Reload before saving.')
            value=deepcopy(row);value['revision']=actual+1;value[self.event_key]=(self._events[-1][self.event_key]+1) if self._events else 1
            self._write_events(self._events+[value]);result=deepcopy(value);result.pop(self.event_key,None)
            return result
    def import_history(self,rows):
        with file_lock(self.lock_path):
            self._load()
            if self._events:raise StorageError('Migration destination is not empty.')
            values=[]
            for event,row in enumerate(rows,1):
                value=deepcopy(row);value[self.event_key]=event;values.append(value)
            self._write_events(values)
    def _write_events(self,events):
        encoded=[]
        for row in events:
            value=deepcopy(row);raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode();value['_checksum']=hashlib.sha256(raw).hexdigest();encoded.append(value)
        atomic_write(self.path,encode(encoded),backup=True)
        self._stamp=None;self._load()
        # Snapshot is derived; a failed snapshot must not turn a committed save into a false failure.
        try:self._snapshot()
        except OSError:pass


def archive_records(root):
    """Freeze the four journals while exporting a consistent CSV/settings copy."""
    import zipfile
    from contextlib import ExitStack
    root=Path(root).resolve()
    locks=[root/'.extraction.lock',root/'.domain_notes.lock',root/'.reading.lock',root/'classification/.classification.lock']
    buffer=io.BytesIO()
    with ExitStack() as stack:
        for path in sorted(locks):stack.enter_context(file_lock(path))
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
            for path in sorted(root.rglob('*')):
                if path.is_file() and path.suffix in ('.csv','.json'):
                    z.writestr(path.relative_to(root).as_posix(),path.read_bytes())
    return buffer.getvalue()
