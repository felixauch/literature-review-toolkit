"""Restart the local review server without re-extracting or overwriting decisions."""
import argparse,hashlib,json,subprocess,sys,time,urllib.request
from pathlib import Path
from synthesis import VERSION

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',required=True);ap.add_argument('--port',type=int,default=8797);a=ap.parse_args()
    run=Path(a.run).resolve();url=f'http://127.0.0.1:{a.port}'
    if not (run/'manifest.csv').exists():raise SystemExit('Extraction run not found')
    def status():
        try:
            with urllib.request.urlopen(url+'/api/status',timeout=1) as f:return json.load(f)
        except Exception:return None
    current=status()
    if current and current.get('app')!='local-synthesis-review':raise SystemExit('Port belongs to another app; select another port')
    if current and current.get('run_id')!=hashlib.sha256(str(run).encode()).hexdigest():raise SystemExit('Port serves a different run or an older server. Use a different port.')
    if current and current.get('version')!=VERSION:raise SystemExit('This port serves an older application version. Save open work and select another port for this version.')
    if not current:
        with (run/f'server-{a.port}.log').open('ab') as log:
            process=subprocess.Popen([sys.executable,str(Path(__file__).parent/'run_synthesis.py'),'serve','--run',str(run),'--port',str(a.port)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(50):
            current=status()
            if current:break
            if process.poll() is not None:raise SystemExit('Server did not start; inspect its log')
            time.sleep(.2)
        else:raise SystemExit('Server did not respond')
    print(json.dumps({'url':url,'app':current['app'],'records':current['records']}))

if __name__=='__main__':main()
