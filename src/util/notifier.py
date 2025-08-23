import json, datetime as dt
from typing import Dict, Any, Optional, List
from util.http import post_json, http_get, post_multipart
from mattermostdriver import Driver

TOP_FIELDS = ["event","headline","severity","urgency","certainty","mag","place","distance_km_from_origin","distance_km","name","layer","title","link"]

class SafeDict(dict):
    def __missing__(self, key): return ""

def render_template(template: str, item: Dict[str, Any]) -> str:
    try:
        return template.format_map(SafeDict(item))
    except Exception:
        return json.dumps(item, ensure_ascii=False)

def render_fields(item: Dict[str, Any]) -> str:
    lines: List[str] = []
    # show top fields first, then the rest
    for k in TOP_FIELDS:
        if k in item and item[k] not in (None, ""):
            lines.append(f"- **{k}**: {item[k]}")
    for k, v in item.items():
        if k in TOP_FIELDS or v in (None, ""): continue
        lines.append(f"- **{k}**: {v}")
    return "\n".join(lines) or json.dumps(item, ensure_ascii=False, indent=2)

class Notifier:
    def __init__(self, cfg: Dict[str, Any], mattermost_api: Driver, logger):
        self.type=(cfg.get('type') or 'webhook').lower()
        self.stream=bool(cfg.get('stream', True))
        self.style=(cfg.get('style') or 'markdown').lower()
        self.thread_root_id=cfg.get('thread_root_id') or ''
        self.batch_threshold=int(cfg.get('batch_threshold', 10))
        # webhook
        self.webhook_url=cfg.get('webhook_url','')
        # bot
        self.scheme=cfg.get('scheme','https'); self.host=cfg.get('host',''); self.port=int(cfg.get('port',443))
        self.token=cfg.get('token','')
        self.channel_id= None  # cfg.get('channel_id',''); self.team=cfg.get('team',''); self.channel=cfg.get('channel','')
        # self._cached_channel_id=None
        self.mattermost_api = mattermost_api
        self.logger = logger

    def _base(self):
        port = f":{self.port}" if self.port and self.port not in (80,443) else ""
        return f"{self.scheme}://{self.host}{port}".rstrip('/')

    # def _resolve_channel_id(self) -> Optional[str]:
    #     if self._cached_channel_id: return self._cached_channel_id
    #     if self.channel_id: self._cached_channel_id=self.channel_id; return self.channel_id
    #     if not (self.host and self.token and self.team and self.channel): return None
    #     base=self._base()
    #     headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
    #     t=http_get(f"{base}/api/v4/teams/name/{self.team}", headers=headers).json(); team_id=t.get('id')
    #     if not team_id: 
    #         return None
    #     c=http_get(f"{base}/api/v4/teams/{team_id}/channels/name/{self.channel}", headers=headers).json(); chan_id=c.get('id')
    #     if chan_id: 
    #         self._cached_channel_id=chan_id
    #     return chan_id

    def _compose_text(self, title: str, items: List[Dict[str, Any]], template: Optional[str]):
        if self.style == 'fields' and items:
            return render_fields(items[0])
        if template and items:
            return render_template(template, items[0])
        # markdown default or batch summary
        if len(items) == 1:
            return json.dumps(items[0], ensure_ascii=False, indent=2)
        return f"**{title}**\nReceived {len(items)} items at {dt.datetime.utcnow().isoformat()}Z."

    def send(self, title: str, payload: Dict[str, Any], override: Optional[Dict[str, Any]] = None, template: Optional[str] = None):
        ocfg = override or {}
        t=(ocfg.get('type') or self.type).lower()
        if t=='bot': 
            return self._send_bot(title, payload, ocfg, template)
        else: 
            return self._send_webhook(title, payload, ocfg, template)

    # ---------- Webhook ----------
    def _send_webhook(self, title: str, payload: Dict[str, Any], ocfg: Dict[str, Any], template: Optional[str]):
        webhook_url=ocfg.get('webhook_url') or self.webhook_url
        if not webhook_url: 
            return None
        items=payload.get('items',[])
        text=self._compose_text(title, items, template)
        return post_json(webhook_url, {"text": text})

    # ---------- Bot posts + file uploads ----------
    def _send_bot(self, title: str, payload: Dict[str, Any], ocfg: Dict[str, Any], template: Optional[str]):
        # allow per-source overrides
        scheme=ocfg.get('scheme', self.scheme)
        host=ocfg.get('host', self.host)
        port=int(ocfg.get('port', self.port))
        token=ocfg.get('token', self.token)
        basepath=ocfg.get('basepath', '/api/v4').rstrip('/')
        # resolve channel id if not explicitly set
        self.channel_id = self._get_channel_id_by_name(ocfg.get('channel'), ocfg.get('team'), ocfg.get('user'))
        # chan_id=ocfg.get('channel_id') or self._cached_channel_id
        if not self.channel_id:
            self.logger.warning("[Notifier] Missing channel ID; cannot send bot message.")
            # self.scheme, self.host, self.port, self.token = scheme, host, port, token
            # self.scheme, self.host, self.port = scheme, host, port
            # self.team = ocfg.get('team', self.team)
            # self.channel = ocfg.get('channel', self.channel)
            # chan_id=self._resolve_channel_id()
            # if not chan_id: return None
            return None

        base=f"{scheme}://{host}{(':'+str(port)) if port and port not in (80,443) else ''}".rstrip('/')
        headers={"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
        url=f"{base}/api/v4/posts"
        items=payload.get('items',[])
        # Decide style: upload large batches
        style = (ocfg.get('style') or self.style).lower()
        batch_threshold = int(ocfg.get('batch_threshold', self.batch_threshold))
        if (style == 'upload' and len(items) >= max(1, batch_threshold)) or (style == 'upload' and len(items) > 1):
            # upload JSON and post
            file_bytes=json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
            finfo={"files": ("newsfeed.json", file_bytes, "application/json")}
            upload_headers={"Authorization": f"Bearer {token}"}
            upload=post_multipart(f"{base}/api/v4/files", files=finfo, data={"channel_id": self.channel_id}, headers=upload_headers)
            file_id=upload.json().get('file_infos',[{}])[0].get('id')
            if not file_id: 
                return None
            body={"channel_id": self.channel_id, "message": f"{title}", "file_ids": [file_id]}
            root_id = ocfg.get('thread_root_id') or self.thread_root_id
            if root_id: 
                body["root_id"] = root_id
            return post_json(url, body, headers=headers)

        # otherwise, plain text message
        text=self._compose_text(title, items, template)
        body={"channel_id": self.channel_id, "message": text}
        root_id = ocfg.get('thread_root_id') or self.thread_root_id
        if root_id: 
            body["root_id"] = root_id
        return post_json(url, body, headers=headers)

    def _get_channel_id_by_name(self, channel_name, team_name, user_name):
        teams = self.mattermost_api.teams.get_teams()
        team = next((team for team in teams if team['display_name'] == team_name), None)
        if team is None:
            self.logger.warning(f'[Notifier] Team {team_name} not found.')
            return
        team_id = team['id']
        user_id = self.mattermost_api.users.get_user_by_username(user_name).get('id')
        channels = self.mattermost_api.channels.get_channels_for_user(user_id, team_id)
        if not channels:
            self.logger.warning(f'[Notifier] No channels found for team {team_name}.')
            return
        channel = next((channel for channel in channels if channel['display_name'] == channel_name), None)
        if channel is None:
            self.logger.warning(f'[Notifier] Channel {channel_name} not found in team {team_name}.')
            return
        return channel['id']
	