# ambient_weather.py (v2, package-style)
from typing import Dict, Any
import json, sys

from util.ws5000_handler import Handler
from util.ws5000_decode import WS5000Decoder
from .base import SourceBase
from util.notifier import Notifier

class AmbientWeather(SourceBase):
    def __init__(self, name: str, cfg: Dict[str, Any], general: Dict[str, Any], seen, logger, notifier: Notifier) -> None:
        super().__init__(name, cfg, general, seen, logger, notifier)
        self.handler = Handler(self.cfg, logger)
        self.handler.start()
        self.decoder = WS5000Decoder(self.params)

    def _pretty(self) -> bool:
        mode = str(self.cfg.get('mode', 'http')).lower()
        section = self.cfg.get(mode, {}) if isinstance(self.cfg, dict) else {}
        return bool(section.get('pretty', False))

    def poll(self, now_ts: float) -> int:
        """Drain queued messages.  For the most recent, decode to dict
        Returns the number of messages processed.
        """
        processed = 0
        pretty = self._pretty()
        last_msg = None
        while True:
            msg = self.handler.poll()
            if not msg:
                break
            else:
                last_msg = msg
                processed += 1
        if last_msg:
            if last_msg.get('type') == 'http':
                fields = last_msg.get('fields', {})
                item = self.decoder.normalize_fields(fields)
                self.post_item(item)
                sys.stdout.flush()
            elif last_msg.get('type') == 'udp':
                payload = last_msg.get('payload', b'')
                rec = self.decoder.decode(payload)
                rec['_transport'] = last_msg.get('transport', {})
                self.logger.debug(json.dumps(rec, indent=2 if pretty else None, ensure_ascii=False))
                sys.stdout.flush()
            else:
                pass
        self.logger.info(f"[AmbientWeather] processed {processed} message(s)")
        return processed
