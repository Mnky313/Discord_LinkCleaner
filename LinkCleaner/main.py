###############
### IMPORTS ###
###############
import discord
import requests
import ffmpeg # You might need to manually install ffmpeg, pip didn't properly install it
import os
import re
import typing
import functools
import asyncio
from yt_dlp import YoutubeDL
from discord import app_commands, Intents, Client, Interaction, Webhook, Permissions
from discord.ext import commands
from discord.utils import get
from datetime import datetime
from sanitizr.sanitizr import URLCleaner
from async_timeout import timeout

#################
### VARIABLES ###
#################

# Discord bot values
intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Dictionaries
webhooks = {}

# Pull Variables:
TOKEN = os.getenv('TOKEN')
INVIDIOUS_FQDN = os.getenv('INVIDIOUS_FQDN')
BLACKLISTED_USERS = os.getenv('BLACKLISTED_USERS').split(" ")
BLACKLISTED_CHANNELS = os.getenv('BLACKLISTED_CHANNELS').split(" ")

# Constants
REDIRECTED_FQDNS = {
    "twitter.com": "vxtwitter.com",
    "x.com": "vxtwitter.com",
    "instagram.com": "kkinstagram.com",
    "threads.net": "fixthreads.net",
    "minecraft.fandom.com": "minecraft.wiki",
    "tiktok.com": "vxtiktok.com"
}
AUTO_DOWNLOAD_VIDEO_DOMAINS = ["ifunny","reddit"]
INVALID_VIDEO_PATHS = ["*.png","*.jpeg","*.avif","*.bmp","*.webp","*.jpg","*jpeg/*","*jpeg%3A*","*jpg/*","*jpg%3A*","*png/*","*png%3A*","*bmp/*","*bmp%3A*","*avif/*","*avif%3A*","*webp/*","*webp%3A*","@jpeg","@png","@bmp","@jpg","emojis/*","*.gif","*.gif?*",]
IGNORED_CLEAN_DOMAINS = ["discord","discordapp","skribbl"]
IGNORED_VIDEO_DOMAINS = ["tenor"]
IGNORED_REDIRECT_DOMAINS = ["kkinstagram","rxddit","fixvx"]
DOMAIN_YDL_OPTS = {
    "ifunny": {'playlist_index': 1,'postprocessors': [], 'postprocessor_args': {}},
    "discordapp": {'format': 'bestvideo*+bestaudio*','recode': 'mp4'}
}
DEFAULT_YDL_OPTS = {
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=mp4]/mp4',
    "postprocessors": [
        {"key": "FFmpegCopyStream"},
    ],
    "postprocessor_args": {
        "copystream": [
            "-c:v", "libx264"
        ],
    }
}

#################
### FUNCTIONS ###
#################

def log_event(level,event):
    '''
    Cleans up log entries
    '''
    for i in range(8-len(level)):
        level = level+" "
    print("["+datetime.now().strftime('%Y-%m-%d %H:%M:%S')+"] ["+level.upper()+"] "+event)

