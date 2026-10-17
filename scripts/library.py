"""Catalog engine. Never imports or executes collected repository code."""
import argparse, base64, csv, io, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
ROOT = Path(__file__).resolve().parents[1]
OWNER = 'Swetha-Pandala'
def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def load(path, default=None):
    p = ROOT / path
    return json.loads(p.read_text()) if p.exists() else default

def save(path, data):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(p)

def normalize(value):
    p = urlsplit(value.strip())
    if p.scheme != 'https' or p.hostname != 'github.com' or p.username or p.password or p.port:
        raise ValueError('Expected an HTTPS github.com repository URL')
    parts = p.path.strip('/').split('/')
    if len(parts) != 2: raise ValueError('Use repository root URLs, not file or issue URLs')
    owner, name = parts
    name = name.removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9-]+', owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or name in ('.','..'):
        raise ValueError('Invalid repository name')
    return f'https://github.com/{owner}/{name}'

def parse_urls(text):
    candidates = re.findall(r'https://github\.com/[^\s<>"\]\)]+', text)
    return list(dict.fromkeys(normalize(x.rstrip('.,;')) for x in candidates))

class API:
    def __init__(self): self.token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    def call(self, path, method='GET', body=None):
        if not path.startswith('/') or path.startswith('//'): raise ValueError('Invalid API path')
        headers = {'Accept':'application/vnd.github+json','User-Agent':'ai-resource-library','X-GitHub-Api-Version':'2022-11-28'}
        if self.token: headers['Authorization'] = 'Bearer ' + self.token
        if body is not None: headers['Content-Type'] = 'application/json'
        for attempt in range(4):
            try:
                with urlopen(Request('https://api.github.com'+path, headers=headers, method=method,
                                     data=json.dumps(body).encode() if body is not None else None), timeout=30) as r:
                    return json.load(r)
            except HTTPError as e:
                retry = e.code in (429,500,502,503,504) or (e.code == 403 and (e.headers.get('X-RateLimit-Remaining')=='0' or e.headers.get('Retry-After')))
                if not retry or attempt==3: raise
                delay = float(e.headers.get('Retry-After') or 2**attempt)
                if e.headers.get('X-RateLimit-Remaining')=='0': delay=max(delay,float(e.headers.get('X-RateLimit-Reset','0'))-time.time()+1)
                if delay > 60: raise RuntimeError('GitHub rate limit: rerun after reset; progress is saved') from e
                time.sleep(max(1,delay))
            except (URLError, TimeoutError):
                if attempt==3: raise
                time.sleep(2**attempt)
    def pages(self, path):
        for page in range(1,10001):
            batch = self.call(path+('&' if '?' in path else '?')+f'per_page=100&page={page}')
            yield from batch
            if len(batch)<100: return
        raise RuntimeError('Pagination limit reached; no completeness claim made')

DEFAULT_CATEGORIES = {
 'ai-skills-mcp': {'title':'AI Skills & MCP','keywords':['mcp','model context protocol','agent skills']},
 'ai-applications': {'title':'Complete AI Applications','keywords':['ai application','knowledge base']},
 'multi-agent-systems': {'title':'Agent Frameworks & Multi-Agent Systems','keywords':['agent framework','multi-agent','multiagent']},
 'automations-apis': {'title':'Automation, APIs & Data Extraction','keywords':['workflow automation','web scraping','data orchestration']},
 'llm-gateways-devtools': {'title':'LLM Gateways & Developer Tools','keywords':['llm gateway','proxy','developer tool']},
 'other': {'title':'Needs Classification Review','keywords':[]}}

def classify(record, categories):
    if record.get('category') and record['category'] in categories: return
    text=' '.join([record.get('name',''),record.get('upstream_description') or '',record.get('readme_excerpt') or '', ' '.join(record.get('upstream_topics',[]))]).lower()
    hits=[key for key,c in categories.items() if any(k.lower() in text for k in c.get('keywords',[]))]
    record['category'] = hits[0] if len(hits)==1 else 'other'
    record['classification_status'] = 'suggested' if len(hits)==1 else 'needs_review'
    record['classification_evidence'] = 'Keyword suggestion; review README before approving.'

