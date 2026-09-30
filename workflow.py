"""Open all project settings in the default browser. No interactive terminal prompts."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'toolkit/review_workspace'))
from setup_server import main
if __name__=='__main__':
    if sys.version_info<(3,10):raise SystemExit('Python 3.10 or newer is required.')
    main(no_browser='--no-browser' in sys.argv)
