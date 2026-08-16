import telebot
import requests
import io
import os
import re
import threading
from flask import Flask

# --- कॉन्फिगरेशन ---
BOT_TOKEN = '8984791001:AAEWdpO_Qfgw3d10S69QsMSWkk5SUZwktR8'
# चैनल का सही यूज़रनेम
TARGET_CHANNEL = '@mycoures123'

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Render के लिए वेब सर्वर रूट
@app.route('/')
def index():
    return "PSCLive Extractor Bot is Running Active & Healthy!"

user_sessions = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://app.psclive.com",
    "Referer": "https://app.psclive.com/"
}

@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {'step': 'WAITING_URL'}
    bot.send_message(
        chat_id,
        "👋 नमस्ते! PSCLive PDF एक्सट्रैक्टर बॉट में आपका स्वागत है।\n\n"
        "कृपया सबसे पहले उस कोर्स का URL लिंक भेजें:\n"
        "👉 उदाहरण: https://app.psclive.com/new-courses/221/content",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_URL')
def handle_url(message):
    chat_id = message.chat.id
    url = message.text.strip()
    
    course_match = re.search(r'courses/(\d+)', url)
    if not course_match:
        bot.send_message(chat_id, "❌ गलत URL! कृपया सही कोर्स लिंक भेजें जिसमें कोर्स ID मौजूद हो।")
        return
        
    course_id = course_match.group(1)
    user_sessions[chat_id]['course_id'] = course_id
    user_sessions[chat_id]['step'] = 'WAITING_CREDS'
    
    bot.send_message(
        chat_id,
        f"✅ कोर्स ID पहचान ली गई: {course_id}\n\n"
        "अब अपना Login ID (Mobile/Email) और Password स्पेस देकर भेजें:\n"
        "👉 उदाहरण: 9876543210 MyPassword123",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_CREDS')
def handle_login(message):
    chat_id = message.chat.id
    creds = message.text.strip().split(maxsplit=1)
    
    if len(creds) < 2:
        bot.send_message(chat_id, "❌ कृपया यूजर ID और पासवर्ड दोनों स्पेस देकर भेजें।")
        return
        
    username, password = creds[0], creds[1]
    bot.send_message(chat_id, "⏳ लॉगिन किया जा रहा है और फोल्डर्स लोड हो रहे हैं...")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    login_url = "https://api.classplusapp.com/v2/users/login"
    login_payload = {
        "email": username if "@" in username else "",
        "mobile": username if "@" not in username else "",
        "password": password,
        "orgId": ""
    }
    
    try:
        res = session.post(login_url, json=login_payload, timeout=60)
        data = res.json()
        
        token = data.get('data', {}).get('token') or data.get('token')
            
        if not token:
            bot.send_message(chat_id, "❌ लॉगिन विफल! यूजर ID या पासवर्ड गलत है। कृपया पुनः /start करें।")
            return
            
        user_sessions[chat_id]['token'] = token
        session.headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
        
        course_id = user_sessions[chat_id]['course_id']
        content_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={course_id}&folderId=0"
        
        c_res = session.get(content_url, timeout=60)
        c_data = c_res.json()
        
        items = c_data.get('data', {}).get('courseContent', [])
        folders = [item for item in items if item.get('type') == 'folder' or item.get('contentType') == 1]
        
        if not folders:
            folders = items
            if not folders:
                        bot.send_message(chat_id, "⚠️ इस कोर्स में कोई फोल्डर या फाइल नहीं मिली।")
                        return
            
        user_sessions[chat_id]['folders'] = folders
        user_sessions[chat_id]['step'] = 'WAITING_FOLDER_CHOICE'
        
        msg_text = "📁 उपलब्ध फोल्डर्स की सूची:\n\n"
        for idx, f in enumerate(folders, start=1):
            name = f.get('name') or f.get('title') or f'Folder {idx}'
            msg_text += f"{idx}. 📁 {name}\n"
            
        msg_text += "\n👉 जिस फोल्डर की PDF देखनी है, उसका नंबर भेजें (उदा. 1):"
        bot.send_message(chat_id, msg_text, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ एरर: {str(e)}\nकृपया /start करके दोबारा प्रयास करें।")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_FOLDER_CHOICE')
def handle_folder_choice(message):
    chat_id = message.chat.id
    choice = message.text.strip()
    
    if not choice.isdigit():
        bot.send_message(chat_id, "❌ कृपया केवल नंबर भेजें (उदा. 1)।")
        return
        
    idx = int(choice) - 1
    folders = user_sessions[chat_id].get('folders', [])
    
    if idx < 0 or idx >= len(folders):
        bot.send_message(chat_id, "❌ गलत नंबर! लिस्ट में दिए गए नंबरों में से चुनें।")
        return
        
    selected_folder = folders[idx]
    folder_id = selected_folder.get('id') or selected_folder.get('folderId')
    
    bot.send_message(chat_id, "⏳ फोल्डर की फाइल्स लोड हो रही हैं...")
    
    token = user_sessions[chat_id]['token']
    course_id = user_sessions[chat_id]['course_id']
    
    headers = HEADERS.copy()
    headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
    
    files_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={course_id}&folderId={folder_id}"
    
    try:
        res = requests.get(files_url, headers=headers, timeout=60)
        f_data = res.json()
        
        items = f_data.get('data', {}).get('courseContent', [])
        pdf_files = [item for item in items if item.get('type') == 'pdf' or item.get('contentType') == 2 or str(item.get('url', '')).endswith('.pdf')]
        
        if not pdf_files:
            bot.send_message(chat_id, "⚠️ इस फोल्डर में कोई PDF नहीं मिली। दूसरा फोल्डर नंबर चुनें।")
            return
            
        user_sessions[chat_id]['files'] = pdf_files
        user_sessions[chat_id]['step'] = 'WAITING_FILE_CHOICE'
        
        msg_text = "📄 उपलब्ध PDF फाइल्स की सूची:\n\n"
        for f_idx, f in enumerate(pdf_files, start=1):
            name = f.get('name') or f.get('title') or f'PDF {f_idx}'
            msg_text += f"{f_idx}. 📄 {name}\n"
            
        msg_text += "\n👉 चैनल पर भेजने के लिए PDF का नंबर भेजें (उदा. 1):"
        bot.send_message(chat_id, msg_text, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ फाइल्स निकालने में एरर: {str(e)}")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_FILE_CHOICE')
def handle_upload(message):
    chat_id = message.chat.id
    choice = message.text.strip()
    
    if not choice.isdigit():
        bot.send_message(chat_id, "❌ कृपया केवल नंबर भेजें (उदा. 1)।")
        return
        
    idx = int(choice) - 1
    files = user_sessions[chat_id].get('files', [])
    
    if idx < 0 or idx >= len(files):
        bot.send_message(chat_id, "❌ गलत नंबर! लिस्ट में दिए गए नंबरों में से चुनें।")
        return
        
    selected_file = files[idx]
    file_name = selected_file.get('name') or selected_file.get('title') or "Notes.pdf"
    if not file_name.endswith('.pdf'):
        file_name += ".pdf"
        
    pdf_url = selected_file.get('url') or selected_file.get('fileUrl')
    bot.send_message(chat_id, f"⏳ {file_name} डाउनलोड हो रही है (लंबी PDF में कुछ समय लग सकता है)...", parse_mode='Markdown')
    
    token = user_sessions[chat_id]['token']
    headers = HEADERS.copy()
    headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
    
    try:
        # बड़ी फाइलों के लिए 600 सेकंड (10 मिनट) का टाइमआउट
        r = requests.get(pdf_url, headers=headers, stream=True, timeout=600)
        
        if r.status_code == 200:
            pdf_bytes = io.BytesIO(r.content)
            pdf_bytes.name = file_name
            
            # चैनल पर अपलोड (बड़ी फाइल्स के लिए timeout बढ़ा दिया गया है)
            bot.send_document(
                chat_id=TARGET_CHANNEL,
                document=pdf_bytes,
                caption=f"📚 {file_name}\n\nUploaded via PSCLive Bot",
                timeout=600
            )
            
            bot.send_message(chat_id, f"✅ सफलता! {file_name} सफलतापूर्वक {TARGET_CHANNEL} में भेज दी गई है।\n\n👉 अगली PDF का नंबर भेजें या नया कोर्स देखने के लिए /start करें।", parse_mode='Markdown')
        else:
            bot.send_message(chat_id, f"❌ PDF डाउनलोड विफल (Status Code: {r.status_code})।")
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ अपलोड एरर: {str(e)}")

def run_polling():
    bot.infinity_polling()

# बैकग्राउंड में बॉट शुरू करना
bot_thread = threading.Thread(target=run_polling)
bot_thread.daemon = True
bot_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    
