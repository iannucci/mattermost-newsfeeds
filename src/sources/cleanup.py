from .base import SourceBase
from typing import Dict, Any
from util.notifier import Notifier
from util.mattermost_api import MattermostAPI, MattermostContext


class CleanUp(SourceBase):

    def __init__(
        self,
        name: str,
        general_config: Dict[str, Any],
        cleanup_config: Dict[str, Any],
        seen,
        logger,
        notifier: Notifier,
    ) -> None:
        super().__init__(name, general_config, cleanup_config, seen, logger, notifier)
        self.bucket = "cleanup"
        self.cleanup_config = cleanup_config
        self.general_config = general_config
        self.mattermost_config = self.general_config.get("mattermost", {})
        self.logger = logger
        self.logger.info(f"[cleanup] Initialized")
        url = self.mattermost_config.get("host", "localhost")
        token = self.mattermost_config.get("token", "")
        scheme = self.mattermost_config.get("scheme", "http")
        port = self.mattermost_config.get("port", 80)
        basepath = self.mattermost_config.get("basepath", "/api/v4")
        self.apiInstance = MattermostAPI(url, token, scheme, port, basepath, self.logger)

    def poll(self, _) -> int:
        self.logger.info(f"[cleanup] Cleanup config: {self.cleanup_config}")
        for target in self.cleanup_config.get["targets", []]:
            channel = target.get["channel", ""]
            admin_user = target.get["admin_user", ""]
            board = target.get["board", ""]
            threshold_minutes = target.get["threshold_minutes", 60]
            self.logger.info(f"[cleanup] Cleaning up channel {channel}")
            with MattermostContext(self.apiInstance) as driver:
                driver.delete_messages_in_channel(
                    admin_user, channel, board, threshold_minutes * 60
                )