def new_record(url):
    return {'id':None,'name':url.rsplit('/',1)[-1],'original_url':url,'canonical_url':url,'aliases':[],
      'fork_url':None,'fork_status':'pending','fork_error':'Fork not yet checked or authorized by runtime.',
      'description':None,'upstream_description':None,'category':None,'tags':[], 'upstream_topics':[],
      'license':None,'license_url':None,'language':None,'technologies':[], 'compatible_ai_tools':[],
      'use_cases':[], 'installation_requirements':[], 'notes':'','status':'unverified','fork_outcome':None,
      'date_added':now(),'last_verified':None,'last_attempted':None,'readme_url':None,'documentation_url':None,
      'classification_status':'needs_review','readme_excerpt':None,'readme_error':None,'metadata_error':None,
      'upstream_pushed_at':None,'upstream_changed':False,'previous_names':[]}

def merge_metadata(record, data, readme=None):
    old=record.get('canonical_url'); canonical=data['html_url']
    if old and old.lower()!=canonical.lower():
        record['aliases']=list(dict.fromkeys(record.get('aliases',[])+[old]))
        record['previous_names']=list(dict.fromkeys(record.get('previous_names',[])+[old.removeprefix('https://github.com/')]))
    before=record.get('upstream_pushed_at')
    record.update(id=data['id'], name=data['name'],canonical_url=canonical,
        upstream_description=data.get('description'),upstream_topics=data.get('topics',[]),
        license=(data.get('license') or {}).get('spdx_id'), license_url=(data.get('license') or {}).get('url'),
        language=data.get('language'),status='archived' if data.get('archived') else 'active',
        last_verified=now(),last_attempted=now(),metadata_error=None,
        documentation_url=data.get('homepage') or None,upstream_pushed_at=data.get('pushed_at'),
        upstream_changed=bool(before and before!=data.get('pushed_at')))
    if readme and readme.get('content'):
        text=base64.b64decode(readme['content']).decode('utf-8',errors='replace')
        record.update(readme_url=readme.get('html_url'),readme_excerpt=text[:12000],readme_error=None)
    # Never alter user descriptions, notes, tags, technologies, or categories on refresh.

def upsert(rows, url, data, readme, categories):
    existing=next((r for r in rows if r.get('id')==data['id']),None)
    provisional=next((r for r in rows if r.get('id') is None and url.lower() in [r['original_url'].lower(),r['canonical_url'].lower()]),None)
    record=existing or provisional or new_record(url)
    if existing and provisional and existing is not provisional:
        # A previously unavailable URL now resolves to a known stable ID. Preserve notes.
        for field in ('tags','use_cases','technologies','compatible_ai_tools','installation_requirements'):
            existing[field]=list(dict.fromkeys(existing.get(field,[])+provisional.get(field,[])))
        if provisional.get('notes'): existing['notes']+='\n'+provisional['notes']
        if provisional.get('description') and not existing.get('description'): existing['description']=provisional['description']
        rows.remove(provisional)
    if record not in rows: rows.append(record)
    if url.lower()!=record['original_url'].lower(): record['aliases']=list(dict.fromkeys(record.get('aliases',[])+[url]))
    merge_metadata(record,data,readme); classify(record,categories)
    record['readme_excerpt'] = None  # retain source links, not copied upstream README text
    return record

def intake(urls, api=None):
    api=api or API(); rows=load('catalog/repositories.json',[]); cats=load('catalog/categories.json',DEFAULT_CATEGORIES)
    pending=load('intake/pending.json',[]); processed=load('intake/processed.json',[]); failed=load('intake/failed.json',[])
    for supplied in urls:
        url=None
        try:
            url=normalize(supplied)
            if url not in pending: pending.append(url)
            save('intake/pending.json',pending)
            prior=next((r for r in rows if url.lower() in [x.lower() for x in [r['original_url'],r['canonical_url']]+r.get('aliases',[])]),None)
            path=f"/repositories/{prior['id']}" if prior and prior.get('id') else '/repos/'+url.removeprefix('https://github.com/')
            data=api.call(path)
            readme=None; readme_error=None
            try: readme=api.call('/repos/'+data['full_name']+'/readme')
            except Exception as e: readme_error=str(e)
            record=upsert(rows,url,data,readme,cats); record['readme_error']=readme_error
            if url not in processed: processed.append(url)
            pending=[x for x in pending if x!=url]; failed=[x for x in failed if x['url']!=url]
        except Exception as e:
            failed=[x for x in failed if x['url']!=supplied]+[{'url':supplied,'error':str(e),'attempted_at':now()}]
            if url:
                record=next((r for r in rows if r['original_url'].lower()==url.lower() or r['canonical_url'].lower()==url.lower()),None)
                if record is None: record=new_record(url); rows.append(record); classify(record,cats)
                record.update(last_attempted=now(),metadata_error=str(e))
                if isinstance(e,HTTPError) and e.code in (404,410): record['status']='unavailable'
        save('catalog/repositories.json',rows); save('catalog/categories.json',cats)
        save('intake/pending.json',pending); save('intake/processed.json',processed); save('intake/failed.json',failed)
    generate()

