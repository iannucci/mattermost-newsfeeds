import json
from mattermostdriver import Driver
import time
import logging

HOUR = 3600
DAY = 86400
WEEK = 604800
AGE_THRESHOLD_SECONDS = DAY


def build_logger(level: str, module):
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")
    return logging.getLogger(module)


class MattermostContext:
    def __init__(self, apiInstance):
        self.apiInstance = apiInstance

    def __enter__(self):
        self.apiInstance.login()
        return self.apiInstance.driver

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.apiInstance.logout()


class MattermostAPI:
    def __init__(self, url, token, scheme, port, basepath, logger):
        self.url = url
        self.token = token
        self.scheme = scheme
        self.port = port
        self.basepath = basepath
        self.logger = logger
        self.driver = None

    def login(self):
        if self.driver is None:
            login_dict = {
                "url": self.url,
                "token": self.token,
                "scheme": self.scheme,
                "port": self.port,
                "basepath": self.basepath,
            }
            self.driver = Driver(login_dict)
            self.driver.login()

    def logout(self):
        if self.driver:
            self.driver.logout()
            self.driver = None

    def create_user(self, email, username, first_name, last_name, nickname, password):
        user_data = {
            "email": email,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "nickname": nickname,
            "password": password,
        }
        with MattermostContext(self) as driver:
            result = driver.users.create_user(options=user_data)
        return result

    def get_user_id_by_name(self, user_name):
        with MattermostContext(self) as driver:
            user_data = driver.users.get_user_by_username(user_name)
        if not user_data:
            self.logger.info(f"[mattermost_api] User {user_name} not found.")
            return None
        return user_data["id"]

    def print_user(self, user_id):
        with MattermostContext(self) as driver:
            user_data = driver.users.get_user(user_id)
        if not user_data:
            self.logger.info(f"[mattermost_api] User {user_id} not found.")
            return None
        self.logger.info(user_data)
        self.logger.info(f'[mattermost_api] User ID: {user_data["id"]}')
        self.logger.info(f'[mattermost_api] First name: {user_data["first_name"]}')
        self.logger.info(f'[mattermost_api] Last name: {user_data["last_name"]}')
        self.logger.info(f'[mattermost_api] Nickname: {user_data["nickname"]}')

    def change_username(self, user_id, new_username):
        with MattermostContext(self) as driver:
            user_data = driver.users.get_user(user_id)
        if not user_data:
            self.logger.info(f"[mattermost_api] User {user_id} not found.")
            return None
        user_data["username"] = new_username.strip()
        with MattermostContext(self) as driver:
            result = driver.users.update_user(user_id, options=user_data)
        return result

    def cleanup_user(self, user_id, first_name, last_name):
        """Adds first and last name to user and sets the nickname to first name + uppercase callsign"""
        with MattermostContext(self) as driver:
            user_data = driver.users.get_user(user_id)
        if not user_data:
            self.logger.info(f"[mattermost_api] User {user_id} not found.")
            return None
        username = user_data["username"].strip()
        user_data["first_name"] = first_name.strip()
        user_data["last_name"] = last_name.strip()
        user_data["nickname"] = f"{first_name} {username.upper()}"
        with MattermostContext(self) as driver:
            result = driver.users.update_user(user_id, options=user_data)
        return result

    def hoover_channel(self):
        return {
            "team_id": next(
                (
                    team
                    for team in self.driver.teams.get_teams()
                    if team["display_name"] == "Palo Alto ESV"
                ),
                None,
            )["id"],
            "name": "hoover-newsfeed",
            "display_name": "Hoover Newsfeed",
            "type": "O",
            "purpose": "This channel provides newsfeeds from a variety of public sources.",
            "header": "Hoover Newsfeed",
        }

    def do_the_team_thing(self):
        with MattermostContext(self) as driver:
            teams = driver.teams.get_teams()
        palo_alto_team = next(
            (team for team in teams if team["display_name"] == "Palo Alto ESV"), None
        )
        if not palo_alto_team:
            self.logger.info(f"[mattermost_api] Palo Alto ESV team not found.")
        else:
            self.logger.info(
                f'[mattermost_api] Palo Alto ESV Team: {palo_alto_team["display_name"]} ({palo_alto_team["name"]})'
            )
        with MattermostContext(self) as driver:
            w6ei = driver.users.get_user_by_username("w6ei")["id"]
        self.logger.info(f"[mattermost_api] User ID for w6ei: {w6ei}")
        with MattermostContext(self) as driver:
            channel_dict = driver.channels.get_channels_for_user(w6ei, palo_alto_team["id"])
        if not channel_dict:
            self.logger.info(
                f"[mattermost_api] No channels found for user w6ei in Palo Alto ESV team."
            )
        else:
            self.logger.info(
                f"[mattermost_api] Channels found for user w6ei in Palo Alto ESV team: {len(channel_dict)}"
            )
            for channel in channel_dict:
                self.logger.info(
                    f'[mattermost_api] Channel: {channel["display_name"]} ({channel["name"]}) - ID: {channel["id"]}'
                )
        self.logger.info(self.driver.channels.create_channel(options=self.hoover_channel()))

    def delete_messages_in_channel(
        self, user_name, channel_name, team_name, age_threshold_seconds=AGE_THRESHOLD_SECONDS
    ):
        with MattermostContext(self) as driver:
            user = driver.users.get_user_by_username(user_name)
        if not user:
            self.logger.info(f"[mattermost_api] User {user_name} not found.")
            return
        # user_id = user["id"]
        with MattermostContext(self) as driver:
            teams = driver.teams.get_teams()
        team = next((team for team in teams if team["display_name"] == team_name), None)
        if team is None:
            self.logger.info(f"[mattermost_api] Team {team_name} not found.")
            return
        team_id = team["id"]
        # WARNING: Don't nest this inside of another with MattermostContext.  This function
        # itself uses a with and will Logout()
        user_id = self.get_user_id_by_name(user_name)
        with MattermostContext(self) as driver:
            channels = driver.channels.get_channels_for_user(user_id, team_id)
        if not channels:
            self.logger.info(
                f"[mattermost_api] No channels found for team {team_name} and user {user_name}."
            )
            return
        channel = next(
            (channel for channel in channels if channel["display_name"] == channel_name),
            None,
        )
        if channel is None:
            self.logger.info(
                f"[mattermost_api] Channel {channel_name} not found in team {team_name}."
            )
            return
        channel_id = channel["id"]
        self.logger.info(
            f"[mattermost_api] Erasing messages in channel {channel_name} (ID: {channel_id}) in team {team_name} (ID: {team_id})"
        )
        now_timestamp = int(time.time())
        page_number = 0
        while True:
            with MattermostContext(self) as driver:
                posts = driver.posts.get_posts_for_channel(
                    channel_id, params={"page": page_number, "per_page": 200}
                )["posts"]
            if not posts:
                self.logger.info(
                    f"[mattermost_api] No more messages found in channel {channel_name}."
                )
                return
            page_number += 1
            for post_id, post_dict in posts.items():
                update_at_timestamp = int(post_dict["update_at"] / 1000)
                age_seconds = now_timestamp - update_at_timestamp
                if age_seconds > age_threshold_seconds:
                    self.logger.info(
                        f"[mattermost_api] Deleting post {post_id} in channel {channel_name} because age in seconds ({age_seconds}) exceeds the threshold ({age_threshold_seconds})."
                    )
                    with MattermostContext(self) as driver:
                        driver.posts.delete_post(post_id)
            time.sleep(5)

    def lookup_channel_by_name(self, channel_name, team_name, user_name):
        with MattermostContext(self) as driver:
            teams = driver.teams.get_teams()
        team = next((team for team in teams if team["display_name"] == team_name), None)
        if team is None:
            self.logger.info(f"[mattermost_api] Team {team_name} not found.")
            return
        team_id = team["id"]
        user_id = self.get_user_id_by_name(user_name)
        with MattermostContext(self) as driver:
            channels = driver.channels.get_channels_for_user(user_id, team_id)
        if not channels:
            self.logger.info(f"[mattermost_api] No channels found for team {team_name}.")
            return
        channel = next(
            (channel for channel in channels if channel["display_name"] == channel_name),
            None,
        )
        if channel is None:
            self.logger.info(
                f"[mattermost_api] Channel {channel_name} not found in team {team_name}."
            )
            return
        return channel["id"]
        # self.logger.info(f'[mattermost_api] Channel {channel_name} ID: {channel["id"]}')
        # self.logger.info(json.dumps(channel, indent=4))


