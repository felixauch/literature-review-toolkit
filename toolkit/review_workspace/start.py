"""Open browser-based setup, or resume an existing run from command-line arguments."""
import argparse,subprocess,sys,webbrowser
from pathlib import Path
HERE=Path(__file__).resolve().parent
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run');p.add_argument('--port',type=int,default=8799);p.add_argument('--no-browser',action='store_true');a=p.parse_args()
 run=a.run
 if not run:
  from setup_server import main as setup_browser
  setup_browser(no_browser=a.no_browser)
  return
 if not run or not (Path(run)/'classification/catalog.csv').is_file():raise SystemExit('Choose a prepared unified review run.')
 subprocess.run([sys.executable,str(HERE/'launch.py'),'--run',run,'--port',str(a.port)],check=True)
 url=f'http://127.0.0.1:{a.port}/'
 if not a.no_browser:
  webbrowser.open(url,new=2)
 print('Review ready: '+url)
if __name__=='__main__':main()
