from library import intake,load
intake([r['canonical_url'] for r in load('catalog/repositories.json',[])])
