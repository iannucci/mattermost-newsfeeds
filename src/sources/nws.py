from util.http import http_get
from .base import SourceBase


class NWS(SourceBase):
    bucket = "nws"

    def poll(self, now_ts: float) -> int:
        api = self.params.get("api_url", "https://api.weather.gov/alerts/active")
        lat = self.general_cfg["location"]["lat"]
        lon = self.general_cfg["location"]["lon"]
        headers = {
            "User-Agent": self.general_cfg.get("user_agent", ""),
            "Accept": "application/geo+json, application/json",
        }
        data = http_get(api, headers=headers, params={"point": f"{lat},{lon}"}).json()
        feats = data.get("features", [])
        new_count = 0
        for f in feats:
            p = f.get("properties", {})
            item = {
                "id": f.get("id"),
                "event": p.get("event"),
                "severity": p.get("severity"),
                "urgency": p.get("urgency"),
                "certainty": p.get("certainty"),
                "headline": p.get("headline"),
                "effective": p.get("effective"),
                "expires": p.get("expires"),
                "areaDesc": p.get("areaDesc"),
                "cap": p.get("cap"),
                "senderName": p.get("senderName"),
            }
            fp = f"{self.bucket}|{item.get('id') or item.get('headline')}"
            if self.seen.is_seen(self.bucket, fp):
                continue
            self.seen.mark_seen(self.bucket, fp)
            self.post_item(item)
            new_count += 1
        if new_count:
            self.logger.info(f"[NWS] {new_count} new alerts")
        else:
            self.logger.debug("[NWS] no new alerts")
        return new_count
