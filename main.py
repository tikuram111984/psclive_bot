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
    return "PSCLive Bot Running"

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
            for k in ['courseContent', 'contents', 'topics', 'list', 'data', 'files', 'materials']:
                if k in d and isinstance(d[k], list):
                    return d[k]
        for k in ['courseContent', 'contents', 'topics', 'data', 'list']:
            if k in resjson and isinstance(resjson[k], list):
                return resjson[k]
    return []

@bot.message_handler(commands=['start'])
def handlestart(message):
    chatid = message.chat.id
    usersessions[chatid] = {'step': 'WAITING_URL'}
    bot.send_message(
        chatid,
        "👋 PSCLive डाउनलोडर बॉट\n\n"
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
        bot.send_message(chatid, "❌ गलत URL! कृपया सही कोर्स लिंक भेजें।")
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
        bot.send_message(chatid, "❌ टोकन eyJ से शुरू होना चाहिए।")
        return

    usersessions[chatid]['token'] = token
    courseid = usersessions[chatid]['courseid']
    
    bot.send_message(chatid, "⏳ टोकन वेरिफाई हो रहा है और सभी फ़ोल्डर्स लोड हो रहे हैं...")
    
    headers = APIHEADERS.copy()
    headers.update({
        "x-access-token": token,
        "Authorization": f"Bearer {token}"
    })
    
    contenturl = f"https://api.classplusapp.com/v2/course/content/get?courseId={courseid}&folderId=0"
    
    try:
        res = requests.get(contenturl, headers=headers, timeout=30)
        items = extractitems(res.json())
        
        # अगर सिर्फ 1 मुख्य फ़ोल्डर आए, तो उसके अंदर के सारे सब-फ़ोल्डर्स निकालें
        if len(items) == 1 and isinstance(items[0], dict):
            parent_id = items[0].get('id') or items[0].get('_id') or items[0].get('folderId') or items[0].get('topicId') or 0
            sub_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={courseid}&folderId={parent_id}"
            sub_res = requests.get(sub_url, headers=headers, timeout=30)
            sub_items = extractitems(sub_res.json())
            if sub_items:
                items = sub_items

        valid_items = [i for i in items if isinstance(i, dict)]
        if not valid_items:
            bot.send_message(chatid, "⚠️ इस कोर्स में कोई सामग्री नहीं मिली।")
            return
            
        usersessions[chatid]['folders'] = valid_items
        usersessions[chatid]['step'] = 'WAITING_FOLDER'
        
        msgtext = "📁 उपलब्ध फ़ोल्डर्स की सूची:\n\n"
        for idx, f in enumerate(valid_items, start=1):
            name = f.get('topicName') or f.get('folderName') or f.get('title') or f.get('name') or f'Folder {idx}'
            msgtext += f"{idx}. 📁 {name}\n"
            
        msgtext += "\n👉 जिस फ़ोल्डर को खोलना है, उसका नंबर भेजें (उदा. 1):"
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
    folderid = selectedfolder.get('id') or selectedfolder.get('_id') or selectedfolder.get('folderId') or selectedfolder.get('topicId') or selectedfolder.get('contentId') or 0
    
    bot.send_message(chatid, "⏳ फ़ोल्डर की फ़ाइलें निकाली जा रही हैं...")
    
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
        
        validfiles = [i for i in items if isinstance(i, dict)]
                
        if not validfiles:
            bot.send_message(chatid, "⚠️ इस फ़ोल्डर में कोई फ़ाइल नहीं मिली।")
            return
            
        usersessions[chatid]['files'] = validfiles
        usersessions[chatid]['step'] = 'WAITING_FILE'
        
        msgtext = "📄 उपलब्ध फ़ाइल्स:\n\n"
        for fidx, f in enumerate(validfiles, start=1):
            name = f.get('topicName') or f.get('fileName') or f.get('title') or f.get('name') or f'File {fidx}'
            msgtext += f"{fidx}. 📄 {name}\n"
            
        msgtext += "\n👉 चैनल पर अपलोड करने के लिए फ़ाइल का नंबर भेजें (उदा. 1):"
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
    filename = selectedfile.get('topicName') or selectedfile.get('fileName') or selectedfile.get('name') or selectedfile.get('title') or f"File_{choice}.pdf"
    if not filename.lower().endswith('.pdf'):
        filename += ".pdf"
        
    contentid = selectedfile.get('id') or selectedfile.get('_id') or selectedfile.get('contentId') or selectedfile.get('topicId')
    courseid = usersessions[chatid]['courseid']
    token = usersessions[chatid]['token']
    
    headers = APIHEADERS.copy()
    headers.update({
        "x-access-token": token,
        "Authorization": f"Bearer {token}"
    })
    
    # 1. पहले ऑब्जेक्ट से डाउनलोड URL देखें
    pdfurl = selectedfile.get('url') or selectedfile.get('fileUrl') or selectedfile.get('documentUrl') or selectedfile.get('downloadUrl')
    
    # 2. अगर URL नहीं है, तो API से डायरेक्ट लिंक निकालें
    if not pdfurl and contentid:
        try:
            url_api = f"https://api.classplusapp.com/v2/course/content/url?courseId={courseid}&contentId={contentid}"
            u_res = requests.get(url_api, headers=headers, timeout=20)
            u_data = u_res.json()
            pdfurl = u_data.get('data', {}).get('url') or u_data.get('data', {}).get('fileUrl') or u_data.get('url')
        except Exception:
            pass

    if not pdfurl:
        bot.send_message(chatid, "❌ इस फ़ाइल का डाउनलोड लिंक नहीं मिला (यह वीडियो या टेस्ट हो सकता है)।")
        return
        
    bot.send_message(chatid, f"⏳ {filename} डाउनलोड होकर चैनल पर भेजी जा रही है...", parse_mode='Markdown')
    
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
            bot.send_message(chatid, f"✅ सफलता! {filename} चैनल {TARGETCHANNEL} पर भेज दी गई है।\n\n👉 अगली फ़ाइल का नंबर भेजें या /start करें।", parse_mode='Markdown')
        else:
            bot.send_message(chatid, f"❌ डाउनलोड विफल: Status {r.status_code}")
            
    except Exception as e:
        bot.send_message(chatid, f"❌ अपलोड एरर: {str(e)}")

def runpolling():
    bot.infinity_polling(skip_pending=True)

threading.Thread(target=runpolling, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    
