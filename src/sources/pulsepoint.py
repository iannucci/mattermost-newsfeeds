from .base import SourceBase


class PulsePoint(SourceBase):
    bucket = "pulsepoint"

    def poll(self, now_ts: float) -> int:
        agency = self.params.get("agency_id", "43070")
        resp = self.params.get(
            "respond_url", f"https://web.pulsepoint.org/?agencies={agency}"
        )
        bcast = self.params.get(
            "broadcastify", "https://www.broadcastify.com/listen/feed/34259"
        )
        item = {"agency_id": agency, "respond_url": resp, "broadcastify": bcast}
        fp = f"{self.bucket}|{agency}"
        if not self.seen.is_seen(self.bucket, fp):
            self.seen.mark_seen(self.bucket, fp)
            self.post_item(item)
            self.logger.info("[PulsePoint] posted helper links")
            return 1
        return 0
