import copy, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import library as l

def data(id=123,name='demo',owner='example'):
    return {'id':id,'name':name,'full_name':f'{owner}/{name}','html_url':f'https://github.com/{owner}/{name}',
      'description':'An agent framework','topics':['agents'],'language':'Python','license':{'spdx_id':'MIT'},'archived':False,'pushed_at':'2026-01-01T00:00:00Z'}

class CatalogTests(unittest.TestCase):
    def test_duplicate_case_and_rename(self):
        rows=[];cats=l.DEFAULT_CATEGORIES
        r=l.upsert(rows,'https://github.com/example/demo',data(),None,cats)
        r['notes']='keep';r['tags']=['mine'];r['description']='custom';r['category']='ai-applications'
        l.upsert(rows,'https://github.com/EXAMPLE/demo.git',data(),None,cats)
        l.upsert(rows,'https://github.com/example/demo',data(name='renamed',owner='newowner'),None,cats)
        self.assertEqual(len(rows),1);self.assertEqual(r['notes'],'keep');self.assertEqual(r['tags'],['mine'])
        self.assertEqual(r['description'],'custom');self.assertEqual(r['category'],'ai-applications')
        self.assertIn('https://github.com/example/demo',r['aliases'])
    def test_new_category_no_code_change(self):
        cats=copy.deepcopy(l.DEFAULT_CATEGORIES);cats['quantum-tools']={'title':'Quantum tools','keywords':['qubit']}
        r=l.new_record('https://github.com/example/quantum');r['upstream_description']='qubit compiler'
        l.classify(r,cats);self.assertEqual(r['category'],'quantum-tools')
        output=l.generated_files([r],cats);self.assertIn('categories/quantum-tools/README.md',output)
    def test_ambiguous_review(self):
        r=l.new_record('https://github.com/example/demo');r['upstream_description']='mcp multi-agent proxy'
        l.classify(r,l.DEFAULT_CATEGORIES);self.assertEqual(r['category'],'other')
    def test_reject_bad_urls(self):
        for url in ['https://evil.com/a/b','https://github.com/a/b/issues','https://x@github.com/a/b','https://github.com/a/..']:
            with self.assertRaises(ValueError):l.normalize(url)
        self.assertEqual(l.normalize('https://github.com/A/b.git?x=1'),'https://github.com/A/b')
    def test_repeated_intake_and_unavailable_recovery(self):
        class Fake:
            broken=False
            def call(self,path):
                if self.broken: raise l.HTTPError('url',404,'missing',{},None)
                if path.endswith('/readme'):return {}
                return data()
        with tempfile.TemporaryDirectory() as tmp,patch.object(l,'ROOT',Path(tmp)):
            api=Fake();u='https://github.com/example/demo'
            l.intake([u,u],api);self.assertEqual(len(l.load('catalog/repositories.json')),1)
            api.broken=True;l.intake([u],api);r=l.load('catalog/repositories.json')[0]
            self.assertEqual(r['status'],'unavailable');self.assertIsNotNone(r['last_verified'])
            self.assertEqual(l.load('intake/pending.json'),[u])
            api.broken=False;l.intake([u],api)
            self.assertEqual(l.load('intake/failed.json'),[]);self.assertEqual(l.load('intake/pending.json'),[])
    def test_renamed_existing_fork_no_post(self):
        class Fake:
            token='test-placeholder'
            def pages(self,path):return [{'fork':True,'owner':{'login':l.OWNER},'full_name':l.OWNER+'/custom'}]
            def call(self,path,method='GET',body=None):
                assert method=='GET','Unexpected mutation'
                if path=='/user':return {'login':l.OWNER}
                return {'fork':True,'parent':{'id':123},'html_url':f'https://github.com/{l.OWNER}/custom'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(l,'ROOT',Path(tmp)):
            rows=[];l.upsert(rows,'https://github.com/example/demo',data(),None,l.DEFAULT_CATEGORIES)
            l.save('catalog/repositories.json',rows);l.fork_all(create=True,api=Fake())
            r=l.load('catalog/repositories.json')[0];self.assertEqual(r['fork_status'],'confirmed');self.assertEqual(r['fork_outcome'],'existing')
    def test_unconfirmed_fork_stays_pending(self):
        class Fake:
            token='test-placeholder'
            def pages(self,path):return []
            def call(self,path,method='GET',body=None):
                if path=='/user':return {'login':l.OWNER}
                if method=='POST':return {'full_name':l.OWNER+'/demo'}
                return {'fork':False,'html_url':f'https://github.com/{l.OWNER}/demo'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(l,'ROOT',Path(tmp)),patch.object(l.time,'sleep'):
            rows=[];l.upsert(rows,'https://github.com/example/demo',data(),None,l.DEFAULT_CATEGORIES)
            l.save('catalog/repositories.json',rows);l.fork_all(create=True,api=Fake())
            r=l.load('catalog/repositories.json')[0];self.assertEqual(r['fork_status'],'pending');self.assertIsNone(r['fork_url'])
    def test_csv_injection_and_escaping(self):
        rows=[];r=l.upsert(rows,'https://github.com/example/demo',data(),None,l.DEFAULT_CATEGORIES)
        r['description']='=HYPERLINK("x")';self.assertIn("'=HYPERLINK",l.csv_text(rows))
        r['description']='a | b\nc';self.assertIn('a &#124; b c',l.generated_files(rows,l.DEFAULT_CATEGORIES)['categories/'+r['category']+'/README.md'])

if __name__=='__main__':unittest.main()
