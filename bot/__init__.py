import logging
import socket
import faulthandler
import aria2p
import qbittorrentapi as qba
import telegram.ext as tg

from logging import getLogger
from os import remove as osremove, path as ospath, environ
from requests import get as rget
from json import loads as jsnloads
from subprocess import Popen, run as srun
from time import sleep, time
from threading import Thread, Lock
from pyrogram import Client
from dotenv import load_dotenv

faulthandler.enable()

socket.setdefaulttimeout(600)

botStartTime = time()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('log.txt'), logging.StreamHandler()],
                    level=logging.INFO)

LOGGER = logging.getLogger

load_dotenv('config.env', override=True)

def getConfig(name: str):
    return environ[name]

try:
    NETRC_URL = getConfig('NETRC_URL')
    if len(NETRC_URL) == 0:
        raise KeyError
    try:
        res = rget(NETRC_URL)
        if res.status_code == 200:
            with open('.netrc', 'wb+') as f:
                f.write(res.content)
                f.close()
        else:
            logging.error(f"Failed to download .netrc {res.status_code}")
    except Exception as e:
        logging.error(f"NETRC_URL: {e}")
except KeyError:
    pass
try:
    SERVER_PORT = getConfig('SERVER_PORT')
    if len(SERVER_PORT) == 0:
        raise KeyError
except KeyError:
    SERVER_PORT = 80

PORT = environ.get('PORT', SERVER_PORT)
web = Popen([f"gunicorn wserver:start_server --bind 0.0.0.0:{PORT} --worker-class aiohttp.GunicornWebWorker"], shell=True)
alive = Popen(["python3", "alive.py"])
nox = Popen(["qbittorrent-nox", "--profile=."])
if not ospath.exists('.netrc'):
    srun(["touch", ".netrc"])
srun(["cp", ".netrc", "/root/.netrc"])
srun(["chmod", "600", ".netrc"])
srun(["chmod", "+x", "aria.sh"])
srun(["./aria.sh"], shell=True)
sleep(0.5)

Interval = []
DRIVES_NAMES = []
DRIVES_IDS = []
INDEX_URLS = []

try:
    if bool(getConfig('_____REMOVE_THIS_LINE_____')):
        logging.error('The README.md file there to be read! Exiting now!')
        exit()
except KeyError:
    pass

aria2 = aria2p.API(
    aria2p.Client(
        host="http://localhost",
        port=6800,
        secret="",
    )
)

def get_client() -> qba.TorrentsAPIMixIn:
    return qba.Client(host="localhost", port=8090)

"""
trackers = subprocess.check_output(["curl -Ns https://raw.githubusercontent.com/XIU2/TrackersListCollection/master/all.txt https://ngosang.github.io/trackerslist/trackers_all_http.txt https://newtrackon.com/api/all | awk '$0'"], shell=True).decode('utf-8')

trackerslist = set(trackers.split("\n"))
trackerslist.remove("")
trackerslist = "\n\n".join(trackerslist)
get_client().application.set_preferences({"add_trackers":f"{trackerslist}"})
"""

DOWNLOAD_DIR = None
BOT_TOKEN = None

download_dict_lock = Lock()
status_reply_dict_lock = Lock()
# Key: update.effective_chat.id
# Value: telegram.Message
status_reply_dict = {}
# Key: update.message.message_id
# Value: An object of Status
download_dict = {}
# key: rss_title
# value: [rss_feed, last_link, last_title]
rss_dict = {}

AUTHORIZED_CHATS = set()
SUDO_USERS = set()
AS_DOC_USERS = set()
EXTENTION_FILTER = set(['.torrent'])
AS_MEDIA_USERS = set()
EXTENSION_FILTER = set()
if ospath.exists('authorized_chats.txt'):
    with open('authorized_chats.txt', 'r+') as f:
        lines = f.readlines()
        for line in lines:
            AUTHORIZED_CHATS.add(int(line.split()[0]))
if ospath.exists('sudo_users.txt'):
    with open('sudo_users.txt', 'r+') as f:
        lines = f.readlines()
        for line in lines:
            SUDO_USERS.add(int(line.split()[0]))

try:
    aid = getConfig('AUTHORIZED_CHATS')
    aid = aid.split()
    for _id in aid:
        AUTHORIZED_CHATS.add(int(_id.strip()))
