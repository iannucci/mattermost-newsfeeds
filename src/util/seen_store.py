import json, time, os
from typing import Dict
class SeenStore:
    def __init__(self, path: str, ttl_days: int = 7):
        self.path=path; self.ttl_seconds=int(ttl_days*86400); self.data: Dict[str, Dict[str,int]]={}; self._load()
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path,"r",encoding="utf-8") as f: self.data=json.load(f)
            except Exception: self.data={}
        else: self.data={}
    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path,"w",encoding="utf-8") as f: json.dump(self.data,f,ensure_ascii=False,indent=2)
    def purge_old(self):
        now=int(time.time()); cutoff=now-self.ttl_seconds; changed=False
        for bucket,mp in list(self.data.items()):
            for fp,ts in list(mp.items()):
                if ts<cutoff: del mp[fp]; changed=True
            if not mp: del self.data[bucket]; changed=True
        if changed: self.save()
    def mark_seen(self, bucket: str, fingerprint: str):
        now=int(time.time()); b=self.data.setdefault(bucket,{}); b[fingerprint]=now; self.save()
    def is_seen(self, bucket: str, fingerprint: str) -> bool:
        return fingerprint in self.data.get(bucket, {})
