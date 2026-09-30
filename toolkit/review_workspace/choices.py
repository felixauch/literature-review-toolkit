"""Validation of configurable single/multiple-choice extraction fields."""
def validate_spec(spec):
    if spec.get('type','text') not in ('text','single','multi'):raise ValueError('Unknown field type')
    if spec.get('type','text')=='text':return
    options=spec.get('options',[])
    if not isinstance(options,list) or not options or len(options)>40 or any(not isinstance(x,str) or not x.strip() or '\n' in x or ';' in x for x in options) or len(options)!=len(set(options)):
        raise ValueError('Choice fields need unique options without semicolons or line breaks')
    if any(x not in options for x in spec.get('exclusive_options',[])):raise ValueError('Exclusive options must be configured choices')

def selection(spec,raw):
    if not isinstance(raw,list) or any(not isinstance(v,str) for v in raw) or len(raw)!=len(set(raw)):raise ValueError('Invalid selection')
    if any(v not in spec['options'] for v in raw):raise ValueError('Choose a configured option')
    if spec['type']=='single' and len(raw)>1:raise ValueError('Choose one option')
    if len(raw)>1 and any(v in spec.get('exclusive_options',[]) for v in raw):raise ValueError('This option cannot be combined with other choices')
    return [v for v in spec['options'] if v in raw]
