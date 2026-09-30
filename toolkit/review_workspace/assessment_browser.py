"""Export a standalone CSV corpus explorer using the live toolkit UI assets."""
from pathlib import Path
import argparse,base64,csv,io,json,re,zipfile
HERE=Path(__file__).resolve().parent
STATIC=HERE/'synthesis/static'
README='''CORPUS EXPLORER

Extract this ZIP, then double-click Corpus explorer.html. No Python,
server, database, model, internet connection or installation is needed.

This read-only browser uses the same paper view, styling, filters, charts
and clickable synthesis matrices as the literature review toolkit. It reads
the accompanying assessment-summary CSV, also embedded in the HTML so
file:// opening works. Load CSV lets you browse a newer compatible export.

Saved values and statuses are shown as supplied. A category missing from
the export is not inferred to be a No. The export does not contain source
PDFs, abstract/conclusion extracts, quote text or full decision history.
Source-page references and available verification flags and metadata are
preserved in the CSV; the complete verification history remains local.
Use the working toolkit for editing and source verification.

The JSON file contains project settings, not a database or paper texts.
No data is uploaded. Website links open only when explicitly selected.
Developed with assistance from GPT-6 Astra.
'''
def b64(text):return base64.b64encode(text.encode('utf-8')).decode('ascii')
def html(csv_text,project=None):
    # Validate basic shape before packaging; the browser validates full CSV syntax.
    rows=list(csv.DictReader(io.StringIO(csv_text.lstrip('\ufeff'))))
    if not rows or not all(r.get('record_id') and r.get('title') for r in rows):raise ValueError('Expected an assessment summary CSV with record_id and title.')
    if len({r['record_id'] for r in rows})!=len(rows):raise ValueError('Duplicate record IDs.')
    page=(STATIC/'index.html').read_text(encoding='utf-8')
    page=page.replace('<title>Literature review toolkit</title>','<title>Corpus explorer</title>').replace('Literature review toolkit</a>','Corpus explorer</a>')
    page=re.sub(r'<script[^>]+src="[^"]+"[^>]*></script>','',page)
    page=re.sub(r'<link[^>]+rel="stylesheet"[^>]*>','',page)
    styles=(STATIC/'style.css').read_text(encoding='utf-8')+'\n'+(HERE.parent/'ui/theme.css').read_text(encoding='utf-8')
    styles+='\n'+(STATIC/'snapshot.css').read_text(encoding='utf-8')
    page=page.replace('</head>',"<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'\"><style>"+styles+'</style></head>')
    scripts='<script type="text/plain" id="snapshot-settings">'+b64(json.dumps(project or {},ensure_ascii=False))+'</script><script type="text/plain" id="snapshot-csv">'+b64(csv_text)+'</script>'
    for name in ['snapshot.js','classification.js','choices.js','reading.js','synthesis-map.js','app.js']:
        scripts+='<script>'+re.sub(r'</script',r'<\\/script',(STATIC/name).read_text(encoding='utf-8'),flags=re.I)+'</script>'
    return page.replace('</body>',scripts+'</body>')
def bundle(csv_text,project=None):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('Corpus explorer.html',html(csv_text,project))
        z.writestr('assessments.csv',csv_text)
        z.writestr('project-settings.json',json.dumps(project or {},ensure_ascii=False,indent=2))
        z.writestr('START HERE.txt',README)
    return buffer.getvalue()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',required=True);p.add_argument('--out',required=True);p.add_argument('--settings');a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);text=Path(a.csv).read_text(encoding='utf-8-sig');project=json.loads(Path(a.settings).read_text(encoding='utf-8-sig')) if a.settings else {}
    data=bundle(text,project)
    with zipfile.ZipFile(io.BytesIO(data)) as z:z.extractall(out)
    (out/'Corpus explorer.zip').write_bytes(data)
    print('Created CSV browser and ZIP:',out)
