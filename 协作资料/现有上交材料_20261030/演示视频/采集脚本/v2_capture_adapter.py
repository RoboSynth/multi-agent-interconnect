"""Attach to an already authorized transport; never starts consumers or changes leases."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

ROLE_CODES={'application':'A02','database':'A03','database-backup':'A04','ops':'A05','verification':'A06','onboarding':'A07'}

class V2Capture:
    def __init__(self, output, config):
        self.output=Path(output)
        self.output.mkdir(parents=True,exist_ok=True)
        self.aliases={config['leader']['aic']:'A01'}
        for role,values in config.get('trusted_participant_aics',{}).items():
            for index,identity in enumerate(values):
                name='database-backup' if role=='database' and index>0 else role
                self.aliases[identity]=ROLE_CODES[name]
        self.discovery=[]
        self.descriptions={}
        self.started_at=datetime.now(timezone.utc).isoformat()
        self.started_monotonic=time.monotonic()
        self.cast=(self.output/'terminal.cast').open('w',encoding='utf-8',newline='\n')
        self.cast.write(json.dumps({'version':2,'width':100,'height':30,'timestamp':int(time.time()),
            'title':'Live ADP discovery and describe capture','env':{'TERM':'xterm-256color'}})+'\n')
        self.emit('V2 capture started: actual discovery and capability responses')

    def alias(self, value):
        return self.aliases.get(value) or 'EXT-'+hashlib.sha256(value.encode()).hexdigest()[:12].upper()

    def clean(self, value, parent=None):
        if isinstance(value,dict):
            result={}
            for key,item in value.items():
                if key.lower() in {'private_key','privatekey','password','secret','authorization','certificate_pem','cert_pem'}:
                    result[key]='[removed]'
                elif parent=='provider' and isinstance(item,str):
                    result[key]='项目团队'
                else:
                    result[self.clean(key)]=self.clean(item,key)
            return result
        if isinstance(value,list): return [self.clean(item,parent) for item in value]
        if not isinstance(value,str): return value
        for identity,alias in sorted(self.aliases.items(),key=lambda item:len(item[0]),reverse=True):
            value=value.replace(identity,alias)
        value=re.sub(r'1\.2\.156\.3088\.1\.[A-Za-z0-9.]+',lambda match:self.alias(match.group()),value)
        value=re.sub(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])','[address removed]',value)
        value=re.sub(r'(?i)[A-Z]:[\\/][^\r\n"<>]+','[local path removed]',value)
        value=re.sub(r'/(?:home|Users)/[^\s"<>]+','[user path removed]',value)
        return value

    def save(self,name,value):
        (self.output/name).write_text(json.dumps(self.clean(value),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def emit(self,line):
        line=self.clean(line)
        print(line,flush=True)
        self.cast.write(json.dumps([round(time.monotonic()-self.started_monotonic,6),'o',line+'\r\n'],ensure_ascii=False)+'\n')
        self.cast.flush()

    def attach(self,transport):
        original=transport.on_event
        def on_event(row):
            if original: original(row)
            event=row.get('event')
            if event=='official_discovery':
                self.discovery.append({'received_at_utc':datetime.now(timezone.utc).isoformat(),**row})
                self.save('adp-response.json',{'source':'fresh cloud ADP requests in this run','responses':self.discovery})
                self.emit('ADP response received: '+str(row.get('skill_id')))
            elif event=='adp_participant_confirmed':
                role=ROLE_CODES[row['role']]
                self.record_description(role,row['description'])
            elif event in {'official_discovery_retry','official_discovery_failed','capability_confirmation_failed','participant_not_confirmed'}:
                self.emit('V2 observed '+str(event)+' '+str(row.get('error_class') or row.get('status_code') or ''))
        transport.on_event=on_event

    def record_description(self,role,description):
        record={'received_at_utc':datetime.now(timezone.utc).isoformat(),'role':role,'description':description}
        self.descriptions[role]=record
        self.save('describe-'+role+'.json',record)
        self.emit('DESCRIBE response confirmed: '+role)

    def finish(self,status='completed',error_class=None):
        self.emit('V2 capture '+status)
        self.save('capture.json',{'started_at_utc':self.started_at,'finished_at_utc':datetime.now(timezone.utc).isoformat(),
            'status':status,'error_class':error_class,'discovery_responses':len(self.discovery),
            'described_roles':sorted(self.descriptions),'terminal_time_source':'monotonic elapsed at actual emitted stdout',
            'terminal_content':'actual capture-adapter stdout; no fabricated command inputs',
            'consumer_management':'provided by the enclosing authorized leased batch; adapter starts no consumer'})
        self.cast.close()
