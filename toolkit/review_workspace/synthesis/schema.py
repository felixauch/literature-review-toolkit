FIELDS=[]
FIELD_MAP={}
GROUPS=[]
STATES=['unchecked','recorded','not_reported','not_applicable','unclear']
DOMAIN_FIELDS=[]
DOMAIN_SPECS=[]
def configure(project):
    from project_setup import validate
    validate(project,'synthesis')
    FIELDS[:]=project['fields'];FIELD_MAP.clear();FIELD_MAP.update({f['id']:f for f in FIELDS})
    GROUPS[:]=list(dict.fromkeys(f['group'] for f in FIELDS))
    DOMAIN_SPECS[:]=project.get('domain_notes',[]);DOMAIN_FIELDS[:]=[f['id'] for f in DOMAIN_SPECS]
def blank():
    return {'reviewer':'','fields':{f['id']:{'state':'unchecked','value':'','pages':'','evidence':[],'choices':[]} for f in FIELDS},'verified':False}