def parse_url(url):
    '''
    Splits a URL into it's components

    https ://   www    . example . com / testpage ? test=yes # completed
    └─┰─┘      └─┰─┘     └──┰──┘   └┰┘   └──┰───┘   └──┰───┘   └───┰───┘
    scheme | subdomain | domain  | tld |   path   |  params  |  fragment
             └───────────┰───────────┘
         fully qualified domain name (fqdn)
    '''

    # Basic validation check
    if url.count(' ') > 0:
        # Reject URLs with spaces
        log_event("ERROR","URL provided is invalid (contains spaces)")
        return False

    # Extract Scheme
    if url.count('://') == 1:
        scheme = url[0:url.find('://')]
    else:
        # Return False for invalid URLs
        log_event("ERROR","URL provided is invalid")
        return False

    # Extract combined (subdoamin), domain, tld

    seperatorPosDict = {}
    for seperator in ('/','?','#'):
        seperatorPosDict[seperator] = url[len(scheme)+3:].find(seperator)
    # Set netLocation (combined subdomain, domain, tld) by finding position of first
    netLocation = url[len(scheme)+3:min(i for i in (seperatorPosDict["/"],seperatorPosDict["?"],seperatorPosDict["#"],len(url)-len(scheme)-3) if i > 0)+len(scheme)+3]

    # Extract TLD
    if netLocation.count('.') > 1:
        # Check if TLD is country code (.co.xx)
        if netLocation[netLocation.rfind('.')-2:netLocation.rfind('.')] == 'co':
            # TLD is country code
            tld = netLocation[netLocation.rfind('.')-2:]
        else:
            # TLD is not country code
            tld = netLocation[netLocation.rfind('.')+1:]
    else:
        # TLD cannot be country code
        tld = netLocation[netLocation.find('.')+1:]

    # Extract subdomain (if exists)
    if netLocation[0:netLocation.rfind(tld)-1].count('.') > 0:
        subdomain = netLocation[0:netLocation[0:netLocation.rfind(tld)-1].rfind('.')]
    else:
        # No subdomain
        subdomain = ''

    # Extract what's left of the domain
    if len(subdomain) > 0:
        # If subdomain exists remove period
        domain = netLocation[len(subdomain)+1:netLocation.rfind(tld)-1]
    else:
        # Else it's not needed
        domain = netLocation[:netLocation.rfind(tld)-1]

    # Extract Path
    if seperatorPosDict["/"] > 0:
        if seperatorPosDict["#"] > 0 or seperatorPosDict["?"] > 0:
            # path ends at params/fragment
            path = url[seperatorPosDict["/"]+len(scheme)+4:min(i for i in (seperatorPosDict["?"],seperatorPosDict["#"]) if i > 0)+len(scheme)+3]
        else:
            # No params/fragment
            path = url[seperatorPosDict["/"]+len(scheme)+4:]
    else:
        # No path
        path = ''

    # Extract params & fragment
    if seperatorPosDict["?"] > 0:
        if seperatorPosDict["#"] > 0 and seperatorPosDict["#"] > seperatorPosDict["?"]:
            # fragment present
            fragment = url[seperatorPosDict["#"]+len(scheme)+4:]
            params = url[seperatorPosDict["?"]+len(scheme)+4:seperatorPosDict["#"]+len(scheme)+3]
        else:
            # No fragment, catch edge case of # before
            fragment = ''
            params = url[seperatorPosDict["?"]+len(scheme)+4:]
    elif seperatorPosDict["#"] > 0:
        # No params but fragment
        fragment = url[seperatorPosDict["#"]+len(scheme)+4:]
        params = ''
    else:
        # No params or fragment
        fragment = ''
        params = ''

    # Break params into dict
    paramsDict = {}
    if params:
        for param in params.split("&"):
            if param.count("=") == 1:
                paramsDict[param.split("=")[0]] = param.split("=")[1]
            else:
                # Malformed params
                log_event("WARNING","URL contains malformed parameters")

    parsedURL = {
        "scheme": scheme,
        "fqdn": netLocation,
        "subdomain": subdomain,
        "domain": domain,
        "tld": tld,
        "path": path,
        "params": paramsDict,
        "fragment": fragment
    }

    return parsedURL

def clean_url(url):
    '''
    Cleans and redirects provided URL
    '''
    # Parse URL
    if not parse_url(url):
        # URL is invalid
        log_event("ERROR","URL provided is invalid")
        return False

    # Check if URL redirects
    try:
        if parse_url(requests.get(url).url)["domain"] != parse_url(url)["domain"] and parse_url(url)["domain"] not in IGNORED_REDIRECT_DOMAINS:
            url = requests.get(url).url
    except:
        log_event("ERROR","Failed to request URL")

    # Clean URL
    cleanURL = URLCleaner().clean_url(url)
    parsedURL = parse_url(cleanURL)

    # Check if Domain is ignored
    if parsedURL["domain"] in IGNORED_CLEAN_DOMAINS:
        return url

    # Redirect Domains
    for key in REDIRECTED_FQDNS:
        if key == parsedURL["domain"]+"."+parsedURL["tld"]:
            cleanURL = cleanURL.replace(key, REDIRECTED_FQDNS[key])

    # Return URL
    return cleanURL

