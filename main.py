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

def is_actual_folder(item):
    # Appx में फोल्डर की सटीक पहचान
    material_type = str(item.get('material_type', '')).lower()
    content_type = str(item.get('type', '')).lower()
    is_f = item.get('is_folder')
    
    if is_f in [1, '1', True]:
        return True
    if material_type in ['folder', 'dir', '1']:
        return True
    if content_type in ['folder', 'dir', '1']:
        return True
    # अगर फाइल लिंक/पाथ पहले से मौजूद है तो वह फोल्डर नहीं है
    if item.get('download_url') or item.get('pdf_url') or item.get('video_url') or item.get('file_url'):
        return False
    return False

def get_clean_title(item, default="Content"):
    for k in ['title', 'topic_name', 'name', 'file_name', 'description']:
        val = item.get(k)
        if val and str(val).strip():
            return str(val).strip()
    return default

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
    bot.send_message(chatid, f"✅ कोर्स ID: {courseid}\n\n2️⃣ अब अपना पूरा Token भेजें:")

@bot.message_handler(func=lambda msg: usersessions.get(msg.chat.id, {}).get('step') == 'WAITING_TOKEN')
def handletoken(message):
    chatid = message.chat.id
    token = message.text.strip()
    
    if not token.startswith("eyJ"):
        bot.send_message(chatid, "❌ अमान्य टोकन! टोकन eyJ से शुरू होना चाहिए।")
        return

    usersessions[chatid]['token'] = token
    courseid = usersessions[chatid]['courseid']
    
    bot.send_message(chatid, "⏳ कोर्स सामग्री लोड की जा रही है...")
    
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
            bot.send_message(chatid, "⚠️ इस कोर्स में कोई सामग्री नहीं मिली।")
            return
            
        usersessions[chatid]['items'] = valid_items
        usersessions[chatid]['step'] = 'WAITING_SELECTION'
        
        msgtext = "📁 मुख्य फ़ोल्डर्स / सूची:\n\n"
        for idx, item in enumerate(valid_items, start=1):
            title = get_clean_title(item, f"Item {idx}")
            icon = "📁" if is_actual_folder(item) else "📄"
            msgtext += f"{idx}. {icon} {title}\n"
            
        msgtext += "\n👉 खोलने के लिए नंबर भेजें:"
        bot.send_message(chatid, msgtext)
        
    except Exception as e:
        bot.send_message(chatid, f"❌ एरर: {str(e)}")

