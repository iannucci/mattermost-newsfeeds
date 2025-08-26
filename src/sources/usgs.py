from util.http import http_get
from .base import SourceBase, km_between

# from datetime import datetime, timezone


class USGS(SourceBase):
    bucket = "usgs"

    def poll(self, now_ts: float) -> int:
        feed = self.params.get(
            "feed_url",
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
        )
        lat0 = self.general_cfg["location"]["lat"]
        lon0 = self.general_cfg["location"]["lon"]
        max_mi = float(self.params.get("max_mi", 100.0))
        data = http_get(
            feed, headers={"User-Agent": self.general_cfg.get("user_agent", "")}
        ).json()
        feats = data.get("features", [])
        new_count = 0
        for f in feats:
            props = f.get("properties", {})
            geom = f.get("geometry", {}) or {}
            coords = geom.get("coordinates", [None, None, None])
            lon, lat, depth = coords[0], coords[1], coords[2]
            if None in (lat, lon):
                continue
            dist = km_between(lat0, lon0, lat, lon) * 0.621371  # to miles
            if dist > max_mi:
                continue

            self.logger.debug(f"[USGS] Earthquake data: {f}")
            self.logger.debug(f'[USGS] Time: {props.get("time")}')

            unix_ts = int(
                props.get("time", 0) / 1000
            )  # time is of format 1756070780800
            dt = self.unix_to_dt(unix_ts)
            timestamp_local = (
                self.ts_local_string
            )  # datetime.astimezone(self.timezone).isoformat()

            item = {
                "id": f.get("id"),
                "timestamp_local": timestamp_local,
                "mag": props.get("mag"),
                "place": props.get("place"),
                "url": props.get("url"),
                "lat": lat,
                "lon": lon,
                "depth_km": depth,
                "distance_mi_from_origin": round(dist, 1),
            }
            fp = f"{self.bucket}|{item['id']}"
            if self.seen.is_seen(self.bucket, fp):
                continue
            self.seen.mark_seen(self.bucket, fp)
            self.post_item(item)
            new_count += 1
        if new_count:
            self.logger.info(f"[USGS] {new_count} new earthquake report(s)")
        else:
            self.logger.debug("[USGS] no new quakes")
        return new_count
