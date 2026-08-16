import telebot
import requests
import io
import os
import re
import threading
from flask import Flask

# --- कॉन्फिगरेशन ---
BOTTOKEN = '8984791001:AAEWdpO_Qfgw3d10S69QsMSWkk5SUZwktR8'
TARGETCHANNEL = '@mycoures123'

bot = telebot.TeleBot(BOTTOKEN)
app = Flask("bot")

@app.route('/')
def index():
    return "PSCLive Final Bot Online"

usersessions = {}

APIHEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "region": "IN"
}

def extractitems(resjson):
    if isinstance(resjson, list):
        return resjson
    if isinstance(resjson, dict):
        d = resjson.get('data', {})
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            for k in ['courseContent', 'contents', 'list', 'data', 'files', 'materials']:
                if k in d and isinstance(d[k], list):
                    return d[k]
        for k in ['courseContent', 'contents', 'data', 'list']:
            if k in resjson and isinstance(resjson[k], list):
                return resjson[k]
    return []

@bot.message_handler(commands=['start'])
def handlestart(message):
    chatid = message.chat.id
    usersessions[chatid] = {'step': 'WAITING_URL'}
    bot.send_message(
        chatid,
        "👋 PSCLive ऑटो एक्सट्रैक्टर\n\n"
        "1️⃣ सबसे पहले कोर्स का URL भेजें:\n"
        "👉 उदाहरण: https://app.psclive.com/new-courses/221/content",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda msg: usersessions.get(msg.chat.id, {}).get('step') == 'WAITING_URL')
def handleurl(message):
    chatid = message.chat.id
    url = message.text.strip()
    
    coursematch = re.search(r'courses/(\d+)', url)
    courseid = coursematch.group(1) if coursematch else (url if url.isdigit() else None)
    
    if not courseid:
        bot.send_message(chatid, "❌ गलत URL! कृपया सही कोर्स लिंक या ID भेजें।")
        return
        
    usersessions[chatid]['courseid'] = courseid
    usersessions[chatid]['step'] = 'WAITING_TOKEN'
    
    bot.send_message(
        chatid,
        f"✅ कोर्स ID पहचान ली गई: {courseid}\n\n"
        "2️⃣ अब अपना Token (eyJ0eXAi...) यहाँ पेस्ट करके भेजें:",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda msg: usersessions.get(msg.chat.id, {}).get('step') == 'WAITING_TOKEN')
def handletoken(message):
    chatid = message.chat.id
    token = message.text.strip()
    
    if not token.startswith("eyJ"):
        bot.send_message(chatid, "❌ अमान्य टोकन! टोकन eyJ से शुरू होना चाहिए।")
        return

    usersessions[chatid]['token'] = token
    courseid = usersessions[chatid]['courseid']
    
    bot.send_message(chatid, "⏳ टोकन वेरिफाई हो रहा है और फोल्डर्स लोड हो रहे हैं...")
    
    headers = APIHEADERS.copy()
    headers.update({
        "x-access-token": token,
        "Authorization": f"Bearer {token}"
    })
    
    contenturl = f"https://api.classplusapp.com/v2/course/content/get?courseId={courseid}&folderId=0"
    
    try:
        res = requests.get(contenturl, headers=headers, timeout=30)
        items = extractitems(res.json())
        
        folders = [i for i in items if isinstance(i, dict) and (i.get('type') == 'folder' or i.get('contentType') == 1 or 'folderId' in i)]
        if not folders:
            folders = [i for i in items if isinstance(i, dict)]
            
        if not folders:
            bot.send_message(chatid, "⚠️ इस कोर्स में कोई फोल्डर या फाइल नहीं मिली।")
            return
            
        usersessions[chatid]['folders'] = folders
        usersessions[chatid]['step'] = 'WAITING_FOLDER'
        
        msgtext = "📁 उपलब्ध फोल्डर्स की सूची:\n\n"
        for idx, f in enumerate(folders, start=1):
            name = f.get('name') or f.get('title') or f.get('folderName') or f'Folder {idx}'
            msgtext += f"{idx}. 📁 {name}\n"
            
        msgtext += "\n👉 जिस फोल्डर की PDF देखनी है उसका नंबर भेजें (उदा. 1):"
        bot.send_message(chatid, msgtext, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chatid, f"❌ एरर: {str(e)}\nकृपया /start करके दोबारा प्रयास करें।")

