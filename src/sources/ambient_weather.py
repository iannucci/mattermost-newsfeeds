# ambient_weather.py (v2, package-style)
from typing import Dict, Any
import json, sys

from .ws5000_handler import Handler
from .ws5000_decode import WS5000Decoder
from .base import SourceBase
from util.notifier import Notifier

class AmbientWeather(SourceBase):
    def __init__(self, name: str, cfg: Dict[str, Any], general: Dict[str, Any], seen, logger, notifier: Notifier) -> None:
        super().__init__(name, cfg, general, seen, logger, notifier)
        self.handler = Handler(self.cfg)
        self.handler.start()
        self.decoder = WS5000Decoder()

    def _pretty(self) -> bool:
        mode = str(self.cfg.get('mode', 'http')).lower()
        section = self.cfg.get(mode, {}) if isinstance(self.cfg, dict) else {}
        return bool(section.get('pretty', False))

    def poll(self, now_ts: float) -> int:
        """Drain queued messages, decode to dicts, and print JSON (one line per record).
        Returns the number of messages processed.
        """
        processed = 0
        pretty = self._pretty()
        while True:
            msg = self.handler.poll()
            if not msg:
                break
            if msg.get('type') == 'http':
                fields = msg.get('fields', {})
                rec = self.decoder.normalize_fields(fields)
                # rec['_transport'] = msg.get('transport', {})
                # print(json.dumps(rec, indent=2 if pretty else None, ensure_ascii=False))
                # self.logger.info(f"[AmbientWeather] {layer} item description: {item['desc']}")
                self.post_item(rec)
                sys.stdout.flush()
            elif msg.get('type') == 'udp':
                payload = msg.get('payload', b'')
                rec = self.decoder.decode(payload)
                rec['_transport'] = msg.get('transport', {})
                print(json.dumps(rec, indent=2 if pretty else None, ensure_ascii=False))
                sys.stdout.flush()
            else:
                pass
            processed += 1
        return processed