def fork_all(create=False, api=None):
    api=api or API(); rows=load('catalog/repositories.json',[])
    if not api.token:
        raise RuntimeError('Set GH_TOKEN with repository creation/fork permissions; no token is stored. Forks remain pending.')
    if api.call('/user')['login'].lower()!=OWNER.lower(): raise RuntimeError('Authenticated account must be '+OWNER)
    # Include renamed forks by scanning all owned repositories, not only expected names.
    candidates=[r for r in api.pages('/user/repos?affiliation=owner') if r.get('fork') and r['owner']['login'].lower()==OWNER.lower()]
    parents={}
    for r in candidates:
        detail=api.call('/repos/'+r['full_name'])
        for parent in ('parent','source'):
            if detail.get(parent): parents[detail[parent]['id']]=detail
    for record in rows:
        if record['id'] is None: continue
        try:
            match=parents.get(record['id']); created=False
            if not match and create:
                result=api.call('/repos/'+record['canonical_url'].removeprefix('https://github.com/')+'/forks','POST',{'default_branch_only':False})
                created=True
                for attempt in range(4):
                    try:
                        candidate=api.call('/repos/'+result['full_name'])
                        if candidate.get('fork') and any(candidate.get(k,{}).get('id')==record['id'] for k in ('parent','source')):
                            match=candidate; break
                    except HTTPError as e:
                        if e.code!=404: raise
                    time.sleep(2**attempt)
            if match:
                record.update(fork_url=match['html_url'],fork_status='confirmed',fork_error=None,
                              fork_outcome='created' if created else record.get('fork_outcome') or 'existing')
                parents[record['id']]=match
            else:
                record.update(fork_url=None,fork_status='pending',fork_error='Creation accepted, awaiting GitHub verification; rerun.' if created else 'No owned fork found; run with --create to authorize creation.')
        except Exception as e: record.update(fork_status='failed',fork_error=str(e),fork_url=None)
        save('catalog/repositories.json',rows)
    generate()

CSV_FIELDS=['id','name','original_url','canonical_url','fork_url','description','category','tags','license','language','technologies','compatible_ai_tools','use_cases','status','fork_status','date_added','last_verified','readme_url','documentation_url']
def csv_text(rows):
    out=io.StringIO(newline=''); w=csv.DictWriter(out,fieldnames=CSV_FIELDS,lineterminator='\n');w.writeheader()
    for r in sorted(rows,key=lambda r:r['canonical_url'].lower()):
        d={k:r.get(k) for k in CSV_FIELDS};d['description']=r.get('description') or r.get('upstream_description')
        for k,v in d.items():
            if isinstance(v,list): d[k]='; '.join(v)
            elif isinstance(v,str) and v.startswith(('=','+','-','@')):d[k]="'"+v
        w.writerow(d)
    return out.getvalue()
def md(text):
    import html
    return html.escape(str(text or 'Unknown')).replace('|','&#124;').replace('\n',' ').replace('[','&#91;').replace(']','&#93;')