def clean_message(message,extractURLs):
    '''
    Cleans URLs in message & replaces them
    '''

    if extractURLs:
        extractedUrls = []
    # Split on code blocks
    multiCodeSecs = message.content.split("```")
    for i in range(len(multiCodeSecs))[0::2]:
        singleCodeSecs = multiCodeSecs[i].split("`")
        for j in range(len(singleCodeSecs))[0::2]:
            # Split message by lines
            msgLines = singleCodeSecs[j].split("\n")
            for k in range(len(msgLines)):
                # Split line by spaces
                msgWords = msgLines[k].split(" ")
                for l in range(len(msgWords)):
                    if msgWords[l][0:4] == "http":
                        cleanedUrl = clean_url(msgWords[l])
                        if extractURLs:
                            extractedUrls.append(cleanedUrl)
                        elif cleanedUrl and cleanedUrl != msgWords[l]:
                            msgWords[l] = cleanedUrl
                msgLines[k] = " ".join(msgWords)
            singleCodeSecs[j] = "\n".join(msgLines)
        multiCodeSecs[i] = "`".join(singleCodeSecs)
    newMsg = "```".join(multiCodeSecs)

    if extractURLs:
        return extractedUrls
    elif newMsg != message.content:
        return newMsg
    else:
        return False

def compress_video(input_file, output_file, boosted, count):
    '''
    Compresses video to target size
    Stolen from https://stackoverflow.com/questions/64430805/how-to-compress-video-to-target-size-by-python
    '''
    if boosted:
        target_size = 50000/count
    else:
        target_size = 10000/count
    if os.path.getsize(input_file) <= target_size * 1000: 
        os.rename(input_file, output_file)
        return(output_file)
    else:
        # Reference: https://en.wikipedia.org/wiki/Bit_rate#Encoding_bit_rate
        min_audio_bitrate = 32000
        max_audio_bitrate = 256000

        probe = ffmpeg.probe(input_file)
        # Video duration, in s.
        duration = float(probe['format']['duration'])
        # Audio bitrate, in bps.
        try:
            audio_bitrate = float(next((s for s in probe['streams'] if s['codec_type'] == 'audio'), None)['bit_rate'])
        except:
            audio_bitrate=0
        # Target total bitrate, in bps.
        target_total_bitrate = (target_size * 1024 * 8) / (1.073741824 * duration)

        # Target audio bitrate, in bps
        if 10 * audio_bitrate > target_total_bitrate:
            audio_bitrate = target_total_bitrate / 10
            if audio_bitrate < min_audio_bitrate < target_total_bitrate:
                audio_bitrate = min_audio_bitrate
            elif audio_bitrate > max_audio_bitrate:
                audio_bitrate = max_audio_bitrate
        # Target video bitrate, in bps.
        video_bitrate = target_total_bitrate - audio_bitrate

        i = ffmpeg.input(input_file)
        ffmpeg.output(i, os.devnull,
                    **{'c:v': 'libx264', 'b:v': video_bitrate, 'pass': 1, 'f': 'mp4'}
                    ).overwrite_output().run()
        ffmpeg.output(i, output_file,
                    **{'c:v': 'libx264', 'b:v': video_bitrate, 'pass': 2, 'c:a': 'aac', 'b:a': audio_bitrate}
                    ).overwrite_output().run()
        os.remove(input_file)
        return(output_file)

def fetch_compress_video(url, ydl_opts, video_full_path, boosted, count):
    '''
    Fetch video through YT-DLP & compress it to send on Discord
    '''
    with YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download(url)
            compress_output = compress_video(video_full_path+".mp4", video_full_path+"-compressed.mp4", boosted, count)
            return compress_output
        except Exception as e:
            print(e)
            return False

