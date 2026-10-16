import sys,json
from library import load
query=' '.join(sys.argv[1:]).lower()
for r in load('catalog/repositories.json',[]):
    if query in json.dumps(r).lower(): print(r['name']+' | '+r['category']+' | '+r['canonical_url'])
