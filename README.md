# Mattermost Newsfeeds

Pulls information from information sources and formats them as messages that are then posted to a Mattermost channel.  Useful for emergency services volunteers for situational awareness.

Config lookup:
- prefers `./config.json` (current working directory)
- else `/etc/mattermost-newsfeeds/config.json`

## Installation

For Python 3.13 on Ubuntu 24
```
$ sudo add-apt-repository ppa:deadsnakes/ppa
$ sudo apt install python3.13-full
$ sudo apt install python3-pip
$ apt install python3.13-venv

$ git clone <this repo>
$ cd <repo-dir>
$ sudo ./install_systemd.sh
```