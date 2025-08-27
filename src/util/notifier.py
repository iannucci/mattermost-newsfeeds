import json, datetime as dt
from typing import Dict, Any, Optional, List
from util.http import post_json, http_get, post_multipart
from mattermostdriver import Driver

TOP_FIELDS = [
    "event",
    "headline",
    "severity",
    "urgency",
    "certainty",
    "mag",
    "place",
    "distance_km_from_origin",
    "distance_km",
    "name",
    "layer",
    "title",
    "link",
]


class SafeDict(dict):
    def __missing__(self, key):
        return ""


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
        if k in TOP_FIELDS or v in (None, ""):
            continue
        lines.append(f"- **{k}**: {v}")
    return "\n".join(lines) or json.dumps(item, ensure_ascii=False, indent=2)


class Notifier:
    def __init__(
        self,
        general_cfg: Dict[str, Any],
        notifier_cfg: Dict[str, Any],
        mattermost_api: Driver,
        logger,
    ):
        self.notifier_cfg = notifier_cfg
        self.general_cfg = general_cfg
        self.mattermost_api = mattermost_api
        self.logger = logger
        self.mattermost_cfg = general_cfg.get("mattermost", {})
        self.mattermost_channel = notifier_cfg.get("channel", "")
        self.mattermost_team = self.mattermost_cfg.get("team", "")
        self.mattermost_user = self.mattermost_cfg.get("user", "")
        self.type = (notifier_cfg.get("type") or "webhook").lower()
        self.stream = bool(notifier_cfg.get("stream", True))
        self.style = (notifier_cfg.get("style") or "markdown").lower()
        self.webhook_url = notifier_cfg.get("webhook_url", "")
        self.channel_id = None
        self.base = None
        if self.mattermost_channel != "":
            self.mattermost_channel_id = self._get_channel_id_by_name(
                self.mattermost_channel, self.mattermost_team, self.mattermost_user
            )
        else:
            self.mattermost_channel_id = None

    def _compose_text(
        self, title: str, items: List[Dict[str, Any]], template: Optional[str]
    ):
        if self.style == "fields" and items:
            return render_fields(items[0])
        if template and items:
            return render_template(template, items[0])
        if len(items) == 1:
            return json.dumps(items[0], ensure_ascii=False, indent=2)
        # return f"**{title}**\nReceived {len(items)} items at {dt.datetime.utcnow().isoformat()}Z."
        return (
            f"**{title}**\nReceived {len(items)} items at {self.base.now_local_str()}."
        )

    def send(
        self,
        title: str,
        payload: Dict[str, Any],
        override: Optional[Dict[str, Any]] = None,
        template: Optional[str] = None,
    ):
        ocfg = override or {}
        t = (ocfg.get("type") or self.type).lower()
        if t == "mattermost":
            return self._send_mattermost(title, payload, template)
        else:
            return self._send_webhook(title, payload, ocfg, template)

    def _send_mattermost(self, title: str, payload: Dict[str, Any], template):
        items = payload.get("items", [])
        text = self._compose_text(title, items, template)

        # {
        # "channel_id": "string",
        # "message": "string",
        # "root_id": "string",
        # "file_ids": [
        #     "string"
        # ],
        # "props": {},
        # "metadata": {
        #     "priority": {
        #     "priority": "string",
        #     "requested_ack": true
        #     }
        # }

        body = {"channel_id": self.channel_id, "message": text}

        return self.mattermost_api.posts.create_post(body)

    def _send_webhook(
        self,
        title: str,
        payload: Dict[str, Any],
        ocfg: Dict[str, Any],
        template: Optional[str],
    ):
        webhook_url = ocfg.get("webhook_url") or self.webhook_url
        if not webhook_url:
            return None
        items = payload.get("items", [])
        text = self._compose_text(title, items, template)
        return post_json(webhook_url, {"text": text})

    def _get_channel_id_by_name(self, channel_name, team_name, user_name):
        # teams = (
        #     self.mattermost_api.teams.get_teams()
        # )  # user has to be a system admin to list teams
        # team = next((team for team in teams if team["display_name"] == team_name), None)
        # if team is None:
        #     self.logger.warning(f"[Notifier] Team {team_name} not found.")
        #     return
        # team_id = team["id"]
        user_id = self.mattermost_api.users.get_user_by_username(user_name).get("id")
        teams = self.mattermost_api.teams.get_user_teams(user_id)
        team = next((team for team in teams if team["display_name"] == team_name), None)
        if team is None:
            self.logger.warning(
                f"[Notifier] Team {team_name} not found for user {user_name}."
            )
            return
        team_id = team["id"]
        channels = self.mattermost_api.channels.get_channels_for_user(user_id, team_id)
        if not channels:
            self.logger.warning(f"[Notifier] No channels found for team {team_name}.")
            return
        channel = next(
            (
                channel
                for channel in channels
                if channel["display_name"] == channel_name
            ),
            None,
        )
        if channel is None:
            self.logger.warning(
                f"[Notifier] Channel {channel_name} not found in team {team_name}."
            )
            return
        return channel["id"]
