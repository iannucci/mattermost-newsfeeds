from typing import Any, Dict, List
import math, time
from util.http import http_get
from util.notifier import Notifier
from datetime import datetime, timezone
import pytz


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class SourceBase:
    bucket = "generic"

    def __init__(
        self,
        name: str,
        general_cfg: Dict[str, Any],
        cfg: Dict[str, Any],
        seen,
        logger,
        notifier: Notifier,
    ):
        self.name = name
        self.general_cfg = general_cfg
        self.timezone_str = general_cfg.get("timezone", "America/Los_Angeles")
        self.timezone = pytz.timezone(self.timezone_str)
        self.mattermost_cfg = general_cfg.get("mattermost", {})
        self.cfg = cfg
        self.params = cfg.get("params", {})
        self.log_time_format = general_cfg.get("log_time_format", "%Y/%m/%d %H:%M:%S")
        self.template = cfg.get("template")
        self.seen = seen
        self.logger = logger
        self.notifier = notifier
        self.next_due = 0.0
        self.poll_seconds = max(30, int(cfg.get("poll_seconds", 300)))
        notifier.base = self

    def due(self) -> bool:
        return time.time() >= self.next_due

    def schedule_next(self):
        self.next_due = time.time() + self.poll_seconds

    def fingerprints(self, item: Dict[str, Any]) -> List[str]:
        fid = item.get("id")
        return [f"{self.bucket}|{fid}"] if fid else []

    def post(self, payload: Dict[str, Any]):
        self.notifier.send(
            f"{self.name} — {payload.get('count',0)} new",
            payload,
            override=self.cfg.get("notifier"),
            template=self.template,
        )

    def post_item(self, item: Dict[str, Any]):
        self.notifier.send(
            self.name,
            {"items": [item]},
            override=self.cfg.get("notifier"),
            template=self.template,
        )

    def poll(self, now_ts: float) -> int:
        raise NotImplementedError

    # Now as a datetime object
    def now_dt(self):
        return datetime.now()

    # Uniz timestamp to datetime object
    def unix_to_dt(self, unix):
        return datetime.fromtimestamp(unix)

    # Timezone as a string
    def timezone_str(self):
        return self.params.get("timezone", "America/Los_Angeles")

    # Datetime to string in local timezone
    def dt_utc_to_local_str(self, dt):
        return dt.astimezone(self.timezone).strftime(self.log_time_format)

    # Datetime to string with no forced timezone interpretation
    def dt_str(self, dt):
        return dt.strftime(self.log_time_format)
