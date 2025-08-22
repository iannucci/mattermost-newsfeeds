# ws5000_handler.py (v2, package-style)
from typing import Dict, Any, Optional
import threading, queue, time, sys

class Handler:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg or {}
        self.mode = str(self.cfg.get('mode', 'http')).lower()
        self._q: 'queue.Queue[Dict[str, Any]]' = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self.mode == 'udp':
            self._thread = threading.Thread(target=self._udp_loop, name='WS5000-UDP', daemon=True)
        else:
            self._thread = threading.Thread(target=self._http_loop, name='WS5000-HTTP', daemon=True)
        self._thread.start()

    def poll(self):
        try:
            return self._q.get_nowait()
        except queue.Empty:
            return None

    def _http_loop(self) -> None:
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import urlsplit, parse_qs, unquote_plus

        http_cfg = self.cfg.get('http', {}) if isinstance(self.cfg, dict) else {}
        host = str(http_cfg.get('host', '0.0.0.0'))
        port = int(http_cfg.get('port', 46000))
        verbose = bool(http_cfg.get('verbose', False))

        outer = self

        class RequestHandler(BaseHTTPRequestHandler):
            def _fields(self):
                split = urlsplit(self.path)
                fields = {k: v[-1] for k, v in parse_qs(split.query, keep_blank_values=True).items()}
                if not fields:
                    tail = (split.path or '').split('/')[-1]
                    if '=' in tail:
                        cand = unquote_plus(tail).replace(';', '&').replace(',', '&')
                        fields = {k: v[-1] for k, v in parse_qs(cand, keep_blank_values=True).items()}
                if self.command == 'POST':
                    ctype = (self.headers.get('Content-Type','').split(';',1)[0] or '').strip().lower()
                    if ctype in ('application/x-www-form-urlencoded','text/plain'):
                        length = int(self.headers.get('Content-Length','0') or 0)
                        body = self.rfile.read(length) if length>0 else b''
                        pq = parse_qs(body.decode('utf-8','ignore'), keep_blank_values=True)
                        fields.update({k: v[-1] for k, v in pq.items()})
                return fields

            def _enqueue(self, method: str):
                msg = {
                    'type': 'http',
                    'fields': self._fields(),
                    'transport': {
                        'src': self.client_address[0],
                        'path': self.path,
                        'method': method,
                        'headers': dict(self.headers),
                        'ts': time.time(),
                    }
                }
                outer._q.put(msg)

            def do_GET(self):
                self._enqueue('GET')
                self.send_response(200); self.end_headers(); self.wfile.write(b'OK')

            def do_POST(self):
                self._enqueue('POST')
                self.send_response(200); self.end_headers(); self.wfile.write(b'OK')

            def log_message(self, fmt, *args):
                if verbose:
                    super().log_message(fmt, *args)

        server = HTTPServer((host, port), RequestHandler)
        try:
            print(f"[ws5000_handler:http] Listening on {host}:{port}", file=sys.stderr, flush=True)
            server.serve_forever(poll_interval=0.5)
        except Exception as e:
            print(f"[ws5000_handler:http] server error: {e}", file=sys.stderr, flush=True)
        finally:
            try: server.server_close()
            except Exception: pass

    def _udp_loop(self) -> None:
        from .ws5000_capture import WS5000BroadcastCapture
        udp_cfg = self.cfg.get('udp', {}) if isinstance(self.cfg, dict) else {}
        iface = udp_cfg.get('iface') or None
        port = int(udp_cfg.get('port', 59387))

        def on_packet(payload: bytes, meta: Dict[str, Any]) -> None:
            self._q.put({'type': 'udp', 'payload': payload, 'transport': meta, 'ts': time.time()})

        print(f"[ws5000_handler:udp] Capture iface={iface or '(auto)'} port={port}", file=sys.stderr, flush=True)
        cap = WS5000BroadcastCapture(dest_port=port, iface=iface, callback=on_packet, debug=True)
        cap.run_blocking()
