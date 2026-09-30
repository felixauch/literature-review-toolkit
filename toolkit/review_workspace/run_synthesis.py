"""Local extraction and synthesis workspace. No generative model calls."""
import sys
if __name__=='__main__':
    if len(sys.argv)<2 or sys.argv[1] not in ('extract','serve'):
        raise SystemExit('Usage: python run_synthesis.py extract --csv FILE --pdf-root DIR --out NEW_RUN\n       python run_synthesis.py serve --run RUN --port 8797')
    command=sys.argv.pop(1)
    if command=='extract':from synthesis.extract import main
    else:from synthesis.server import main
    main()