except:
    pass
try:
    aid = getConfig('SUDO_USERS')
    aid = aid.split()
    for _id in aid:
        SUDO_USERS.add(int(_id.strip()))
except:
    pass
try:
    fx = getConfig('EXTENSION_FILTER')
    if len(fx) > 0:
        fx = fx.split()
        for x in fx:
            EXTENSION_FILTER.add(x.strip().lower())
except:
    pass  
try:
    BOT_TOKEN = getConfig('BOT_TOKEN')
    parent_id = getConfig('GDRIVE_FOLDER_ID')
    DOWNLOAD_DIR = getConfig('DOWNLOAD_DIR')
    if not DOWNLOAD_DIR.endswith("/"):
        DOWNLOAD_DIR = DOWNLOAD_DIR + '/'
    DOWNLOAD_STATUS_UPDATE_INTERVAL = int(getConfig('DOWNLOAD_STATUS_UPDATE_INTERVAL'))
    OWNER_ID = int(getConfig('OWNER_ID'))
    AUTO_DELETE_MESSAGE_DURATION = int(getConfig('AUTO_DELETE_MESSAGE_DURATION'))
    AUTO_DELETE = int(getConfig('AUTO_DELETE'))
    TELEGRAM_API = getConfig('TELEGRAM_API')
    TELEGRAM_HASH = getConfig('TELEGRAM_HASH')
    LOG_CHANNEL_LINK1 = getConfig('LOG_CHANNEL_LINK1')
    LOG_CHANNEL_LINK2 = getConfig('LOG_CHANNEL_LINK2')
except KeyError as e:
    LOGGER(__name__).error("Check the Main Variables")
    exit(1)

LOGGER(__name__).info("Generating BOT_STRING_SESSION")
app = Client('pyrogram', api_id=int(TELEGRAM_API), api_hash=TELEGRAM_HASH, bot_token=BOT_TOKEN, no_updates=True)

def aria2c_init():
    try:
        logging.info("Initializing Aria2c")
        link = "https://releases.ubuntu.com/21.10/ubuntu-21.10-desktop-amd64.iso.torrent"
        aria2.add_uris([link], {'dir': DOWNLOAD_DIR})
        sleep(3)
        downloads = aria2.get_downloads()
        sleep(30)
        for download in downloads:
            aria2.remove([download], force=True, files=True)
    except Exception as e:
        logging.error(f"Aria2c initializing error: {e}")
        pass

if not ospath.isfile(".restartmsg"):
    Thread(target=aria2c_init).start()
    sleep(1)

try:
    DB_URI = getConfig('DATABASE_URL')
    if len(DB_URI) == 0:
        raise KeyError
except KeyError:
    DB_URI = None
tgBotMaxFileSize = 2097151000
try:
    TG_SPLIT_SIZE = getConfig('TG_SPLIT_SIZE')
    if len(TG_SPLIT_SIZE) == 0 or int(TG_SPLIT_SIZE) > tgBotMaxFileSize:
        raise KeyError
    TG_SPLIT_SIZE = int(TG_SPLIT_SIZE)
except:
    TG_SPLIT_SIZE = tgBotMaxFileSize
try:
    USER_SESSION_STRING = getConfig('USER_SESSION_STRING')
    if len(USER_SESSION_STRING) == 0:
        raise KeyError
    rss_session = Client(name='rss_session', api_id=int(TELEGRAM_API), api_hash=TELEGRAM_HASH, session_string=USER_SESSION_STRING, parse_mode=enums.ParseMode.HTML, no_updates=True)
    if not rss_session:
        LOGGER(__name__).error("Cannot initialized User Session. Please regenerate USER_SESSION_STRING")
    else:
        rss_session.start()
        if (rss_session.get_me()).is_premium:
            if not LEECH_LOG:
                LOGGER(__name__).error("You must set LEECH_LOG for uploads. Eiting now.")
                try: rss_session.send_message(OWNER_ID, "You must set LEECH_LOG for uploads. Bot is closing. Bye.")
                except Exception as e: LOGGER(__name__).exception(e)
                rss_session.stop()
                app.stop()
                exit(1)
            TG_SPLIT_SIZE = 4194304000
            LOGGER(__name__).info("Premium user detected. Upload limit is 4GB now.")
        elif (not DB_URI) or (not RSS_CHAT_ID):
            rss_session.stop()
            LOGGER(__name__).info(f"Not using rss. if you want to use fill RSS_CHAT_ID and DB_URI variables.")
