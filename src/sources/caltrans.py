import xml.etree.ElementTree as ET
from html import unescape as _html_unescape
from util.http import http_get
from .base import SourceBase, km_between

class Caltrans(SourceBase):
    bucket="caltrans"
    def poll(self, now_ts: float)->int:
        lat0=self.general['location']['lat']; lon0=self.general['location']['lon']
        max_km=float(self.params.get('max_km',80.0)); endpoints=self.params.get('endpoints',{}); layer_filter=(self.params.get('layer_filter_prefix') or '').strip()
        headers={'User-Agent': self.general.get('user_agent',''), 'Accept':'application/vnd.google-earth.kml+xml, application/xml, text/xml'}
        new_count=0
        for layer,url in endpoints.items():
            if layer_filter and not layer.startswith(layer_filter): continue
            try:
                xml_text=http_get(url, headers=headers).text
                for it in self._parse_kml(xml_text):
                    lat,lon=it.get('lat'),it.get('lon')
                    if None in (lat,lon): continue
                    d=km_between(lat0,lon0,lat,lon)
                    if d>max_km: continue
                    item=dict(it); item['distance_km']=round(d,1); item['layer']=layer
                    fp=f"{self.bucket}|{layer}|{item.get('name')}|{lat}|{lon}"
                    if self.seen.is_seen(self.bucket, fp): continue
                    self.seen.mark_seen(self.bucket, fp); self.post_item(item); new_count+=1
            except Exception as e:
                self.logger.error(f"[Caltrans] {layer} error: {e}")
        if new_count: self.logger.info(f"[Caltrans] {new_count} new items")
        else: self.logger.debug("[Caltrans] no new items")
        return new_count
    def _parse_kml(self, xml_text: str):
        root=ET.fromstring(xml_text); ns={'k':'http://www.opengis.net/kml/2.2'}; items=[]
        for pm in root.findall('.//Placemark') + root.findall('.//k:Placemark', ns):
            name=self._txt(pm.find('name')) or self._txt(pm.find('{http://www.opengis.net/kml/2.2}name'))
            desc=self._txt(pm.find('description')) or self._txt(pm.find('{http://www.opengis.net/kml/2.2}description'))
            lon=lat=None; coord_text=None
            pt=pm.find('Point') or pm.find('{http://www.opengis.net/kml/2.2}Point')
            if pt is not None:
                c=pt.find('coordinates') or pt.find('{http://www.opengis.net/kml/2.2}coordinates'); coord_text=self._txt(c)
            if coord_text is None:
                for tag in ('LineString','Polygon'):
                    g=pm.find(tag) or pm.find(f'{{http://www.opengis.net/kml/2.2}}{tag}')
                    if g is not None:
                        c=g.find('coordinates') or g.find('{http://www.opengis.net/kml/2.2}coordinates'); coord_text=self._txt(c); break
            if coord_text:
                parts=coord_text.strip().split()
                if parts:
                    first=parts[0].split(',')
                    if len(first)>=2:
                        try: lon=float(first[0]); lat=float(first[1])
                        except ValueError: lon=lat=None
            if desc: desc=_html_unescape(desc).replace('\n',' ').replace('\r',' ')
            items.append({'name':name,'description':desc,'lon':lon,'lat':lat})
        return items
    def _txt(self, e): return e.text.strip() if (e is not None and e.text) else None
