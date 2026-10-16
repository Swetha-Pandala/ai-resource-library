import argparse,json
from library import intake,load,parse_urls
p=argparse.ArgumentParser();p.add_argument('urls',nargs='*');p.add_argument('--file');p.add_argument('--event')
a=p.parse_args();urls=a.urls
if a.file:
    text=open(a.file).read();urls+=json.loads(text) if a.file.endswith('.json') else parse_urls(text)
if a.event:
    event=json.load(open(a.event));issue=event['issue']
    if issue['user']['login'].lower()!='swetha-pandala': raise SystemExit('Only owner-authored issues are authorized')
    if not issue['title'].startswith('[Intake]'): raise SystemExit('Not an intake issue')
    urls+=parse_urls(issue.get('body') or '')
if not urls: urls=load('intake/pending.json',[])
intake(urls)
