import xml.etree.ElementTree as ET
from html import unescape as _html_unescape
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
import pytz
from datetime import datetime, timezone

# 08/23/2025 11:03am
time_format = "%m/%d/%Y %H:%M:%M%p"

class Caltrans(SourceBase):

    def __init__(self, name: str, cfg: Dict[str, Any], general: Dict[str, Any], seen, logger, notifier: Notifier) -> None:
        super().__init__(name, cfg, general, seen, logger, notifier)
        self.bucket="caltrans"
        self.acronyms=cfg.get('acronyms',{})

    def poll(self, now_ts: float)->int:
        lat0=self.general['location']['lat']
        lon0=self.general['location']['lon']
        max_mi=float(self.params.get('max_mi',10.0))
        endpoints=self.params.get('endpoints',{})
        layer_filter=(self.params.get('layer_filter_prefix') or '').strip()
        headers={'User-Agent': self.general.get('user_agent',''), 'Accept':'application/vnd.google-earth.kml+xml, application/xml, text/xml'}
        new_count=0
        for layer,url in endpoints.items():
            if layer_filter and not layer.startswith(layer_filter): 
                self.logger.debug(f"[CalTrans] skipping layer {layer} due to filter {layer_filter}")
                continue
            try:
                xml_text=http_get(url, headers=headers).text  # this is a sizable chunk of XML with lots of placemarks
                for item_raw in self._parse_kml(xml_text):
                    lat,lon=item_raw.get('lat'),item_raw.get('lon')
                    if None in (lat,lon): 
                        self.logger.debug(f"[CalTrans] skipping item {item_raw} due to missing lat/lon")
                        continue
                    d=km_between(lat0,lon0,lat,lon)*0.621371 # to miles
                    if d>max_mi: 
                        self.logger.debug(f"[CalTrans] skipping item {item_raw} due to distance {d} mi > max {max_mi} mi")
                        continue
                    item=dict(item_raw)
                    item['distance_mi']=round(d*0.621371,1)
                    item['layer']=layer
                    fp=f"{self.bucket}|{layer}|{item.get('name')}|{lat}|{lon}"
                    if self.seen.is_seen(self.bucket, fp): 
                        continue
                    self.seen.mark_seen(self.bucket, fp)
                    soup=BeautifulSoup(item['description'], 'html.parser')
                    if soup and isinstance(soup, Tag):
                        self.logger.info(f"[CalTrans] sent {item['description']}\n")
                        # (item['desc'], item["timestamp_local"])= self._parse_caltrans_soup(soup)
                        (item['desc'], item["timestamp_local"])= self._extract_update_and_text(soup)
                    else:
                        item['desc']=unescape(item.get('description', ''))
                        item['timestamp_local']=datetime.now().isoformat()

                    # item['desc']=self._de_acronymize(item['desc'])

                    # <debug>
                    self.logger.info(f"[CalTrans] {layer} we substituted: {item['desc']}\n")

                    self.post_item(item)
                    new_count+=1
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
        pattern = re.compile(r'\b(' + '|'.join(re.escape(k) for k in self.acronyms.keys()) + r')\b')
        return pattern.sub(replace, text) if self.acronyms else text

    def _extract_update_and_text(self, soup):
        """
        Extract:
        - the timestamp from <p class="update-stamp"> (both raw string and parsed datetime if possible)
        - concatenated text from the remaining <p> tags, ignoring the 'Information courtesy of' paragraph,
            replacing <br> with spaces, and stripping leading timestamps from paragraphs with align='left'.

        Returns:
        dict: {
            "updated_raw": str | None,      # e.g., "08/23/2025 6:55pm"
            "updated_dt": datetime | None,  # parsed datetime if format matches
            "text": str                     # concatenated incident text
        }
        """
        # soup = BeautifulSoup(html, "html.parser")

        # Replace <br> tags with spaces globally
        for br in soup.find_all("br"):
            br.replace_with(" ")

        # Pull update timestamp (raw string like "Last updated: 08/23/2025 6:55pm")
        updated_p = soup.find("p", class_="update-stamp")
        updated_raw = None
        updated_dt = None

        if updated_p:
            raw = updated_p.get_text(strip=True)
            # Extract the MM/DD/YYYY hh:mm(am|pm) portion
            m = re.search(r"(\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}\s*[ap]m)", raw, flags=re.I)
            if m:
                updated_raw = m.group(1)
                try:
                    updated_dt = datetime.strptime(updated_raw, "%m/%d/%Y %I:%M%p")
                except ValueError:
                    updated_dt = None
            else:
                # Fall back to whole string if pattern not found
                updated_raw = raw

        # Regex to remove a leading timestamp like "Aug 23 2025  6:53PM" at the start of a paragraph
        lead_ts = re.compile(
            r"^\s*[A-Za-z]{3}\s+\d{1,2}\s+\d{4}\s+\d{1,2}:\d{2}\s*[AP]M\s*",
            flags=re.I
        )

        parts = []
        for p in soup.find_all("p"):
            # Skip update-stamp and the "Information courtesy of" paragraph
            if "update-stamp" in (p.get("class") or []):
                continue

            text = p.get_text(" ", strip=True)

            # Ignore "Information courtesy of ..." paragraphs (case-insensitive)
            if text.lower().startswith("information courtesy of"):
                continue

            # Only strip leading timestamps from paragraphs with align='left'
            if p.get("align", "").lower() == "left":
                text = lead_ts.sub("", text)

            if text:
                parts.append(text)

        return " ".join(parts), updated_dt

        # return {
        #     "updated_raw": updated_raw,
        #     "updated_dt": updated_dt,
        #     "text": " ".join(parts)
        # }

    def _parse_caltrans_soup(self, soup) -> str:
        # Enter with soup that is structured like this:
        #
        # <div style="font-size:1.15em;">
        #   <img src="https://quickmap.dot.ca.gov/img/chp-32x32.png" style="float:left">
        #   <p align="left">Aug 23 2025 10:08AM <br> 1125-Traffic Hazard <br> Us101 N / San Antonio Rd Ofr </p>
        #   <p align="left"> </p>
        #   <p>Information courtesy of <img src="https://quickmap.dot.ca.gov/QM/imagesquickmap/CHP_Badge_logo.png" height="30"></p>
        #   <p class="update-stamp">Last updated: 08/23/2025 10:10am </p>
        # </div>

        # <div style="font-size:1.15em;">
        #   <img src="https://quickmap.dot.ca.gov/img/chp-32x32.png" style="float:left">
        #   <p align="left">Aug 23 2025 11:02AM <br> 1183-Trfc Collision-Unkn Inj <br> Us101 S / Woodside Rd Ofr </p>
        #   <p align="left"> </p>
        #   <p>Information courtesy of <img src="https://quickmap.dot.ca.gov/QM/imagesquickmap/CHP_Badge_logo.png" height="30"></p>
        #   <p class="update-stamp">Last updated: 08/23/2025 11:03am </p>
        # </div>

        # <div style="font-size:1.15em;">
        #   <img src="https://quickmap.dot.ca.gov/img/chp-32x32.png" style="float:left">
        #   <p align="left">Aug 23 2025 11:16AM <br> 1125-Traffic Hazard <br> I280 N / El Monte Rd Ofr </p>
        #   <p align="left"> </p>
        #   <p>Information courtesy of <img src="https://quickmap.dot.ca.gov/QM/imagesquickmap/CHP_Badge_logo.png" height="30"></p>
        #   <p class="update-stamp">Last updated: 08/23/2025 11:17am </p>
        # </div>

        # <div style="font-size:1.15em;">
        #   <img src="https://quickmap.dot.ca.gov/img/chp-32x32.png" style="float:left">
        #   <p align="left">Aug 23 2025 11:16AM <br> 1125-Traffic Hazard <br> I280 N / Alpine Rd Ofr </p>
        #   <p align="left">Aug 23 2025 11:18AM [3] NO ASSOC VEH SEEN<br />Aug 23 2025 11:17AM [2] LARGE PIECE OF TIRE - BTN #3/#4 LNS<br /> </p>
        #   <p>Information courtesy of <img src="https://quickmap.dot.ca.gov/QM/imagesquickmap/CHP_Badge_logo.png" height="30"></p>
        #   <p class="update-stamp">Last updated: 08/23/2025 11:19am </p>
        # </div>
        self.logger.debug(f"[CalTrans] processing soup: {soup}")  

        last_update_p = soup.find("p", class_="update-stamp")
        if last_update_p:
            time_string = last_update_p.get_text(strip=True).replace("Last updated:", "").strip()
            time = datetime.strptime(time_string, time_format)
        else:
            time = datetime.now()

        information_p_list = soup.find_all("p", align="left")
        raw_text = ""
        for information_p in information_p_list:
            p_text = information_p.get_text(strip=True)
            p_text_cleaned = re.sub(r'^\w{3} \d{1,2} \d{4} \d{1,2}:\d{2}(AM|PM)?\s*', '', p_text)
            raw_text += p_text_cleaned

        ts_local_time = time.isoformat()

        return (ts_local_time, _de_acronymize(raw_text))

    def _parse_kml(self, xml_text: str):
        root=ET.fromstring(xml_text)
        ns={'k':'http://www.opengis.net/kml/2.2'}
        items=[]
        for pm in root.findall('.//Placemark') + root.findall('.//k:Placemark', ns):
            name=self._txt(pm.find('name')) or self._txt(pm.find('{http://www.opengis.net/kml/2.2}name'))
            desc=self._txt(pm.find('description')) or self._txt(pm.find('{http://www.opengis.net/kml/2.2}description'))

            lon=lat=None
            coord_text=None
            pt=pm.find('Point') or pm.find('{http://www.opengis.net/kml/2.2}Point')
            if pt is not None:
                c=pt.find('coordinates') or pt.find('{http://www.opengis.net/kml/2.2}coordinates'); coord_text=self._txt(c)
            if coord_text is None:
                for tag in ('LineString','Polygon'):
                    g=pm.find(tag) or pm.find(f'{{http://www.opengis.net/kml/2.2}}{tag}')
                    if g is not None:
                        c=g.find('coordinates') or g.find('{http://www.opengis.net/kml/2.2}coordinates'); coord_text=self._txt(c); break
            if coord_text:
                parts=coord_text.strip().split()
                if parts:
                    first=parts[0].split(',')
                    if len(first)>=2:
                        try: lon=float(first[0]); lat=float(first[1])
                        except ValueError: lon=lat=None

            items.append({'name':name,'description':desc,'lon':lon,'lat':lat})
        return items

    def _txt(self, e): 
        return e.text.strip() if (e is not None and e.text) else None
