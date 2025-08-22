# ws5000_decode.py
from typing import Dict, Any, Optional
from urllib.parse import parse_qs, urlsplit, unquote_plus
from datetime import datetime, timezone
import re

_QS_RUN_RE   = re.compile(r'([A-Za-z0-9_]+=[^&\s]+(?:[&;,\s]+[A-Za-z0-9_]+=[^&\s]+)+)')
_PAIR_RE     = re.compile(r'([A-Za-z0-9_]+)\s*=\s*([^&;,\s]+)')

class WS5000Decoder:
    """Decode WS-5000 UDP/HTTP payloads into a normalized dict (robust)."""

    # -------- parsing --------
    def _safe_text(self, raw: bytes) -> str:
        try:
            return raw.decode('utf-8', errors='strict')
        except UnicodeDecodeError:
            return raw.decode('latin-1', errors='ignore')

    def _ascii_only(self, text: str) -> str:
        out = []
        for ch in text:
            o = ord(ch)
            if 32 <= o <= 126 or ch in '\r\n\t':
                out.append(ch)
            else:
                out.append(' ')
        return ''.join(out)

    def _extract_candidate(self, text: str) -> str:
        if '?' in text:
            frag = text.split('?', 1)[1]
            frag = frag.splitlines()[0].strip()
            if '=' in frag:
                return frag
        m = _QS_RUN_RE.search(text)
        if m:
            return m.group(1)
        first = text.splitlines()[0]
        if '=' in first:
            return first.strip()
        return ''

    def parse_fields(self, raw: bytes) -> Dict[str, str]:
        text = self._safe_text(raw)
        ascii_text = self._ascii_only(text)
        candidate = self._extract_candidate(ascii_text)
        if candidate:
            norm = candidate.replace(';', '&').replace(',', '&')
            if norm.startswith('/'):
                norm = urlsplit(norm).query or norm
            parsed = {k: v[-1] for k, v in parse_qs(norm, keep_blank_values=True).items()}
            if parsed:
                return {k: unquote_plus(v) for k, v in parsed.items()}
        pairs = dict(_PAIR_RE.findall(ascii_text))
        if pairs:
            return {k: unquote_plus(v) for k, v in pairs.items()}
        return {}

    # Public API
    def decode(self, raw: bytes) -> Dict[str, Any]:
        fields = self.parse_fields(raw)
        return self._normalize(fields)

    def normalize_fields(self, fields: Dict[str, str]) -> Dict[str, Any]:
        """Normalize a pre-parsed dict of fields into the standard record."""
        return self._normalize(fields)

    # -------- normalization helpers --------
    @staticmethod
    def _to_float(v: Optional[str]) -> Optional[float]:
        if v is None: return None
        try:
            s = v.strip()
            if s in ('', 'NA', 'NAN', 'nan', 'null', 'None'): return None
            return float(s)
        except Exception:
            return None

    @staticmethod
    def _to_int(v: Optional[str]) -> Optional[int]:
        if v is None: return None
        try:
            s = v.strip()
            if s in ('', 'NA', 'NAN', 'nan', 'null', 'None'): return None
            return int(float(s))
        except Exception:
            return None

    @staticmethod
    def _parse_dateutc(s: Optional[str]):
        if not s: return None
        s = s.strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%m/%d/%Y %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except Exception:
            return None
        
    def _degrees_to_compass(self, degrees):
        """
        Converts wind direction in degrees (0-360) to a 16-point compass direction.
        N is 0 degrees, E is 90 degrees, S is 180 degrees, W is 270 degrees.
        """
        directions = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        ]
        # Adjust degrees to start N at the center of its range (348.75 to 11.25)
        # This shifts the degree range so N is centered around 0.
        adjusted_degrees = (degrees + 11.25) % 360

        # Calculate the index for the directions list
        # Each direction covers 22.5 degrees (360 / 16)
        index = int(adjusted_degrees / 22.5)

        return directions[index]

    # -------- normalization --------
    def _normalize(self, fields: Dict[str, str]) -> Dict[str, Any]:
        f = self._to_float(fields.get('tempf'))
        c = self._to_float(fields.get('tempc'))
        temp_c = c if c is not None else (None if f is None else (f - 32) * 5/9)
        temp_f = f if f is not None else None

        # Indoor temp aliases: Ambient uses 'tempinf' for indoor F
        f = self._to_float(fields.get('indoortempf') or fields.get('tempinf'))
        c = self._to_float(fields.get('indoortempc') or fields.get('tempinc'))
        indoor_c = c if c is not None else (None if f is None else (f - 32) * 5/9)

        humidity = self._to_int(fields.get('humidity'))
        # Indoor humidity alias: Ambient uses 'humidityin'
        indoor_h = self._to_int(fields.get('indoorhumidity') or fields.get('humidityin'))

        mph = self._to_float(fields.get('windspeedmph'))
        wind_mps = mph * 0.44704 if mph is not None else None
        wind_mph = mph if mph is not None else None
        mph_g = self._to_float(fields.get('windgustmph'))
        wind_gust_mps = mph_g * 0.44704 if mph_g is not None else None
        wind_gust_mph = mph_g if mph_g is not None else None
        wind_dir = self._to_int(fields.get('winddir'))
        if wind_dir is None:
            wind_dir = None

        pressure_hpa = None
        for k in ('baromin', 'baromrelin', 'baromabsin'):
            v = self._to_float(fields.get(k))
            if v is not None:
                pressure_hpa = v * 33.8638866667
                break

        pressure_in_h20 = pressure_hpa * 0.295299830714 if pressure_hpa is not None else None

        rr_in = self._to_float(fields.get('rainratein'))
        rain_rate_in_hr = rr_in if rr_in is not None else 0
        rain_rate_mm_h = rr_in * 25.4 if rr_in is not None else None
        dr_in = self._to_float(fields.get('dailyrainin')) or self._to_float(fields.get('eventrainin'))
        rain_daily_mm = dr_in * 25.4 if dr_in is not None else 0
        rain_daily_in = dr_in if dr_in is not None else 0

        solar_wm2 = self._to_float(fields.get('solarradiation'))
        uv_index  = self._to_float(fields.get('UV') or fields.get('uv'))

        pm25 = ( self._to_float(fields.get('pm2_5'))
                 or self._to_float(fields.get('pm25'))
                 or self._to_float(fields.get('pm25_ch1')) )
        pm10 = ( self._to_float(fields.get('pm10'))
                 or self._to_float(fields.get('pm10_ch1')) )

        dt_utc = None
        for k in ('dateutc', 'datetime', 'time_utc'):
            if k in fields:
                dt_utc = self._parse_dateutc(fields[k]); break
        ts_utc = dt_utc.isoformat().replace('+00:00','Z') if dt_utc else None

        battery = None
        for k in ('batt','battery','lowbatt','wh65batt','wh32batt'):
            if k in fields:
                b = (fields[k] or '').strip().lower()
                battery = int(b) if b in ('0','1') else b
                break

        return {
            'timestamp_utc': ts_utc,
            'temperature_F': temp_f,
            'humidity_pct': humidity,
            'wind_mph': wind_mph,
            'wind_gust_mph': wind_gust_mph,
            'wind_dir': self._degrees_to_compass(wind_dir),
            'pressure_in_h20': pressure_in_h20,
            'rain_rate_in_hr': rain_rate_in_hr,
            'rain_daily_mm': rain_daily_in,
            'solar_wm2': solar_wm2,
            'uv_index': uv_index,
            'pm2p5_ugm3': pm25,
            'pm10_ugm3': pm10,
            'indoor_temperature_C': indoor_c,
            'indoor_humidity_pct': indoor_h,
            'battery': battery,
            'raw': fields,
        }
