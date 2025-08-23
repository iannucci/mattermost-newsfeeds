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

## Configuration

Copy `config-example.json` to `config.json` in the same directory or `/etc/mattermost-newsfeeds/config.json` and edit the below fields (the rest are defaults which you can tweak later).

### General section

- `lat`: latitude as a floating point number
- `lon`: longitude as a floating point number

Some sources provide GPS coordinates for events.  The latitude and longitude you set define the center of a circle.  The max_mi for that source determines the radius of the circle in miles.

- `host`: mattermost FQDN
- `token`: the Mattermost token for the user that will be posting.
- `scheme`: http or https, depending on your server
- `port`: 80, 443, or something else depending on your server

### Per-source sections

The above host, token, scheme, and pot parameters are repeated per-source to allow targeting of more than one Mattermost server.  In the general case, set these parameters to be the same as in the general section unless you have a reason to do otherwise.

- `enabled`: true or false
- `poll_seconds`: how frequently this source will be checked for updates
- `team`: the name of the team
- `channel` the name of the channel to which this source will post
- `user` the name of the posting user
- `token` the token of the posting user

### The Ambient Weather source

The code implements a small webserver that receives push notifications from Ambient Weather's [WS-5000](https://ambientweather.com/?gad_source=1&gad_campaignid=16445094618&gbraid=0AAAAAD_pbGdX3o98S-7tyg4vKUGxkdM0U&gclid=Cj0KCQjwzaXFBhDlARIsAFPv-u-AThOCMgwDWni_jhlCzVcVWIJFZe8c3luZpP3AmwdSlRBZ8lt6vKYaAilrEALw_wcB) (I am not affiliated with Ambient Weather in any way -- just a happy user).  This source is disabled by default, but you can enable it by setting `enabled` parameter above.  Note that you will need to configure your WS-5000 device to send data to the hostname or IP address that is running this code.  You will also need to make sure that the `port` on the host running this code is otherwise free and that the WS-5000 is targeting it.  Make changes to the `http` subsection (ignore the `udp` subsection -- it is intended to capture UDP broadcasts from the WS-5000 that only contain device info and not weather readings).

## Discussion

After the thrill of receiving automated pushes to your Mattermost channels wears off, you may find yourself inundated with posts. Tweak the `poll_seconds` to provide a balance between latency and post volume. 

At present, this code does not delete old messages, although it is possible to do this using the [Mattermost API](https://github.com/mattermost/mattermost/tree/master/api).  In this code, I use a very nice [Python wrapper](https://github.com/Vaelor/python-mattermost-driver) that exposes the Mattermost REST endpoints conveniently.  An endpoint is available for deleting old messages, should you be interested in doing so.  My experimentation shows that this leaves a bunch of `Message deleted` indicators in the corresponding Mattermost channel instead of completely deleting all traces of old messages.