async def fetch_thread(channel, fetch_compress_video: typing.Callable, *args, **kwargs) -> typing.Any:
    '''
    Called to run fetch_compress_video in seperate thread (to preserve heartbeat)
    '''
    async with channel.typing():
        return await client.loop.run_in_executor(None, functools.partial(fetch_compress_video, *args, **kwargs))

def test_url_for_video(url,parsedURL):
    if parsedURL["domain"] in IGNORED_VIDEO_DOMAINS:
        return False
    for path in INVALID_VIDEO_PATHS:
        if path[0] == "*" and path[-1] == "*":
            if path.replace("*","") in parsedURL["path"]:
                return False
        elif path[-1] == "*":
            if path.replace("*","") == parsedURL["path"][0:len(path.replace("*",""))]:
                return False
        elif path[0] == "*":
            if path.replace("*","") == parsedURL["path"][len(path.replace("*",""))*-1:]:
                return False
    try:
        with YoutubeDL({"simulate": True, "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b"}) as ydl:
            ydl.download(url)
        return True
    except:
        return False

async def download_videos(urls, message, interaction):
    vidFiles = []
    for url in urls:
        parsedURL = parse_url(url)
        if parsedURL:
            if test_url_for_video(url, parsedURL):
                if message:
                    outputFile = str(message.id)+"-"+str(urls.index(url))
                    channel = message.channel
                else:
                    outputFile = "video"
                    channel = interaction.channel
                ydlOutput = {'outtmpl': outputFile+".mp4"}
                ydlDomainOpts = {}
                for key in DOMAIN_YDL_OPTS:
                    if key == parsedURL["domain"]:
                        ydlDomainOpts = DOMAIN_YDL_OPTS[key]
                try:
                    async with timeout(60):
                        vidFiles.append(await fetch_thread(channel, fetch_compress_video, url, dict(list(ydlOutput.items()) + list(DEFAULT_YDL_OPTS.items()) + list(ydlDomainOpts.items())), outputFile, False, len(urls)))
                except asyncio.TimeoutError:
                    break
    if len(vidFiles):
        return vidFiles
    else:
        return False

async def test_message_for_videos(message):
    urls = clean_message(message,True)
    for url in urls:
        parsedURL = parse_url(url)
        if parsedURL:
            if test_url_for_video(url, parsedURL):
                return True
    return False

# Sends updated message
async def send_message(message, newMsg, vidFiles):
    try:
        # Channels
        if not message.channel.id in webhooks:
            ### Clears old webhooks from the bot ###
            channel_webhooks = await message.channel.webhooks() 
            for w in channel_webhooks:
                if w.name == "LinkCleaner2":
                    await w.delete()
            ### END Clears old webhooks from the bot ###
            webhooks[message.channel.id] = await message.channel.create_webhook(name="LinkCleaner2")
            BLACKLISTED_USERS.append(str(webhooks[message.channel.id].id))

        files = []
        if vidFiles:
            for vid in vidFiles:
                if vid:
                    files.append(discord.File("./"+vid))

            tmpMessage = await webhooks[message.channel.id].send(content=newMsg, files=files, username=message.author.display_name, avatar_url=message.author.display_avatar.url, wait=True, suppress_embeds=True)

            for vid in vidFiles:
                if vid:
                    os.remove("./"+vid)
        else:
            tmpMessage = await webhooks[message.channel.id].send(content=newMsg, username=message.author.display_name, avatar_url=message.author.display_avatar.url, wait=True)
        return tmpMessage
    except AttributeError:
        # DMs
        files = []
        if vidFiles:
            for vid in vidFiles:
                if vid:
                    files.append(discord.File("./"+vid))
            newMessage = await message.channel.send(files=files)
            for vid in vidFiles:
                if vid:
                    os.remove("./"+vid)

# Extracts youtube video IDs from parsedURL
def extract_youtube_vid_id(parsedURL):
    try:
        vidID = parsedURL["params"]["v"]
    except:
        # Not using params
        pathParts = parsedURL["path"].split("/")
        for part in pathParts:
            if len(part) < 13 and len(part) > 9:
                if part.isalnum():
                    vidID = part
                elif "_" in part or "-" in part:
                    if part.replace("_", "A").replace("-", "A").isalnum():
                        vidID = part
    return(vidID)

