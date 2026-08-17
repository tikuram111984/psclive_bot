import telebot
import requests
import io
import os
import re
import threading
from flask import Flask

BOTTOKEN = '8984791001:AAEWdpO_Qfgw3d10S69QsMSWkk5SUZwktR8'
TARGETCHANNEL = '@mycoures123'

bot = telebot.TeleBot(BOTTOKEN)
app = Flask("bot")

@app.route('/')
def index():
    return "PSCLive Appx Bot Running"

usersessions = {}

def get_headers(token, userid="12913"):
    return {
        "accept": "*/*",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "auth-key": "appxapi",
        "authorization": token,
        "client-service": "Appx",
        "device-type": "",
        "is-safari": "0",
        "origin": "https://app.psclive.com",
        "referer": "https://app.psclive.com/",
        "source": "website",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "user-id": str(userid)
    }

@bot.message_handler(commands=['start'])
def handlestart(message):
    chatid = message.chat.id
    usersessions[chatid] = {'step': 'WAITING_URL'}
    bot.send_message(
        chatid,
        "👋 PSCLive डाउनलोडर बॉट\n\n1️⃣ कोर्स का URL या ID भेजें:\n👉 उदा. https://app.psclive.com/new-courses/221/content"
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
    bot.send_message(chatid, f"✅ कोर्स ID: {courseid}\n\n2️⃣ अब अपना Token भेजें:")

@bot.message_handler(func=lambda msg: usersessions.get(msg.chat.id, {}).get('step') == 'WAITING_TOKEN')
def handletoken(message):
    chatid = message.chat.id
    token = message.text.strip()
    
    if not token.startswith("eyJ"):
        bot.send_message(chatid, "❌ अमान्य टोकन! टोकन eyJ से शुरू होना चाहिए।")
        return

    usersessions[chatid]['token'] = token
    courseid = usersessions[chatid]['courseid']
    
    bot.send_message(chatid, "⏳ फ़ोल्डर्स लोड किए जा रहे हैं...")
    
    headers = get_headers(token)
    api_url = f"https://psclivepawansirapi.akamai.net.in/get/folder_contentsv3?course_id={courseid}&parent_id=-1&start=0"
    
    try:
        res = requests.get(api_url, headers=headers, timeout=25)
        raw_json = res.json()
        
        items = raw_json.get('data', [])
        if not items and isinstance(raw_json, list):
            items = raw_json
            
        valid_items = [i for i in items if isinstance(i, dict)]
        if not valid_items:
            bot.send_message(chatid, f"⚠️ कोर्स में कोई सामग्री नहीं मिली या ऑथेंटिकेशन फेल हो गया।\nरिस्पॉन्स: {str(raw_json)[:200]}")
            return
            
        usersessions[chatid]['items'] = valid_items
        usersessions[chatid]['step'] = 'WAITING_CHOICE'
        
        msgtext = "📁 उपलब्ध फ़ोल्डर्स / सामग्री:\n\n"
        for idx, item in enumerate(valid_items, start=1):
            title = item.get('title') or item.get('topic_name') or item.get('name') or f"Item {idx}"
            is_folder = item.get('is_folder') or (item.get('type') == 'folder')
            icon = "📁" if is_folder else "📄"
            msgtext += f"{idx}. {icon} {title}\n"
            
        msgtext += "\n👉 खोलने या डाउनलोड करने के लिए नंबर भेजें:"
        bot.send_message(chatid, msgtext)
        
    except Exception as e:
        bot.send_message(chatid, f"❌ एरर: {str(e)}")

@bot.message_handler(func=lambda msg: usersessions.get(msg.chat.id, {}).get('step') == 'WAITING_CHOICE')
def handlechoice(message):
    chatid = message.chat.id
    choice = message.text.strip()
    
    if not choice.isdigit():
        bot.send_message(chatid, "❌ केवल नंबर भेजें।")
        return
        
    idx = int(choice) - 1
    items = usersessions[chatid].get('items', [])
    
    if idx < 0 or idx >= len(items):
        bot.send_message(chatid, "❌ गलत नंबर!")
        return
        
    selected = items[idx]
    token = usersessions[chatid]['token']
    courseid = usersessions[chatid]['courseid']
    headers = get_headers(token)
    
    is_folder = selected.get('is_folder') or (selected.get('type') == 'folder') or ('parent_id' in selected and not selected.get('download_url'))
    selected_id = selected.get('id') or selected.get('folder_id')
    
    if is_folder:
        bot.send_message(chatid, f"⏳ फ़ोल्डर खोला जा रहा है...")
        sub_url = f"https://psclivepawansirapi.akamai.net.in/get/folder_contentsv3?course_id={courseid}&parent_id={selected_id}&start=0"
        try:
            res = requests.get(sub_url, headers=headers, timeout=25)
            sub_items = res.json().get('data', [])
            valid_sub = [i for i in sub_items if isinstance(i, dict)]
            
            if not valid_sub:
                bot.send_message(chatid, "⚠️ यह फ़ोल्डर खाली है।")
                return
                
            usersessions[chatid]['items'] = valid_sub
            
            msgtext = "📄 फ़ोल्डर की फ़ाइलें:\n\n"
            for fidx, item in enumerate(valid_sub, start=1):
                title = item.get('title') or item.get('topic_name') or item.get('name') or f"File {fidx}"
                msgtext += f"{fidx}. 📄 {title}\n"
                
            msgtext += "\n👉 चैनल पर भेजने के लिए फ़ाइल का नंबर भेजें:"
            bot.send_message(chatid, msgtext)
        except Exception as e:
            bot.send_message(chatid, f"❌ फ़ोल्डर एरर: {str(e)}")
        return

    # PDF / File Download Logic
    file_title = selected.get('title') or selected.get('topic_name') or selected.get('name') or "Document"
    if not file_title.lower().endswith('.pdf'):
        file_title += ".pdf"
        
    pdf_url = (
        selected.get('download_url') or 
        selected.get('pdf_url') or 
        selected.get('url') or 
        selected.get('file_url') or 
        selected.get('document_url')
    )
    
    # अगर डायरेक्ट लिंक न हो तो फाइल डीटेल API चेक करें
    if not pdf_url and selected_id:
        try:
            d_url = f"https://psclivepawansirapi.akamai.net.in/get/content_details?course_id={courseid}&content_id={selected_id}"
            d_res = requests.get(d_url, headers=headers, timeout=15).json()
            data_dict = d_res.get('data', {})
            if isinstance(data_dict, dict):
                pdf_url = data_dict.get('download_url') or data_dict.get('pdf_url') or data_dict.get('url')
        except Exception:
            pass

    if not pdf_url:
        bot.send_message(chatid, f"❌ इस फ़ाइल का डाउनलोड लिंक नहीं मिला।")
        return

    bot.send_message(chatid, f"⏳ {file_title} डाउनलोड करके चैनल पर भेजा जा रहा है...")
    
    try:
        r = requests.get(pdf_url, headers=headers, stream=True, timeout=600)
        if r.status_code == 200:
            pdfbytes = io.BytesIO(r.content)
            pdfbytes.name = file_title
            
            bot.send_document(
                chat_id=TARGETCHANNEL,
                document=pdfbytes,
                caption=f"📚 {file_title}\n\nUploaded via PSCLive Bot",
                timeout=600
            )
            bot.send_message(chatid, f"✅ सफलता! {file_title} चैनल पर भेज दी गई है।\n\n👉 अगली फ़ाइल का नंबर भेजें या /start करें।")
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
