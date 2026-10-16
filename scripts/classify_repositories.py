from library import load,save,classify,generate
rows=load('catalog/repositories.json',[]);cats=load('catalog/categories.json',{})
for r in rows: classify(r,cats)
save('catalog/repositories.json',rows);generate()