except:
    LOGGER(__name__).info("USER_SESSION_STRING: not found ")
    USER_SESSION_STRING = None
    rss_session = None
LOGGER(__name__).info(f"TG_SPLIT_SIZE: {TG_SPLIT_SIZE}")
try:
    STATUS_LIMIT = getConfig('STATUS_LIMIT')
    if len(STATUS_LIMIT) == 0:
        raise KeyError
    else:
        STATUS_LIMIT = int(STATUS_LIMIT)
except KeyError:
    STATUS_LIMIT = None
try:
    MEGA_API_KEY = getConfig('MEGA_API_KEY')
    if len(MEGA_API_KEY) == 0:
        raise KeyError
except KeyError:
    logging.warning('MEGA API KEY not provided!')
    MEGA_API_KEY = None
try:
    MEGA_EMAIL_ID = getConfig('MEGA_EMAIL_ID')
    MEGA_PASSWORD = getConfig('MEGA_PASSWORD')
    if len(MEGA_EMAIL_ID) == 0 or len(MEGA_PASSWORD) == 0:
        raise KeyError
except KeyError:
    logging.warning('MEGA Credentials not provided!')
    MEGA_EMAIL_ID = None
    MEGA_PASSWORD = None
try:
    UPTOBOX_TOKEN = getConfig('UPTOBOX_TOKEN')
    if len(UPTOBOX_TOKEN) == 0:
        raise KeyError
except KeyError:
    UPTOBOX_TOKEN = None
try:
    INDEX_URL = getConfig('INDEX_URL').rstrip("/")
    if len(INDEX_URL) == 0:
        raise KeyError
    else:
        INDEX_URLS.append(INDEX_URL)
except KeyError:
    INDEX_URL = None
    INDEX_URLS.append(None)
try:
    SEARCH_API_LINK = getConfig('SEARCH_API_LINK').rstrip("/")
    if len(SEARCH_API_LINK) == 0:
        raise KeyError
except KeyError:
    SEARCH_API_LINK = None
try:
    RSS_COMMAND = getConfig('RSS_COMMAND')
    if len(RSS_COMMAND) == 0:
        raise KeyError
except KeyError:
    RSS_COMMAND = None
try:
    TORRENT_DIRECT_LIMIT = getConfig('TORRENT_DIRECT_LIMIT')
    if len(TORRENT_DIRECT_LIMIT) == 0:
        raise KeyError
    else:
        TORRENT_DIRECT_LIMIT = float(TORRENT_DIRECT_LIMIT)
except KeyError:
    TORRENT_DIRECT_LIMIT = None
try:
    CLONE_LIMIT = getConfig('CLONE_LIMIT')
    if len(CLONE_LIMIT) == 0:
        raise KeyError
    else:
        CLONE_LIMIT = float(CLONE_LIMIT)
except KeyError:
    CLONE_LIMIT = None
try:
    MEGA_LIMIT = getConfig('MEGA_LIMIT')
    if len(MEGA_LIMIT) == 0:
        raise KeyError
    else:
        MEGA_LIMIT = float(MEGA_LIMIT)
except KeyError:
    MEGA_LIMIT = None
try:
    ZIP_UNZIP_LIMIT = getConfig('ZIP_UNZIP_LIMIT')
    if len(ZIP_UNZIP_LIMIT) == 0:
        raise KeyError
    else:
        ZIP_UNZIP_LIMIT = float(ZIP_UNZIP_LIMIT)
except KeyError:
    ZIP_UNZIP_LIMIT = None
try:
    RSS_CHAT_ID = getConfig('RSS_CHAT_ID')
    if len(RSS_CHAT_ID) == 0:
        raise KeyError
    else:
        RSS_CHAT_ID = int(RSS_CHAT_ID)
except KeyError:
    RSS_CHAT_ID = None
try:
    RSS_DELAY = getConfig('RSS_DELAY')
    if len(RSS_DELAY) == 0:
        raise KeyError
    else:
        RSS_DELAY = int(RSS_DELAY)
except KeyError:
    RSS_DELAY = 900
