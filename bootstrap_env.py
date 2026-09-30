"""Create or repair this toolkit's Python environment, then install its dependencies."""
from pathlib import Path
import datetime
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
MIN_VERSION = (3, 10)


def usable(executable):
    try:
        result = subprocess.run([str(executable), '-c', 'import sys; sys.exit(sys.version_info < (3, 10))'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main():
    if sys.version_info < MIN_VERSION:
        raise SystemExit('Python 3.10 or newer is required. Install it, then run Setup.cmd again.')
    environment = HERE / '.venv'
    executable = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not usable(executable):
        if environment.exists():
            # Never move a resolved environment outside this toolkit folder.
            if environment.resolve().parent != HERE or not (environment / 'pyvenv.cfg').is_file():
                raise SystemExit('The .venv path is not a recognised local virtual environment. Check it manually.')
            backup = HERE / ('.venv-backup-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            if backup.resolve().parent != HERE or backup.exists():
                raise SystemExit('Could not choose a safe environment backup path.')
            shutil.move(str(environment), str(backup))
            print('Previous environment saved as ' + backup.name, flush=True)
        print('Creating a Python ' + sys.version.split()[0] + ' environment...', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True)
    subprocess.run([str(executable), '-m', 'pip', 'install', '-r', str(HERE / 'requirements.txt')], check=True)
    subprocess.run([str(executable), '-c', 'import pypdf, pypdfium2, requests; print("Dependencies ready.")'], check=True)
    print('Setup complete. Run Start review.cmd.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit('Setup failed: ' + str(exc))
