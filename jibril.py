import json
import logging
import sqlite3
import requests
import datetime
from httplib2 import Http
from base64 import b64encode
from threading import Thread
from googleapiclient.discovery import build
from oauth2client import file, client, tools
from telegram import InlineQueryResultArticle, ParseMode, InputTextMessageContent
from telegram.ext import Updater, CommandHandler, InlineQueryHandler, ConversationHandler, run_async

with open('config.json', 'r') as f:
    config = json.load(f)

def authorize(bot, update):
    user = update.message.from_user
    if update.message.chat.id in config['chatList'] or user.id in config['chatList']:
        print("{} : Authorized usage by: {} -- {}".format(datetime.datetime.now(), user.username, user.id))
        return True
    else:
        print("{} : Unauthorized usage attempted by: {} -- {}".format(datetime.datetime.now(), user.username, user.id))
        update.message.reply_text("Mere Imanity can't order me around.")
        return False

def login(token):
    scope = 'https://www.googleapis.com/auth/drive'
    store = file.Storage(token)
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', scope)
        creds = tools.run_flow(flow, store)
    service = build('drive', 'v3', http=creds.authorize(Http()))
    return service

def search(service, query):
    nextPageToken, nextPage, results = '', True, []
    while nextPage:
        result = service.files().list(
            q=query, 
            pageSize=1000,
            pageToken=nextPageToken, 
            fields='nextPageToken, files(id, name)', 
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora='allDrives').execute()
        if 'nextPageToken' in result: 
            nextPageToken = result['nextPageToken']
        else: 
            nextPage = False
        results += result['files']
    return(results)

def refresh(bot, update):
    if not authorize(bot, update):
        return
    anime, lastname = {}, ""
    reply = update.message.reply_text('Updating database')
    service = login('token.json')
    drives = service.drives().list(pageSize=100).execute()
    for drive in drives['drives']:
        if not drive['name'].startswith('Public Mirror'):
            continue
        if lastname != drive["name"].replace(" - N", "").split(" - ")[-1][:-3]:
            lastname = drive["name"].replace(" - N", "").split(" - ")[-1][:-3]
            reply.edit_text(f'Processing {lastname}')
        folders = search(service, f"mimeType = 'application/vnd.google-apps.folder' and not name contains '_gsdata_' and '{drive['id']}' in parents and trashed=false")
        for folder in folders:
            if folder['name'] not in anime.keys():
                anime.update({folder['name']: [{"id": folder['id'], "td": drive['id']}]})
            else:
                anime[folder['name']].append({"id": folder['id'], "td": drive['id']})
    reply.edit_text('Pushing Updates')
    push(anime)
    reply.edit_text('Database Updated')

def push(folders):
    con = sqlite3.connect('Jibril.db')
    cur = con.cursor()
    cur.execute(f'DROP TABLE IF EXISTS Jibril')
    cur.execute(f'CREATE TABLE Jibril (name NVARCHAR(250) PRIMARY KEY, id NVARCHAR(500));')
    for folder in folders.keys():
        ids = str([x['id'] for x in folders[folder]])[2:-2].replace("', '", " ")
        cur.execute(f'INSERT OR IGNORE INTO Jibril (name, id) VALUES ("{folder}", "{ids}");')
    con.commit()
    con.close()
    with open('jibril.json', 'w', encoding='utf8') as f:
        json.dump(folders, f, indent=4, ensure_ascii=False)
    data = {
        "client_id" : config["gdrive"]["client_id"],
        "client_secret" : config["gdrive"]["client_secret"],
        "redirect_uri" : "https://localhost:8080",
        "refresh_token" : config["gdrive"]["refresh_token"],
        "grant_type" : "refresh_token"
    }
    token = requests.post("https://oauth2.googleapis.com/token", data=data).json()["access_token"]
    headers = {
        "Authorization" : f"Bearer {token}",
        "Content-Type" : "application/json"
    }
    requests.patch(f"https://www.googleapis.com/upload/drive/v3/files/{config['gdrive']['id']}?uploadType=media", headers=headers, data=json.dumps(folders, indent=4, ensure_ascii=False).encode('utf-8'))

def dump(bot, update):
    if not authorize(bot, update):
        return
    with open('jibril.json', 'rb') as document:
        bot.send_document(update.effective_chat.id, document)

def inlineSearch(bot, update):
    if update.inline_query.from_user.id not in config['chatList']:
        return
    try:
        query = update.inline_query.query
        args = query.lower().split()
        items = []
        if not args:
            return
        sql = f'SELECT * FROM Jibril WHERE name LIKE "%{args[0]}%";'
        args.pop(0)
        for arg in args: 
            sql = sql[:-1] + f' AND name LIKE "%{arg}%";'
        con = sqlite3.connect('Jibril.db')
        cur = con.cursor()
        cur.execute(sql)
        results = cur.fetchall()
        for result in results:
            code = b64encode(result[0].encode('utf-8')).decode('utf-8')
            cont = f'[{result[0]}](https://drive.google.com/open?id={result[1].split()[0]})\n`{code}`'
            items.append(InlineQueryResultArticle(
                id=result[1][:10],
                title=result[0],
                input_message_content=InputTextMessageContent(cont, parse_mode=ParseMode.MARKDOWN)))
        update.inline_query.answer(items)
    except Exception as e:
        print(e)

def cancel(bot, update):
    if not authorize(bot, update): 
        return
    update.message.reply_text('Cancelled.')
    return ConversationHandler.END

def start(bot, update):
    if not authorize(bot, update): 
        return
    update.message.reply_text("Hi! I'm Jibril and I'm here to help you fix dead links. Tap /refresh update the search index and use inline mode to search.\n\n`@JibrilRobot [Keywords]`")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.ERROR)
logger = logging
updater = Updater(config['token'])
dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler('dump', dump))
dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('refresh', refresh))
dispatcher.add_handler(InlineQueryHandler(inlineSearch))
logger.info('Bot Started.')
updater.start_polling()
updater.idle()