try:
    BUTTON_FOUR_NAME = getConfig('BUTTON_FOUR_NAME')
    BUTTON_FOUR_URL = getConfig('BUTTON_FOUR_URL')
    if len(BUTTON_FOUR_NAME) == 0 or len(BUTTON_FOUR_URL) == 0:
        raise KeyError
except KeyError:
    BUTTON_FOUR_NAME = None
    BUTTON_FOUR_URL = None
try:
    BUTTON_FIVE_NAME = getConfig('BUTTON_FIVE_NAME')
    BUTTON_FIVE_URL = getConfig('BUTTON_FIVE_URL')
    if len(BUTTON_FIVE_NAME) == 0 or len(BUTTON_FIVE_URL) == 0:
        raise KeyError
except KeyError:
    BUTTON_FIVE_NAME = None
    BUTTON_FIVE_URL = None
try:
    BUTTON_SIX_NAME = getConfig('BUTTON_SIX_NAME')
    BUTTON_SIX_URL = getConfig('BUTTON_SIX_URL')
    if len(BUTTON_SIX_NAME) == 0 or len(BUTTON_SIX_URL) == 0:
        raise KeyError
except KeyError:
    BUTTON_SIX_NAME = None
    BUTTON_SIX_URL = None
try:
    STOP_DUPLICATE = getConfig('STOP_DUPLICATE')
    STOP_DUPLICATE = STOP_DUPLICATE.lower() == 'true'
except KeyError:
    STOP_DUPLICATE = False
try:
    VIEW_LINK = getConfig('VIEW_LINK')
    VIEW_LINK = VIEW_LINK.lower() == 'true'
except KeyError:
    VIEW_LINK = False
try:
    IS_TEAM_DRIVE = getConfig('IS_TEAM_DRIVE')
    IS_TEAM_DRIVE = IS_TEAM_DRIVE.lower() == 'true'
except KeyError:
    IS_TEAM_DRIVE = False
try:
    USE_SERVICE_ACCOUNTS = getConfig('USE_SERVICE_ACCOUNTS')
    USE_SERVICE_ACCOUNTS = USE_SERVICE_ACCOUNTS.lower() == 'true'
except KeyError:
    USE_SERVICE_ACCOUNTS = False
try:
    BLOCK_MEGA_FOLDER = getConfig('BLOCK_MEGA_FOLDER')
    BLOCK_MEGA_FOLDER = BLOCK_MEGA_FOLDER.lower() == 'true'
except KeyError:
    BLOCK_MEGA_FOLDER = False
try:
    BLOCK_MEGA_LINKS = getConfig('BLOCK_MEGA_LINKS')
    BLOCK_MEGA_LINKS = BLOCK_MEGA_LINKS.lower() == 'true'
except KeyError:
    BLOCK_MEGA_LINKS = False
try:
    WEB_PINCODE = getConfig('WEB_PINCODE')
    WEB_PINCODE = WEB_PINCODE.lower() == 'true'
except KeyError:
    WEB_PINCODE = False
try:
    SHORTENER = getConfig('SHORTENER')
    SHORTENER_API = getConfig('SHORTENER_API')
    if len(SHORTENER) == 0 or len(SHORTENER_API) == 0:
        raise KeyError
except KeyError:
    SHORTENER = None
    SHORTENER_API = None
try:
    IGNORE_PENDING_REQUESTS = getConfig("IGNORE_PENDING_REQUESTS")
    IGNORE_PENDING_REQUESTS = IGNORE_PENDING_REQUESTS.lower() == 'true'
except KeyError:
    IGNORE_PENDING_REQUESTS = False
try:
    BASE_URL = getConfig('BASE_URL_OF_BOT').rstrip("/")
    if len(BASE_URL) == 0:
        raise KeyError
except KeyError:
    logging.warning('BASE_URL_OF_BOT not provided!')
    BASE_URL = None
try:
    IS_VPS = getConfig('IS_VPS')
    IS_VPS = IS_VPS.lower() == 'true'
except KeyError:
    IS_VPS = False
try:
    AS_DOCUMENT = getConfig('AS_DOCUMENT')
    AS_DOCUMENT = AS_DOCUMENT.lower() == 'true'
except KeyError:
    AS_DOCUMENT = False
try:
    EQUAL_SPLITS = getConfig('EQUAL_SPLITS')
    EQUAL_SPLITS = EQUAL_SPLITS.lower() == 'true'
