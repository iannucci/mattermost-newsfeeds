# ws5000_capture.py
from typing import Callable, Optional, Dict, Any
import sys
from scapy.all import sniff, UDP, Raw, IP  # requires sudo on macOS for pcap


class WS5000BroadcastCapture:
    """Scapy/pcap blocking capture of WS-5000 UDP broadcasts."""

    def __init__(
        self,
        dest_port: int = 59387,
        iface: Optional[str] = None,
        callback: Optional[Callable[[bytes, Dict[str, Any]], None]] = None,
        debug: bool = True,
    ) -> None:
        self.dest_ip = "255.255.255.255"
        self.dest_port = dest_port
        self.iface = iface
        self.callback = callback
        self.debug = debug
        self.bpf = f"udp and dst host {self.dest_ip}"  # port filtered in _on_packet

    def run_blocking(self) -> None:
        print(
            f"[ws5000_capture] sniff start iface={self.iface or '(auto)'} BPF='{self.bpf}' filter_dport={self.dest_port}",
            file=sys.stderr,
            flush=True,
        )
        try:
            sniff(filter=self.bpf, iface=self.iface, store=False, prn=self._on_packet)
        except Exception as e:
            print(
                f"[ws5000_capture] ERROR starting sniff: {e}",
                file=sys.stderr,
                flush=True,
            )

    def _on_packet(self, pkt) -> None:
        if not (IP in pkt and UDP in pkt):
            return
        ip = pkt[IP]
        udp = pkt[UDP]
        if int(udp.dport) != self.dest_port:
            return
        payload = bytes(pkt[Raw].load) if Raw in pkt else b""
        meta = {
            "src_ip": ip.src,
            "src_port": int(udp.sport),
            "dst_ip": ip.dst,
            "dst_port": int(udp.dport),
        }
        if self.debug:
            print(
                f"[ws5000_capture] pkt {meta['src_ip']}:{meta['src_port']} -> {meta['dst_ip']}:{meta['dst_port']} payload={len(payload)}B",
                file=sys.stderr,
                flush=True,
            )
        if self.callback:
            try:
                self.callback(payload, meta)
            except Exception as e:
                print(
                    f"[ws5000_capture] callback error: {e}", file=sys.stderr, flush=True
                )
