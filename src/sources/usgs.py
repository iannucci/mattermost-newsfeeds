import datetime as dt
from util.http import http_get
from .base import SourceBase, km_between

class USGS(SourceBase):
    bucket="usgs"
    def poll(self, now_ts: float)->int:
        feed=self.params.get("feed_url","https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson")
        lat0=self.general["location"]["lat"]; lon0=self.general["location"]["lon"]; max_km=float(self.params.get("max_km",150.0))
        data=http_get(feed, headers={"User-Agent": self.general.get("user_agent","")}).json()
        feats=data.get("features",[]); new_count=0
        for f in feats:
            props=f.get("properties",{}); geom=f.get("geometry",{}) or {}; coords=geom.get("coordinates",[None,None,None])
            lon,lat,depth=coords[0],coords[1],coords[2]
            if None in (lat,lon): continue
            dist=km_between(lat0,lon0,lat,lon)
            if dist>max_km: continue
            item={"id":f.get("id"),"time":(dt.datetime.utcfromtimestamp(props.get("time",0)/1000).isoformat()+"Z") if props.get("time") else None,
                  "mag":props.get("mag"),"place":props.get("place"),"url":props.get("url"),
                  "lat":lat,"lon":lon,"depth_km":depth,"distance_km_from_origin":round(dist,1)}
            fp=f"{self.bucket}|{item['id']}"
            if self.seen.is_seen(self.bucket, fp): continue
            self.seen.mark_seen(self.bucket, fp); self.post_item(item); new_count+=1
        if new_count: self.logger.info(f"[USGS] {new_count} new quakes")
        else: self.logger.debug("[USGS] no new quakes")
        return new_count