except KeyError:
    EQUAL_SPLITS = False
try:
    QB_SEED = getConfig('QB_SEED')
    QB_SEED = QB_SEED.lower() == 'true'
except KeyError:
    QB_SEED = False
try:
    CUSTOM_FILENAME = getConfig('CUSTOM_FILENAME')
    if len(CUSTOM_FILENAME) == 0:
        raise KeyError
except KeyError:
    CUSTOM_FILENAME = None
try:
    PHPSESSID = getConfig('PHPSESSID')
    CRYPT = getConfig('CRYPT')
    if len(PHPSESSID) == 0 or len(CRYPT) == 0:
        raise KeyError
except KeyError:
    PHPSESSID = None
    CRYPT = None
try:
    APPDRIVE_EMAIL = getConfig('APPDRIVE_EMAIL')
    APPDRIVE_PASS = getConfig('APPDRIVE_PASS')
    if len(APPDRIVE_EMAIL) == 0 or len(APPDRIVE_PASS) == 0:
        raise KeyError
except KeyError:
    APPDRIVE_EMAIL = None
    APPDRIVE_PASS = None
    
try:
    BOT_PM = getConfig('BOT_PM')
    BOT_PM = BOT_PM.lower() == 'true'
except KeyError:
    BOT_PM = False
    
try:
    GD_INFO = getConfig('GD_INFO')
    if len(GD_INFO) == 0:
        GD_INFO = 'Uploaded by MSP Mirror Bot'
except KeyError:
    GD_INFO = 'Uploaded by MSP Mirror Bot'

try:
    TITLE_NAME = getConfig('TITLE_NAME')
    if len(TITLE_NAME) == 0:
        TITLE_NAME = 'MSP-Mirror-Search'
except KeyError:
    TITLE_NAME = 'MSP-Mirror-Search'

try:
    AUTHOR_NAME = getConfig('AUTHOR_NAME')
    if len(AUTHOR_NAME) == 0:
        AUTHOR_NAME = 'MSP-Mirror-Bot'
except KeyError:
    AUTHOR_NAME = 'MSP-Mirror-Bot'

try:
    AUTHOR_URL = getConfig('AUTHOR_URL')
    if len(AUTHOR_URL) == 0:
        AUTHOR_URL = 'https://t.me/MSPbots'
except KeyError:
    AUTHOR_URL = 'https://t.me/MSPbots'

try:
    HEROKU_APP_NAME = getConfig('HEROKU_APP_NAME')
    if len(HEROKU_APP_NAME) == 0:
        raise KeyError
except KeyError:
    logging.warning('HEROKU_APP_NAME not provided!')
    HEROKU_APP_NAME = None

try:
    HEROKU_API_KEY = getConfig('HEROKU_API_KEY')
    if len(HEROKU_API_KEY) == 0:
        raise KeyError
except KeyError:
    logging.warning('HEROKU_API_KEY not provided!')
    HEROKU_API_KEY = None

try:
    IMAGE_URL = getConfig('IMAGE_URL')
    if len(IMAGE_URL) == 0:
        IMAGE_URL = None
except KeyError:
    IMAGE_URL = 'https://telegra.ph/file/f85d8e57d44ea5deb0d69.jpg'
    
try:
    LOG_CHANNEL = int(getConfig('LOG_CHANNEL'))
    if int(LOG_CHANNEL) == 0:
        raise KeyError
except KeyError:
    logging.warning('LOG_CHANNEL not provided!')
    LOG_CHANNEL = None
    
try:
    LOG_CHANNEL_LOGGER = int(getConfig('LOG_CHANNEL_LOGGER'))
    if int(LOG_CHANNEL_LOGGER) == 0:
        raise KeyError
except KeyError:
    logging.warning('LOG_CHANNEL_LOGGER not provided!')
    LOG_CHANNEL_LOGGER = None 
    
try:
    LOG_LEECH = int(getConfig('LOG_LEECH'))
    if int(LOG_LEECH) == 0:
        raise KeyError
except KeyError:
    logging.warning('LOG_LEECH not provided!')
    LOG_LEECH = None
    
try:
    TIMEZONE = getConfig('TIMEZONE')
    if len(TIMEZONE) == 0:
        TIMEZONE = None
except KeyError:
    TIMEZONE = 'Asia/Kolkata'
    
