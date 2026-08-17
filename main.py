import telebot
import requests
import io
import os
import re
import json
import threading
from flask import Flask

# --- कॉन्फिगरेशन ---
BOTTOKEN = '8984791001:AAEWdpO_Qfgw3d10S69QsMSWkk5SUZwktR8'
TARGETCHANNEL = '@mycoures123'

bot = telebot.TeleBot(BOTTOKEN)
app = Flask("bot")

@app.route('/')
def index():
    return "PSCLive Diagnostic Bot Online"

usersessions = {}

APIHEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "region": "IN"
}

def clean_name(item, idx):
    for key in ['name', 'title', 'topicName', 'folderName', 'fileName', 'resourceName']:
        if key in item and item[key]:
            return str(item[key])
    return f"Item_{idx}"

def extract_items(resjson):
    if isinstance(resjson, list):
        return resjson
    if isinstance(resjson, dict):
        d = resjson.get('data', {})
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            for k in ['courseContent', 'contents', 'topics', 'list', 'data', 'files', 'materials']:
                if k in d and isinstance(d[k], list) and len(d[k]) > 0:
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
        "👋 PSCLive डायग्नोस्टिक डाउनलोडर\n\n"
        "1️⃣ कोर्स का URL या Course ID भेजें:\n"
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
        f"✅ कोर्स ID: {courseid}\n\n"
        "2️⃣ अब अपना Token (eyJ0eXAi...) भेजें:",
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
    
    bot.send_message(chatid, "⏳ टोकन वेरिफाई हो रहा है...")
    
    headers = APIHEADERS.copy()
    headers.update({
        "x-access-token": token,
        "Authorization": f"Bearer {token}"
    })
    
    contenturl = f"https://api.classplusapp.com/v2/course/content/get?courseId={courseid}&folderId=0"
    
    try:
        res = requests.get(contenturl, headers=headers, timeout=30)
        raw_json = res.json()
        
        # डीबग मैसेज
        debug_info = f"🔍 सर्वर रिस्पॉन्स (HTTP {res.status_code}):\n{str(raw_json)[:350]}..."
        bot.send_message(chatid, debug_info, parse_mode='Markdown')
        
        items = extract_items(raw_json)
        
        if len(items) == 1 and isinstance(items[0], dict):
            pid = items[0].get('id') or items[0].get('_id') or items[0].get('folderId') or items[0].get('topicId') or 0
            sub_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={courseid}&folderId={pid}"
            sub_res = requests.get(sub_url, headers=headers, timeout=30)
            sub_items = extract_items(sub_res.json())
            if sub_items:
                items = sub_items

        valid_items = [i for i in items if isinstance(i, dict)]
        if not valid_items:
            bot.send_message(chatid, "⚠️ कोई फ़ोल्डर नहीं मिला। ऊपर दिया गया डीबग डेटा चेक करें।")
            return
            
        usersessions[chatid]['folders'] = valid_items
        usersessions[chatid]['step'] = 'WAITING_FOLDER'
        
        msgtext = "📁 उपलब्ध सूची:\n\n"
        for idx, f in enumerate(valid_items, start=1):
            name = clean_name(f, idx)
            msgtext += f"{idx}. 📁 {name}\n"
            
        msgtext += "\n👉 जिसका डेटा खोलना है उसका नंबर भेजें:"
        bot.send_message(chatid, msgtext, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chatid, f"❌ एरर: {str(e)}")

@bot.message_handler(func=lambda msg: usersessions.get(msg.chat.id, {}).get('step') == 'WAITING_FOLDER')
def handlefolder(message):
    chatid = message.chat.id
    choice = message.text.strip()
    
    if not choice.isdigit():
        bot.send_message(chatid, "❌ केवल नंबर भेजें।")
        return
        
    idx = int(choice) - 1
    folders = usersessions[chatid].get('folders', [])
    
    if idx < 0 or idx >= len(folders):
        bot.send_message(chatid, "❌ गलत नंबर!")
        return
        
    selectedfolder = folders[idx]
    folderid = selectedfolder.get('id') or selectedfolder.get('_id') or selectedfolder.get('folderId') or selectedfolder.get('topicId') or selectedfolder.get('contentId') or 0
    
    bot.send_message(chatid, f"⏳ फ़ोल्डर ID {folderid} से फाइल्स निकाली जा रही हैं...")
    
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
        raw_json = res.json()
        
        items = extract_items(raw_json)
        validfiles = [i for i in items if isinstance(i, dict)]
        
        # अगर कोई फाइल नहीं मिली तो पूरा JSON स्क्रीन पर दिखाएगा
        if not validfiles:
            bot.send_message(chatid, f"⚠️ फ़ाइलें नहीं मिलीं। सर्वर डेटा:\n{str(raw_json)[:400]}", parse_mode='Markdown')
            return
            
        usersessions[chatid]['files'] = validfiles
        usersessions[chatid]['step'] = 'WAITING_FILE'
        
        msgtext = "📄 उपलब्ध फ़ाइल्स:\n\n"
        for fidx, f in enumerate(validfiles, start=1):
            name = clean_name(f, fidx)
            msgtext += f"{fidx}. 📄 {name}\n"
            
        msgtext += "\n👉 चैनल पर भेजने के लिए फ़ाइल का नंबर भेजें:"
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
    filename = clean_name(selectedfile, choice)
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
    
    pdfurl = (
        selectedfile.get('url') or 
        selectedfile.get('fileUrl') or 
        selectedfile.get('documentUrl') or 
        selectedfile.get('downloadUrl')
    )
    
    debug_log = f"📌 फाइल डेटा (Keys): {list(selectedfile.keys())}\n"
    
    if not pdfurl and contentid:
        url_apis = [
            f"https://api.classplusapp.com/v2/course/content/url?courseId={courseid}&contentId={contentid}",
            f"https://api.classplusapp.com/v2/course/content/loadUrl?courseId={courseid}&contentId={contentid}"
        ]
        for u_api in url_apis:
            try:
                u_res = requests.get(u_api, headers=headers, timeout=15)
                u_data = u_res.json()
                debug_log += f"🔗 API Call: {str(u_data)[:150]}\n"
                d_obj = u_data.get('data', {})
                if isinstance(d_obj, dict):
                    pdfurl = d_obj.get('url') or d_obj.get('fileUrl') or d_obj.get('signedUrl')
                elif isinstance(d_obj, str) and d_obj.startswith('http'):
                    pdfurl = d_obj
                if pdfurl:
                    break
            except Exception as ex:
                debug_log += f"⚠️ Call Failed: {str(ex)}\n"

    # डायग्नोस्टिक लॉग भेजें
    bot.send_message(chatid, debug_log, parse_mode='Markdown')

    if not pdfurl:
        bot.send_message(chatid, "❌ डाउनलोड URL नहीं मिला। ऊपर दिया गया लॉग चेक करें।")
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
            bot.send_message(chatid, f"✅ सफलता! {filename} चैनल पर भेज दी गई है।", parse_mode='Markdown')
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
    