# self.logger.info(lookup_channel_by_name('National Weather Service', 'Palo Alto ESV', 'hoover'))
# self.logger.info(lookup_channel_by_name('CalTrans', 'Palo Alto ESV', 'hoover'))
# self.logger.info(lookup_channel_by_name('US Geological Survey', 'Palo Alto ESV', 'hoover'))
# self.logger.info(lookup_channel_by_name('Local Weather', 'Palo Alto ESV', 'hoover'))

# user = ""
# first = ""
# last = ""

# create_user()
# self.logger.info_user(get_user_id_by_name(user))
# cleanup_user(get_user_id_by_name(user), first, last)
# self.logger.info_user(get_user_id_by_name(user))

# delete_messages_in_channel("w6ei", "Local Weather", "Palo Alto ESV", age_threshold_seconds=HOUR * 3)
# delete_messages_in_channel("w6ei", "CalTrans", "Palo Alto ESV", age_threshold_seconds=HOUR * 3)
# delete_messages_in_channel(
#     "w6ei", "US Geological Survey", "Palo Alto ESV", age_threshold_seconds=HOUR * 12
# )
# delete_messages_in_channel("w6ei", "PulsePoint", "Palo Alto ESV", age_threshold_seconds=WEEK)
# delete_messages_in_channel(
#     "w6ei", "National Weather Service", "Palo Alto ESV", age_threshold_seconds=HOUR * 12
# )

file_path = "config.json"
config = {}
logger = build_logger(logging.INFO, "mattermost_api")

try:
    with open(file_path, "r") as f:
        config = json.load(f)
    logger.info("[mattermost_api] Configuration data loaded successfully")
except FileNotFoundError:
    logger.info(f"[mattermost_api] Error: The file '{file_path}' was not found.")
except json.JSONDecodeError:
    logger.info(
        f"[mattermost_api] Error: Could not decode JSON from '{file_path}'. Check file format."
    )
except Exception as e:
    logger.info(f"[mattermost_api] An unexpected error occurred: {e}")

general_config = config.get("general", {})
mattermost_config = general_config.get("mattermost", {})
url = mattermost_config["host"]
token = mattermost_config["token"]
scheme = mattermost_config["scheme"]
port = mattermost_config["port"]
basepath = mattermost_config["basepath"]

api = MattermostAPI(url, token, scheme, port, basepath, logger)
api.delete_messages_in_channel(
    "w6ei", "Local Weather", "Palo Alto ESV", age_threshold_seconds=HOUR * 3
)