try:
    BOT_NO = getConfig('BOT_NO')
    if len(BOT_NO) == 0:
        BOT_NO = None
except KeyError:
    BOT_NO = '0'

try:
    CHANNEL_USERNAME = getConfig('CHANNEL_USERNAME')
    if len(CHANNEL_USERNAME) == 0:
        raise KeyError
except KeyError:
    logging.warning('CHANNEL_USERNAME not provided!')
    CHANNEL_USERNAME = None
try:
    TOKEN_PICKLE_URL = getConfig('TOKEN_PICKLE_URL')
    if len(TOKEN_PICKLE_URL) == 0:
        raise KeyError
    try:
        res = rget(TOKEN_PICKLE_URL)
        if res.status_code == 200:
            with open('token.pickle', 'wb+') as f:
                f.write(res.content)
                f.close()
        else:
            logging.error(f"Failed to download token.pickle, link got HTTP response: {res.status_code}")
    except Exception as e:
        logging.error(f"TOKEN_PICKLE_URL: {e}")
except KeyError:
    pass
try:
    ACCOUNTS_ZIP_URL = getConfig('ACCOUNTS_ZIP_URL')
    if len(ACCOUNTS_ZIP_URL) == 0:
        raise KeyError
    else:
        try:
            res = rget(ACCOUNTS_ZIP_URL)
            if res.status_code == 200:
                with open('accounts.zip', 'wb+') as f:
                    f.write(res.content)
                    f.close()
            else:
                logging.error(f"Failed to download accounts.zip, link got HTTP response: {res.status_code}")
        except Exception as e:
            logging.error(f"ACCOUNTS_ZIP_URL: {e}")
            raise KeyError
        srun(["unzip", "-q", "-o", "accounts.zip"])
        srun(["chmod", "-R", "777", "accounts"])
        osremove("accounts.zip")
except KeyError:
    pass
try:
    MULTI_SEARCH_URL = getConfig('MULTI_SEARCH_URL')
    if len(MULTI_SEARCH_URL) == 0:
        raise KeyError
    try:
        res = rget(MULTI_SEARCH_URL)
        if res.status_code == 200:
            with open('drive_folder', 'wb+') as f:
                f.write(res.content)
                f.close()
        else:
            logging.error(f"Failed to download drive_folder, link got HTTP response: {res.status_code}")
    except Exception as e:
        logging.error(f"MULTI_SEARCH_URL: {e}")
except KeyError:
    pass
try:
    YT_COOKIES_URL = getConfig('YT_COOKIES_URL')
    if len(YT_COOKIES_URL) == 0:
        raise KeyError
    try:
        res = rget(YT_COOKIES_URL)
        if res.status_code == 200:
            with open('cookies.txt', 'wb+') as f:
                f.write(res.content)
                f.close()
        else:
            logging.error(f"Failed to download cookies.txt, link got HTTP response: {res.status_code}")
    except Exception as e:
        logging.error(f"YT_COOKIES_URL: {e}")
except KeyError:
    pass

DRIVES_NAMES.append("Main")
DRIVES_IDS.append(parent_id)
if ospath.exists('drive_folder'):
    with open('drive_folder', 'r+') as f:
        lines = f.readlines()
        for line in lines:
            try:
                temp = line.strip().split()
                DRIVES_IDS.append(temp[1])
                DRIVES_NAMES.append(temp[0].replace("_", " "))
            except:
                pass
            try:
                INDEX_URLS.append(temp[2])
            except IndexError as e:
                INDEX_URLS.append(None)
try:
    SEARCH_PLUGINS = getConfig('SEARCH_PLUGINS')
    if len(SEARCH_PLUGINS) == 0:
        raise KeyError
    SEARCH_PLUGINS = jsnloads(SEARCH_PLUGINS)
    qbclient = get_client()
    qb_plugins = qbclient.search_plugins()
    if qb_plugins:
        for plugin in qb_plugins:
            p = plugin['name']
            qbclient.search_uninstall_plugin(names=p)
    qbclient.search_install_plugin(SEARCH_PLUGINS)
except KeyError:
    SEARCH_PLUGINS = None

updater = tg.Updater(token=BOT_TOKEN)
bot = updater.bot
dispatcher = updater.dispatcher
job_queue = updater.job_queue