@bot.message_handler(func=lambda msg: usersessions.get(msg.chat.id, {}).get('step') == 'WAITING_FOLDER')
def handlefolder(message):
    chatid = message.chat.id
    choice = message.text.strip()
    
    if not choice.isdigit():
        bot.send_message(chatid, "❌ केवल नंबर भेजें (उदा. 1)।")
        return
        
    idx = int(choice) - 1
    folders = usersessions[chatid].get('folders', [])
    
    if idx < 0 or idx >= len(folders):
        bot.send_message(chatid, "❌ गलत नंबर! सूची में से चुनें।")
        return
        
    selectedfolder = folders[idx]
    folderid = selectedfolder.get('id') or selectedfolder.get('folderId') or 0
    
    bot.send_message(chatid, "⏳ फोल्डर की फाइल्स निकाली जा रही हैं...")
    
    token = usersessions[chatid]['token']
    courseid = usersessions[chatid]['courseid']
    
    headers = APIHEADERS.copy()
    headers.update({
        "x-access-token": token,
        "Authorization": f"Bearer {token}"
    })
    
    filesurl = f"https://api.classplusapp.com/v2/course/content/get?courseId={courseid}&folderId={folderid}"
    
    try:
        res = requests.get(filesurl, headers=headers, timeout=30)
        items = extractitems(res.json())
        
        validfiles = []
        for i in items:
            if isinstance(i, dict):
                urlval = i.get('url') or i.get('fileUrl') or i.get('documentUrl') or i.get('downloadUrl') or ''
                if i.get('type') == 'pdf' or i.get('contentType') == 2 or str(urlval).lower().endswith('.pdf') or 'pdf' in str(urlval).lower():
                    validfiles.append(i)
                    
        if not validfiles:
            validfiles = [i for i in items if isinstance(i, dict) and (i.get('url') or i.get('fileUrl') or i.get('documentUrl'))]
            
        if not validfiles:
            bot.send_message(chatid, "⚠️ इस फोल्डर में कोई PDF फाइल नहीं मिली। दूसरा नंबर चुनें।")
            return
            
        usersessions[chatid]['files'] = validfiles
        usersessions[chatid]['step'] = 'WAITING_FILE'
        
        msgtext = "📄 उपलब्ध PDF फाइल्स:\n\n"
        for fidx, f in enumerate(validfiles, start=1):
            name = f.get('name') or f.get('title') or f.get('fileName') or f'PDF {fidx}'
            msgtext += f"{fidx}. 📄 {name}\n"
            
        msgtext += "\n👉 चैनल पर अपलोड करने के लिए PDF का नंबर भेजें (उदा. 1):"
        bot.send_message(chatid, msgtext, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chatid, f"❌ एरर: {str(e)}")

@bot.message_handler(func=lambda msg: usersessions.get(msg.chat.id, {}).get('step') == 'WAITING_FILE')
def handleupload(message):
    chatid = message.chat.id
    choice = message.text.strip()
    
    if not choice.isdigit():
        bot.send_message(chatid, "❌ केवल नंबर भेजें।")
        return
        
    idx = int(choice) - 1
    files = usersessions[chatid].get('files', [])
    
    if idx < 0 or idx >= len(files):
        bot.send_message(chatid, "❌ गलत नंबर!")
        return
        
    selectedfile = files[idx]
    filename = selectedfile.get('name') or selectedfile.get('title') or selectedfile.get('fileName') or "Notes.pdf"
    if not filename.lower().endswith('.pdf'):
        filename += ".pdf"
        
    pdfurl = selectedfile.get('url') or selectedfile.get('fileUrl') or selectedfile.get('documentUrl') or selectedfile.get('downloadUrl')
    
    bot.send_message(chatid, f"⏳ {filename} डाउनलोड होकर चैनल पर भेजी जा रही है...", parse_mode='Markdown')
    token = usersessions[chatid]['token']
    headers = APIHEADERS.copy()
    headers.update({
        "x-access-token": token,
        "Authorization": f"Bearer {token}"
    })
    
    try:
        r = requests.get(pdfurl, headers=headers, stream=True, timeout=600)
        
        if r.status_code == 200:
            pdfbytes = io.BytesIO(r.content)
            pdfbytes.name = filename
            
            bot.send_document(
                chat_id=TARGETCHANNEL,
                document=pdfbytes,
                caption=f"📚 {filename}\n\nUploaded via PSCLive Bot",
                timeout=600
            )
            
            bot.send_message(chatid, f"✅ सफलता! {filename} सफलतापूर्वक {TARGETCHANNEL} में भेज दी गई है।\n\n👉 अगली PDF का नंबर भेजें या /start करें।", parse_mode='Markdown')
        else:
            bot.send_message(chatid, f"❌ डाउनलोड विफल: Status {r.status_code}")
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ अपलोड एरर: {str(e)}")

def runpolling():
    bot.infinity_polling(skip_pending=True)

threading.Thread(target=runpolling, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    
