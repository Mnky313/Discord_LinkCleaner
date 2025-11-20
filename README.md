# Discord_LinkCleaner
Discord bot that cleans URLs &amp; Downloads/Fixes embedded videos

This is pretty old, messy code. I might get around to updating it at some point.

Designed to be run in a docker container:

example docker-compose.yml provided, make sure to create a .env with the following:

TOKEN=*bot token*
INVIDIOUS_FQDN=*FQDN for and Invidious Instance (this is kind of broken rn anyway I think)*
BLACKLISTED_USERS=*space seperated list of user ids to ignore (usually bots including itself)*
BLACKLISTED_CHANNELS=*space seperated list of channel ids to ignore*
