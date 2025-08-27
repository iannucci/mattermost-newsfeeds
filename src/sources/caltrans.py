import xml.etree.ElementTree as ET
from util.http import http_get
from .base import SourceBase, km_between
from typing import Dict, Any
from util.notifier import Notifier
from util.ws5000_handler import Handler
import re
import sys
from typing import Optional
from bs4 import BeautifulSoup, NavigableString, Tag
from html import unescape
from util.ws5000_handler import Handler
from datetime import datetime


class Caltrans(SourceBase):

    def __init__(
        self,
        name: str,
        cfg: Dict[str, Any],
        general_cfg: Dict[str, Any],
        seen,
        logger,
        notifier: Notifier,
    ) -> None:
        super().__init__(name, cfg, general_cfg, seen, logger, notifier)
        self.bucket = "caltrans"
        self.acronyms = cfg.get("acronyms", {})

    def poll(self, now_ts: float) -> int:
        lat0 = self.general_cfg["location"]["lat"]
        lon0 = self.general_cfg["location"]["lon"]
        max_mi = float(self.params.get("max_mi", 10.0))
        endpoints = self.params.get("endpoints", {})
        layer_filter = (self.params.get("layer_filter_prefix") or "").strip()
        headers = {
            "User-Agent": self.general_cfg.get("user_agent", ""),
            "Accept": "application/vnd.google-earth.kml+xml, application/xml, text/xml",
        }
        new_count = 0
        for layer, url in endpoints.items():
            if layer_filter and not layer.startswith(layer_filter):
                self.logger.debug(
                    f"[CalTrans] skipping layer {layer} due to filter {layer_filter}"
                )
                continue
            try:
                xml_text = http_get(
                    url, headers=headers
                ).text  # this is a sizable chunk of XML with lots of placemarks
                for item_raw in self._parse_kml(xml_text):
                    lat, lon = item_raw.get("lat"), item_raw.get("lon")
                    if None in (lat, lon):
                        self.logger.debug(
                            f"[CalTrans] skipping item {item_raw} due to missing lat/lon"
                        )
                        continue
                    d = km_between(lat0, lon0, lat, lon) * 0.621371  # to miles
                    if d > max_mi:
                        self.logger.debug(
                            f"[CalTrans] skipping item {item_raw} due to distance {d} mi > max {max_mi} mi"
                        )
                        continue
                    item = dict(item_raw)
                    item["distance_mi"] = round(d * 0.621371, 1)
                    item["layer"] = layer
                    fp = f"{self.bucket}|{layer}|{item.get('name')}|{lat}|{lon}"
                    if self.seen.is_seen(self.bucket, fp):
                        continue
                    self.seen.mark_seen(self.bucket, fp)
                    soup = BeautifulSoup(item["description"], "html.parser")
                    if soup and isinstance(soup, Tag):
                        self.logger.debug(f"[CalTrans] sent {item['description']}\n")
                        # (item['desc'], item["timestamp_local"])= self._parse_caltrans_soup(soup)
                        (item["desc"], item["timestamp_local"]) = (
                            self._extract_incident_from_soup(soup)
                        )
                    else:
                        item["desc"] = unescape(item.get("description", ""))
                        item["timestamp_local"] = self.dt_local_str(self.now_dt())
                    self.logger.debug(
                        f"[CalTrans] {layer} we substituted: {item['desc']}\n"
                    )

                    self.post_item(item)
                    new_count += 1
            except Exception as e:
                self.logger.error(f"[CalTrans] {layer} error: {e}")
        if new_count > 0:
            self.logger.info(f"[CalTrans] processed {new_count} new item(s)")
        else:
            self.logger.debug("[CalTrans] no new items")
        return new_count

    # see also https://lostcoastoutpost.com/chpwatch/codes/
    def _de_acronymize(self, text: str) -> str:
        """Replace known acronyms in the text with their expansions."""

        def replace(match):
            acronym = match.group(0)
            return self.acronyms.get(acronym, acronym)

        pattern = re.compile(
            r"\b(" + "|".join(re.escape(k) for k in self.acronyms.keys()) + r")\b"
        )
        return pattern.sub(replace, text) if self.acronyms else text

    def _extract_incident_from_soup(self, soup):
        updated_dt = None
        updated_p = soup.find("p", class_="update-stamp")
        if updated_p:
            raw = updated_p.get_text(strip=True)
            m = re.search(
                r"(\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}\s*[ap]m)", raw, flags=re.I
            )
            if m:
                try:
                    updated_dt = datetime.strptime(
                        m.group(1).upper(), "%m/%d/%Y %I:%M%p"
                    )
                except ValueError:
                    updated_dt = None

        # Patterns
        lead_ts = re.compile(
            r"^\s*[A-Za-z]{3,9}\s+\d{1,2}\s+\d{4}\s+\d{1,2}:\d{2}\s*[AP]M\s*", re.I
        )
        bracket_nums = re.compile(r"\s*\[\s*\d+\s*\]\s*")  # e.g., [2], [12]

        parts = []
        for p in soup.find_all("p"):
            # Skip update-stamp and info-credit paragraphs
            if "update-stamp" in (p.get("class") or []):
                continue
            block = p.get_text(separator="\n", strip=True)
            if not block or "information courtesy of" in block.lower():
                continue

            lines = [ln for ln in block.split("\n") if ln.strip()]
            if p.get("align", "").lower() == "left":
                # Remove leading timestamps per line
                lines = [lead_ts.sub("", ln).strip() for ln in lines if ln.strip()]

            # Join lines, then remove bracketed numeric tags
            text = " ".join(lines)
            text = bracket_nums.sub(" ", text)

            # Collapse whitespace and add
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                parts.append(text)

        return self._de_acronymize(" ".join(parts)), updated_dt

    def _parse_kml(self, xml_text: str):
        root = ET.fromstring(xml_text)
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        items = []
        for pm in root.findall(".//Placemark") + root.findall(".//k:Placemark", ns):
            name = self._txt(pm.find("name")) or self._txt(
                pm.find("{http://www.opengis.net/kml/2.2}name")
            )
            desc = self._txt(pm.find("description")) or self._txt(
                pm.find("{http://www.opengis.net/kml/2.2}description")
            )

            lon = lat = None
            coord_text = None
            pt = pm.find("Point") or pm.find("{http://www.opengis.net/kml/2.2}Point")
            if pt is not None:
                c = pt.find("coordinates") or pt.find(
                    "{http://www.opengis.net/kml/2.2}coordinates"
                )
                coord_text = self._txt(c)
            if coord_text is None:
                for tag in ("LineString", "Polygon"):
                    g = pm.find(tag) or pm.find(
                        f"{{http://www.opengis.net/kml/2.2}}{tag}"
                    )
                    if g is not None:
                        c = g.find("coordinates") or g.find(
                            "{http://www.opengis.net/kml/2.2}coordinates"
                        )
                        coord_text = self._txt(c)
                        break
            if coord_text:
                parts = coord_text.strip().split()
                if parts:
                    first = parts[0].split(",")
                    if len(first) >= 2:
                        try:
                            lon = float(first[0])
                            lat = float(first[1])
                        except ValueError:
                            lon = lat = None

            items.append({"name": name, "description": desc, "lon": lon, "lat": lat})
        return items

    def _txt(self, e):
        return e.text.strip() if (e is not None and e.text) else None
