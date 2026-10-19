"""Validate explicit final verdicts and observed stock delegation calls, not prose claims."""
import json
from pathlib import Path

def events(path):
 for line in Path(path).read_text().splitlines():
  try:yield json.loads(line)
  except ValueError:continue # CLI banners are not JSON events.

def final_object(path):
 text=''
 for e in events(path):
  m=e.get('message',{})
  for c in m.get('content',[]):
   if c.get('type') in ('toolRequest','toolResponse'):text=''
   elif m.get('role')=='assistant' and c.get('type')=='text':text+=c.get('text','')
 text=text.strip()
 if text.endswith('```') and '```json' in text:text=text.rsplit('```json',1)[1].rsplit('```',1)[0].strip()
 elif text.startswith('```'):text='\n'.join(text.splitlines()[1:-1]).strip()

 try:result=json.loads(text)
 except ValueError:return {}
 return result if isinstance(result,dict) else {}

def delegations(path):
 requests={};done=set()
 for e in events(path):
  for c in e.get('message',{}).get('content',[]):
   if c.get('type')=='toolRequest':
    v=c.get('toolCall',{}).get('value',{})
    if v.get('name','').split('__')[-1]=='delegate':requests[c['id']]=v.get('arguments',{})
   if c.get('type')=='toolResponse' and c.get('toolResult',{}).get('status')=='success':done.add(c['id'])
 return [{'call_id':k,**v,'response_observed':k in done} for k,v in requests.items()]

def native_sessions(path):
 return sorted({e.get('message',{}).get('metadata',{}).get('inference',{}).get('providerSessionId') for e in events(path)}-{None})
