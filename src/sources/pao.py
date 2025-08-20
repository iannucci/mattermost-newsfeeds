from bs4 import BeautifulSoup
from util.http import http_get
from .base import SourceBase

class PAO(SourceBase):
    bucket='pao'
    def poll(self, now_ts: float)->int:
        url=self.params.get('news_url','https://www.paloaltoonline.com/news/'); max_items=int(self.params.get('max_items',15))
        headers={'User-Agent': self.general.get('user_agent',''), 'Accept':'text/html'}
        html=http_get(url, headers=headers).text; soup=BeautifulSoup(html,'html.parser'); origin=url.split('/news')[0].rstrip('/')
        new_count=0
        for a in soup.find_all('a', href=True):
            hdr=a.find(['h2','h3'])
            if not hdr: continue
            title=hdr.get_text(strip=True); href=a['href']
            if not title or not href: continue
            link=(origin + href) if href.startswith('/') else (href if href.startswith('http') else None)
            if not link: continue
            item={'title':title,'link':link}
            fp=f"{self.bucket}|{title}|{link}"
            if self.seen.is_seen(self.bucket, fp): continue
            self.seen.mark_seen(self.bucket, fp); self.post_item(item); new_count+=1
            if new_count>=max_items: break
        if new_count: self.logger.info(f"[PAO] {new_count} new stories")
        else: self.logger.debug("[PAO] no new stories")
        return new_count