################
### COMMANDS ###
################

# Clean command (Cleans links and replies ephemerally)
@tree.command(name = "clean", description = "Cleans links")
async def clean(interaction, link: str):
    cleanedURL = clean_url(link)
    await interaction.response.send_message(cleanedURL, ephemeral=True)

# Attempts to Download video from provided URL
@tree.command(name = "download", description = "Attempts to Download video from provided URL")
async def download(interaction, link: str):
    await interaction.response.send_message("Attempting Download", ephemeral=True)
    parsedURL = parse_url(link)
    if test_url_for_video(link,parsedURL):
        vidFiles = await download_videos([link], False, interaction)
        if vidFiles:
            await interaction.channel.send(file=discord.File("./"+vidFiles[0]))
            os.remove("./"+vidFiles[0])

##############
### EVENTS ###
##############

@client.event
async def on_message(message):
    if str(message.author.id) not in BLACKLISTED_USERS and str(message.channel.id) not in BLACKLISTED_CHANNELS:
        if "http://" in message.content or "https://" in message.content:
            cleanedMessage = clean_message(message,False)
            extractedURLs = clean_message(message,True)
            containsVideos = await test_message_for_videos(message)
            reactions = []
            newMessage = False
            if cleanedMessage:
                newMessage = await send_message(message, cleanedMessage, False)
                await message.delete()
                if containsVideos:
                    vidURLs = []
                    for url in extractedURLs:
                        if parse_url(url)["domain"] in AUTO_DOWNLOAD_VIDEO_DOMAINS:
                            vidURLs.append(url)
                        if parse_url(url)["domain"] in ["youtube"]:
                            if '➡️' not in reactions:
                                reactions.append('➡️')
                    if vidURLs:
                        vidFiles = await download_videos(vidURLs, message, False)
                        await send_message(message, cleanedMessage, vidFiles)
                        await message.delete()
                    else:
                        reactions.append('💾')
            elif containsVideos:
                vidURLs = []
                for url in extractedURLs:
                    if parse_url(url)["domain"] in AUTO_DOWNLOAD_VIDEO_DOMAINS:
                        vidURLs.append(url)
                    if parse_url(url)["domain"] in ["youtube"]:
                        if '➡️' not in reactions:
                            reactions.append('➡️')
                if vidURLs:
                    vidFiles = await download_videos(vidURLs, message, False)
                    await send_message(message, message.content, vidFiles)
                    await message.delete()
                else:
                    reactions.append('💾')
            for emoji in reactions:
                if newMessage:
                    await newMessage.add_reaction(emoji)
                else:
                    await message.add_reaction(emoji)

@client.event
async def on_reaction_add(reaction, user):
    if str(user.id) not in BLACKLISTED_USERS and str(reaction.message.channel.id) not in BLACKLISTED_CHANNELS:
        if reaction.emoji == '💾':
            containsVideos = await test_message_for_videos(reaction.message)
            extractedURLs = clean_message(reaction.message,True)
            if containsVideos:
                vidURLs = []
                for url in extractedURLs:
                    vidURLs.append(url)
                if vidURLs:
                    vidFiles = await download_videos(vidURLs, reaction.message, False)
                    await send_message(reaction.message, reaction.message.content, vidFiles)
                    await reaction.message.delete()
        elif reaction.emoji == '➡️':
            extractedURLs = clean_message(reaction.message,True)
            for url in extractedURLs:
                parsedURL = parse_url(url)
                if parsedURL["domain"] == "youtube":
                    vidID = extract_youtube_vid_id(parsedURL)
                    await send_message(reaction.message, "https://"+INVIDIOUS_FQDN+"/embed/"+vidID+"?raw=1&quality=medium", False)
                    await reaction.message.edit(suppress=True)


##############
### RUNNER ###
##############

@client.event
async def on_ready():
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='Waiting for links'))
    await tree.sync()
client.run(TOKEN)