@bot.message_handler(func=lambda msg: usersessions.get(msg.chat.id, {}).get('step') == 'WAITING_SELECTION')
def handleselection(message):
    chatid = message.chat.id
    choice = message.text.strip()
    
    if not choice.isdigit():
        bot.send_message(chatid, "❌ कृपया केवल लिस्ट का नंबर भेजें।")
        return
        
    idx = int(choice) - 1
    items = usersessions[chatid].get('items', [])
    
    if idx < 0 or idx >= len(items):
        bot.send_message(chatid, "❌ गलत नंबर! कृपया लिस्ट में से सही नंबर चुनें।")
        return
        
    selected = items[idx]
    token = usersessions[chatid]['token']
    courseid = usersessions[chatid]['courseid']
    headers = get_headers(token)
    
    selected_id = selected.get('id') or selected.get('folder_id') or selected.get('content_id') or 0

    # 1. अगर यूजर ने फ़ोल्डर चुना है
    if is_actual_folder(selected):
        bot.send_message(chatid, "⏳ फ़ोल्डर खोला जा रहा है...")
        sub_url = f"https://psclivepawansirapi.akamai.net.in/get/folder_contentsv3?course_id={courseid}&parent_id={selected_id}&start=0"
        try:
            res = requests.get(sub_url, headers=headers, timeout=25)
            sub_items = res.json().get('data', [])
            valid_sub = [i for i in sub_items if isinstance(i, dict)]
            
            if not valid_sub:
                bot.send_message(chatid, "⚠️ यह फ़ोल्डर खाली है।")
                return
                
            usersessions[chatid]['items'] = valid_sub
            
            msgtext = "📄 फ़ोल्डर के अंदर उपलब्ध फ़ाइलें:\n\n"
            for fidx, item in enumerate(valid_sub, start=1):
                title = get_clean_title(item, f"File {fidx}")
                icon = "📁" if is_actual_folder(item) else "📄"
                msgtext += f"{fidx}. {icon} {title}\n"
                
            msgtext += "\n👉 चैनल पर अपलोड करने के लिए फ़ाइल नंबर भेजें:"
            bot.send_message(chatid, msgtext)
        except Exception as e:
            bot.send_message(chatid, f"❌ फ़ोल्डर लोड करने में एरर: {str(e)}")
        return

    # 2. अगर यूजर ने फ़ाइल (PDF/Video) चुनी है -> डाउनलोड शुरू
    file_title = get_clean_title(selected, f"Material_{choice}")
    bot.send_message(chatid, f"⏳ {file_title} का डाउनलोड लिंक निकाला जा रहा है...")

    download_url = (
        selected.get('download_url') or 
        selected.get('pdf_url') or 
        selected.get('video_url') or 
        selected.get('file_url') or 
        selected.get('url') or 
        selected.get('document_url') or
        selected.get('path')
    )
    
    # अगर लिस्ट में सीधा लिंक न हो, तो कंटेंट डिटेल API से URL फेच करना
    if not download_url and selected_id:
        detail_apis = [
            f"https://psclivepawansirapi.akamai.net.in/get/content_details?course_id={courseid}&content_id={selected_id}",
            f"https://psclivepawansirapi.akamai.net.in/get/pdf_details?course_id={courseid}&content_id={selected_id}",
            f"https://psclivepawansirapi.akamai.net.in/get/video_details?course_id={courseid}&content_id={selected_id}"
        ]
        for d_url in detail_apis:
            try:
                d_res = requests.get(d_url, headers=headers, timeout=15).json()
                d_data = d_res.get('data', {})
                if isinstance(d_data, dict):
                    download_url = d_data.get('download_url') or d_data.get('pdf_url') or d_data.get('video_url') or d_data.get('file_url') or d_data.get('url')
                elif isinstance(d_data, str) and d_data.startswith('http'):
                    download_url = d_data
                if download_url:
                    break
            except Exception:
                continue

    if not download_url:
        bot.send_message(chatid, "❌ इस फ़ाइल का डाउनलोड लिंक सर्वर से प्राप्त नहीं हो सका।")
        return

    # फ़ाइल एक्सटेंशन तय करना (PDF या MP4)
    is_video = any(ext in download_url.lower() for ext in ['.mp4', '.m3u8', 'video']) or selected.get('type') == 'video'
    ext = ".mp4" if is_video else ".pdf"
    
    if not file_title.lower().endswith(ext):
        file_title += ext

    bot.send_message(chatid, f"⬇️ डाउनलोड करके @mycoures123 पर अपलोड किया जा रहा है: {file_title}")
    
    try:
        r = requests.get(download_url, headers=headers, stream=True, timeout=600)
        if r.status_code == 200:
            file_bytes = io.BytesIO(r.content)
            file_bytes.name = file_title
            
            if is_video:
                bot.send_video(
                    chat_id=TARGETCHANNEL,
                    video=file_bytes,
                    caption=f"🎥 {file_title}\n\nUploaded via PSCLive Bot",
                    timeout=600
                )
            else:
                bot.send_document(
                    chat_id=TARGETCHANNEL,
                    document=file_bytes,
                    caption=f"📚 {file_title}\n\nUploaded via PSCLive Bot",
                    timeout=600
                )
                
            bot.send_message(chatid, f"✅ सफलता! {file_title} चैनल पर भेज दी गई है।\n\n👉 अगली फ़ाइल का नंबर भेजें या /start करें।")
        else:
            bot.send_message(chatid, f"❌ डाउनलोड विफल: Status Code {r.status_code}")
    except Exception as e:
        bot.send_message(chatid, f"❌ अपलोड एरर: {str(e)}")

def runpolling():
    bot.infinity_polling(skip_pending=True)

threading.Thread(target=runpolling, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    