def generated_files(rows,cats):
    output={'catalog/repositories.csv':csv_text(rows)}
    verified=max((r['last_verified'] for r in rows if r.get('last_verified')),default='Not verified')
    home=['# AI Resource Library','','A curated, continuously expandable collection of AI skills, MCP servers, agents, applications, automation tools, and open-source developer resources.', '', f'Maintained by {OWNER}. Upstream code is not copied or executed.','',f'**Repositories: {len(rows)} · Last successful metadata verification: {verified}**','',
          'Search [the CSV catalog](catalog/repositories.csv) or use `python scripts/search.py QUERY`. Category pages contain full repository tables.','',
          '| Category | Repositories |','| --- | ---: |']
    for key,cat in cats.items():
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',key):raise ValueError('Unsafe category slug')
        selected=sorted([r for r in rows if r['category']==key],key=lambda r:r['name'].lower())
        home.append(f'| [{md(cat["title"])}](categories/{key}/README.md) | {len(selected)} |')
        lines=[f'# {md(cat["title"])}','',f'{len(selected)} repositories. [All categories](../../README.md).','', '| Repository | Description | Fork | License | Tags | Status |','| --- | --- | --- | --- | --- | --- |']
        for r in selected:
            fork=f'[Fork]({r["fork_url"]})' if r['fork_status']=='confirmed' else md(r['fork_status'])
            lines.append(f'| [{md(r["name"])}]({r["canonical_url"]}) | {md(r.get("description") or r.get("upstream_description"))} | {fork} | {md(r["license"])} | {md(", ".join(r["tags"]+r.get("upstream_topics",[])))} | {md(r["status"])} |')
        output[f'categories/{key}/README.md']='\n'.join(lines)+'\n'
    home+=['','## Add resources','', 'Submit the **Add repositories** issue form, or run `python scripts/add_repositories.py --file links.txt`. Only owner-authored issues are processed automatically. New chat messages do not trigger Actions.','',
           'See [setup and intake](docs/how-to-add.md), [usage](docs/how-to-use.md), [maintenance](docs/maintenance.md), and [licensing](docs/licensing.md).','',
           '## Attribution','', 'All linked projects belong to their upstream authors. Forking does not change their licenses or grant additional reuse rights. Unknown and NOASSERTION licenses require review.','',
           'Generated from `catalog/repositories.json`; edit the catalog, not generated tables.']
    template_path = Path(__file__).resolve().parents[1] / 'docs/templates/README.md.template'
    if template_path.exists():
        table = ['| Collection | Focus | Resources |', '| :--- | :--- | ---: |']
        for key, cat in cats.items():
            count = sum(r['category'] == key for r in rows)
            table.append(f'| [{md(cat["title"])}](categories/{key}/README.md) | {md(cat.get("description") or cat["title"])} | **{count}** |')
        values = {
            'TOTAL': str(len(rows)),
            'FORKS': str(sum(r['fork_status'] == 'confirmed' for r in rows)),
            'UNCONFIRMED': str(sum(r['fork_status'] != 'confirmed' for r in rows)),
            'CATEGORIES': str(len({r['category'] for r in rows})),
            'REVIEW': str(sum(r.get('classification_status') != 'reviewed' for r in rows)),
            'VERIFIED': verified,
            'CATEGORY_TABLE': '\n'.join(table),
        }
        rendered = template_path.read_text()
        for key, value in values.items():
            rendered = rendered.replace('{{' + key + '}}', value)
        output['README.md'] = rendered
    else:
        output['README.md']='\n'.join(home)+'\n'
    return output

def generate():
    for name,content in generated_files(load('catalog/repositories.json',[]),load('catalog/categories.json',DEFAULT_CATEGORIES)).items():
        p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)

def validate():
    import jsonschema
    rows=load('catalog/repositories.json',[]); cats=load('catalog/categories.json',{})
    jsonschema.validate(rows,load('catalog/schema.json'))
    ids=[r['id'] for r in rows if r['id'] is not None];assert len(ids)==len(set(ids)),'Duplicate stable IDs'
    urls=[r['canonical_url'].lower() for r in rows];assert len(urls)==len(set(urls)),'Duplicate URLs'
    for r in rows:
        assert r['category'] in cats, 'Unknown category'
        normalize(r['canonical_url']);normalize(r['original_url'])
        assert r['fork_status']!='confirmed' or (r['fork_url'] and r['id']), 'Unverified fork'
    for name,content in generated_files(rows,cats).items():assert (ROOT/name).read_text()==content,'Stale generated file: '+name
    initial=load('intake/initial.json',[])
    known={u.lower() for r in rows for u in [r['original_url'],r['canonical_url']]+r.get('aliases',[])}
    assert all(u.lower() in known for u in initial),'Missing initial entries'
    print(f'PASS: {len(rows)} records, {len(cats)} categories, schema, unique IDs/URLs, initial collection, CSV and indexes')
