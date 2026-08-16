import telebot
import requests
import io
import os
import re
import threading
import time
from flask import Flask

BOT_TOKEN = '8984791001:AAEWdpO_Qfgw3d10S69QsMSWkk5SUZwktR8'
CHANNEL_ID = -1003946396225

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(name)

@app.route('/')
def home():
    return "✅ PSCLive Bot is running on Render!"

@app.route('/health')
def health():
    return "OK", 200

user_sessions = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://app.psclive.com",
    "Referer": "https://app.psclive.com/"
}

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {'step': 'WAITING_URL'}
    bot.send_message(
        chat_id,
        "👋 नमस्ते! PSCLive PDF एक्सट्रैक्टर बॉट में आपका स्वागत है।\n\n"
        "कृपया सबसे पहले उस कोर्स/कंटेंट का URL लिंक भेजें:\n"
        "👉 उदाहरण: https://app.psclive.com/new-courses/221/content",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_URL')
def get_url(message):
    chat_id = message.chat.id
    url = message.text.strip()
    
    course_match = re.search(r'courses/(\d+)', url)
    if not course_match:
        bot.send_message(chat_id, "❌ गलत URL! कृपया सही कोर्स लिंक भेजें।")
        return
        
    course_id = course_match.group(1)
    user_sessions[chat_id]['course_id'] = course_id
    user_sessions[chat_id]['step'] = 'WAITING_CREDS'
    
    bot.send_message(
        chat_id,
        f"✅ कोर्स ID: {course_id}\n\nअब Login ID और Password स्पेस देकर भेजें:\n👉 उदाहरण: 9876543210 MyPassword123",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_CREDS')
def login_and_fetch_folders(message):
    chat_id = message.chat.id
    creds = message.text.strip().split(maxsplit=1)
    
    if len(creds) < 2:
        bot.send_message(chat_id, "❌ कृपया यूजर ID और पासवर्ड दोनों भेजें।")
        return
        
    username, password = creds[0], creds[1]
    bot.send_message(chat_id, "⏳ लॉगिन हो रहा है...")
    
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
        res = session.post(login_url, json=login_payload, timeout=30)
        data = res.json()
        
        token = data.get('data', {}).get('token')
        if not token:
            token = data.get('token')
            
        if not token:
            bot.send_message(chat_id, "❌ लॉगिन विफल! कृपया /start करें।")
            return
            
        user_sessions[chat_id]['token'] = token
        session.headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
        
        course_id = user_sessions[chat_id]['course_id']
        content_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={course_id}&folderId=0"
        
        c_res = session.get(content_url, timeout=30)
        c_data = c_res.json()
        
        items = c_data.get('data', {}).get('courseContent', [])
        folders = [item for item in items if item.get('type') == 'folder' or item.get('contentType') == 1]
        
        if not folders:
            folders = items
            
        if not folders:
            bot.send_message(chat_id, "⚠️ कोई फोल्डर नहीं मिला।")
            return
            
        user_sessions[chat_id]['folders'] = folders
        user_sessions[chat_id]['step'] = 'WAITING_FOLDER_CHOICE'
        msg_text = "📁 उपलब्ध फोल्डर्स:\n\n"
        for idx, f in enumerate(folders, start=1):
            name = f.get('name') or f.get('title') or f'Item {idx}'
            msg_text += f"{idx}. {name}\n"
            
        msg_text += "\n👉 फोल्डर का नंबर भेजें:"
        bot.send_message(chat_id, msg_text, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ एरर: {str(e)}")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_FOLDER_CHOICE')
def select_folder(message):
    chat_id = message.chat.id
    choice = message.text.strip()
    
    if not choice.isdigit():
        bot.send_message(chat_id, "❌ कृपया नंबर भेजें।")
        return
        
    idx = int(choice) - 1
    folders = user_sessions[chat_id].get('folders', [])
    
    if idx < 0 or idx >= len(folders):
        bot.send_message(chat_id, "❌ गलत नंबर!")
        return
        
    selected_folder = folders[idx]
    folder_id = selected_folder.get('id') or selected_folder.get('folderId')
    
    if selected_folder.get('type') == 'pdf' or selected_folder.get('contentType') == 2:
        user_sessions[chat_id]['files'] = [selected_folder]
        user_sessions[chat_id]['step'] = 'WAITING_FILE_CHOICE'
        bot.send_message(chat_id, f"📄 PDF मिली: {selected_folder.get('name')}\nअपलोड करें? (1 भेजें)")
        return
    
    bot.send_message(chat_id, "⏳ फाइल्स निकाली जा रही हैं...")
    
    token = user_sessions[chat_id]['token']
    course_id = user_sessions[chat_id]['course_id']
    
    headers = HEADERS.copy()
    headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
    
    files_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={course_id}&folderId={folder_id}"
    
    try:
        res = requests.get(files_url, headers=headers, timeout=30)
        f_data = res.json()
        
        items = f_data.get('data', {}).get('courseContent', [])
        pdf_files = [item for item in items if item.get('type') == 'pdf' or item.get('contentType') == 2]
        
        if not pdf_files:
            bot.send_message(chat_id, "⚠️ कोई PDF नहीं मिली।")
            return
            
        user_sessions[chat_id]['files'] = pdf_files
        user_sessions[chat_id]['step'] = 'WAITING_FILE_CHOICE'
        
        msg_text = "📄 PDF फाइल्स:\n\n"
        for f_idx, f in enumerate(pdf_files, start=1):
            name = f.get('name') or f.get('title') or f'PDF {f_idx}'
            msg_text += f"{f_idx}. {name}\n"
            
        msg_text += "\n👉 PDF का नंबर भेजें:"
        bot.send_message(chat_id, msg_text, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ एरर: {str(e)}")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_FILE_CHOICE')
def upload_pdf_to_channel(message):
    chat_id = message.chat.id
    choice = message.text.strip()
    
    if not choice.isdigit():
        bot.send_message(chat_id, "❌ कृपया नंबर भेजें।")
        return
        
    idx = int(choice) - 1
    files = user_sessions[chat_id].get('files', [])
    
    if idx < 0 or idx >= len(files):
        bot.send_message(chat_id, "❌ गलत नंबर!")
        return
        
    selected_file = files[idx]
    file_name = selected_file.get('name') or selected_file.get('title') or "Notes.pdf"
    if not file_name.endswith('.pdf'):
        file_name += ".pdf"
        
    pdf_url = selected_file.get('url') or selected_file.get('fileUrl') or selected_file.get('attachmentUrl')
    
    if not pdf_url:
        bot.send_message(chat_id, "❌ PDF URL नहीं मिला।")
        return
    
    bot.send_message(chat_id, f"⏳ {file_name} अपलोड हो रही है...")
    
    token = user_sessions[chat_id]['token']
    headers = HEADERS.copy()
    headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
    
    try:
        r = requests.get(pdf_url, headers=headers, stream=True, timeout=600)
        
        if r.status_code == 200:
            pdf_bytes = io.BytesIO(r.content)
            pdf_bytes.name = file_name
            
            bot.send_document(
                chat_id=CHANNEL_ID,
                document=pdf_bytes,
                caption=f"📚 {file_name}\n\nUploaded via PSCLive Bot",
                timeout=600
            )
            
            bot.send_message(
                chat_id,
                f"✅ {file_name} सफलतापूर्वक चैनल पर भेज दी गई!\n\nचैनल: https://t.me/mycoures123",
                parse_mode='Markdown'
            )
            
            user_sessions[chat_id]['step'] = 'WAITING_FILE_CHOICE'
            
        else:
            bot.send_message(chat_id, f"❌ डाउनलोड विफल (Status: {r.status_code})")
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ एरर: {str(e)}")

def run_bot():
    try:
        print("🤖 Bot starting...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Bot Error: {e}")
        time.sleep(5)
        run_bot()

if name == 'main':
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    time.sleep(2)
    print("🚀 Flask starting...")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
    
            
