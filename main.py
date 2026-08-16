import telebot
import requests
import io
import os
import re
import threading
import time
from flask import Flask

# --- कॉन्फिगरेशन ---
BOT_TOKEN = '8984791001:AAEWdpO_Qfgw3d10S69QsMSWkk5SUZwktR8'
CHANNEL_ID = -1003946396225  # ✅ आपका चैनल ID (नोट: -100 जरूरी है)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(name)

# Render के लिए डमी वेब सर्वर
@app.route('/')
def home():
    return "✅ PSCLive Bot is running smoothly on Render!"

@app.route('/health')
def health():
    return "OK", 200

# यूजर सेशन डेटा स्टोर करने के लिए
user_sessions = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
        bot.send_message(chat_id, "❌ गलत URL! कृपया सही कोर्स लिंक भेजें जिसमें कोर्स ID मौजूद हो।")
        return
        
    course_id = course_match.group(1)
    user_sessions[chat_id]['course_id'] = course_id
    user_sessions[chat_id]['step'] = 'WAITING_CREDS'
    
    bot.send_message(
        chat_id,
        f"✅ कोर्स ID पहचान ली गई: {course_id}\n\n"
        "अब अपना Login ID (Mobile/Email) और Password स्पेस देकर एक साथ भेजें:\n"
        "👉 उदाहरण: 9876543210 MyPassword123",
        parse_mode='Markdown'
    )

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_CREDS')
def login_and_fetch_folders(message):
    chat_id = message.chat.id
    creds = message.text.strip().split(maxsplit=1)
    
    if len(creds) < 2:
        bot.send_message(chat_id, "❌ कृपया यूजर ID और पासवर्ड दोनों स्पेस देकर भेजें।")
        return
        
    username, password = creds[0], creds[1]
    bot.send_message(chat_id, "⏳ लॉगिन किया जा रहा है और फोल्डर्स फेच हो रहे हैं...")
    
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
        
        print(f"🔍 Login Response: {data}")  # Debugging
        
        token = data.get('data', {}).get('token')
        if not token:
            token = data.get('token')
            
        if not token:
            bot.send_message(chat_id, "❌ लॉगिन विफल! यूजर ID या पासवर्ड गलत है। कृपया पुनः /start करें।")
            return
            
        user_sessions[chat_id]['token'] = token
        session.headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
        
        course_id = user_sessions[chat_id]['course_id']
        content_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={course_id}&folderId=0"
        
        c_res = session.get(content_url, timeout=30)
        c_data = c_res.json()
        
        print(f"📁 Content Response: {c_data}")  # Debugging
        items = c_data.get('data', {}).get('courseContent', [])
        
        # फोल्डर और PDF दोनों को एक साथ दिखाएं
        folders = [item for item in items if item.get('type') == 'folder' or item.get('contentType') == 1]
        
        if not folders:
            # अगर फोल्डर नहीं मिले तो सारी फाइल्स दिखाएं
            folders = items
            
        if not folders:
            bot.send_message(chat_id, "⚠️ इस कोर्स में कोई फोल्डर या फाइल्स नहीं मिलीं।")
            return
            
        user_sessions[chat_id]['folders'] = folders
        user_sessions[chat_id]['step'] = 'WAITING_FOLDER_CHOICE'
        
        msg_text = "📁 उपलब्ध फोल्डर्स/फाइल्स की सूची:\n\n"
        for idx, f in enumerate(folders, start=1):
            name = f.get('name') or f.get('title') or f'Item {idx}'
            file_type = f.get('type') or 'file'
            emoji = "📁" if file_type == 'folder' else "📄"
            msg_text += f"{idx}. {emoji} {name}\n"
            
        msg_text += "\n👉 जिस फोल्डर की PDF देखनी है, उसका नंबर टाइप करके भेजें (उदा. 1):"
        bot.send_message(chat_id, msg_text, parse_mode='Markdown')
        
    except Exception as e:
        print(f"❌ Login Error: {e}")
        bot.send_message(chat_id, f"❌ एरर: {str(e)}\nकृपया /start करके दोबारा प्रयास करें।")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_FOLDER_CHOICE')
def select_folder(message):
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
    
    # अगर यह सीधे PDF है तो सीधे अपलोड करें
    if selected_folder.get('type') == 'pdf' or selected_folder.get('contentType') == 2:
        user_sessions[chat_id]['files'] = [selected_folder]
        user_sessions[chat_id]['step'] = 'WAITING_FILE_CHOICE'
        bot.send_message(chat_id, f"📄 PDF मिली: {selected_folder.get('name')}\nक्या आप इसे अपलोड करना चाहते हैं? (हाँ के लिए 1 भेजें)")
        return
    
    bot.send_message(chat_id, "⏳ फोल्डर की फाइल्स निकाली जा रही हैं...")
    
    token = user_sessions[chat_id]['token']
    course_id = user_sessions[chat_id]['course_id']
    
    headers = HEADERS.copy()
    headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
    
    files_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={course_id}&folderId={folder_id}"
    
    try:
        res = requests.get(files_url, headers=headers, timeout=30)
        f_data = res.json()
        
        print(f"📄 Files Response: {f_data}")  # Debugging
        
        items = f_data.get('data', {}).get('courseContent', [])
        pdf_files = [item for item in items if item.get('type') == 'pdf' or item.get('contentType') == 2 or str(item.get('url', '')).endswith('.pdf')]
        
        if not pdf_files:
            bot.send_message(chat_id, "⚠️ इस फोल्डर में कोई PDF फाइल नहीं मिली। दूसरा फोल्डर नंबर चुनें।")
            return
            
        user_sessions[chat_id]['files'] = pdf_files
        user_sessions[chat_id]['step'] = 'WAITING_FILE_CHOICE'
        
        msg_text = "📄 उपलब्ध PDF फाइल्स की सूची:\n\n"
        for f_idx, f in enumerate(pdf_files, start=1):
            name = f.get('name') or f.get('title') or f'PDF {f_idx}'
            size = f.get('size', 0)
            size_mb = f"({round(size/1024/1024, 2)} MB)" if size else ""
            msg_text += f"{f_idx}. 📄 {name} {size_mb}\n"
            
        msg_text += "\n👉 चैनल पर अपलोड करने के लिए PDF का नंबर भेजें (उदा. 1):"
        bot.send_message(chat_id, msg_text, parse_mode='Markdown')
        
    except Exception as e:
        print(f"❌ Files Error: {e}")
        bot.send_message(chat_id, f"❌ फाइल्स निकालने में एरर: {str(e)}")

@bot.message_handler(func=lambda msg: user_sessions.get(msg.chat.id, {}).get('step') == 'WAITING_FILE_CHOICE')
def upload_pdf_to_channel(message):
    chat_id = message.chat.id
    choice = message.text.strip()
    
    # अगर सीधे PDF चुनी गई है तो auto-select
    if choice == '1' and len(user_sessions[chat_id].get('files', [])) == 1:
        idx = 0
    else:
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
        
    # PDF URL निकालें - कई तरह की keys check करें
    pdf_url = (selected_file.get('url') or 
               selected_file.get('fileUrl') or 
               selected_file.get('attachmentUrl') or
               selected_file.get('downloadUrl') or
               selected_file.get('link'))
    
    if not pdf_url:
        bot.send_message(chat_id, "❌ PDF का URL नहीं मिल पाया।")
        return
    
    bot.send_message(chat_id, f"⏳ {file_name} डाउनलोड होकर चैनल पर अपलोड हो रही है...\n⏱️ बड़ी PDF के लिए कुछ मिनट लग सकते हैं।", parse_mode='Markdown')
    
    token = user_sessions[chat_id]['token']
    headers = HEADERS.copy()
    headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
    
    try:
        # ✅ बड़ी PDF के लिए Timeout बढ़ाया (10 मिनट)
        r = requests.get(pdf_url, headers=headers, stream=True, timeout=600)
        
        if r.status_code == 200:
            # ✅ Content-Length चेक करें (अगर मिले तो)
            content_length = r.headers.get('content-length')
            if content_length:
                size_mb = round(int(content_length) / 1024 / 1024, 2)
                bot.send_message(chat_id, f"📊 PDF का साइज़: {size_mb} MB\n⏳ अपलोड हो रहा है...")
            
            pdf_bytes = io.BytesIO(r.content)
            pdf_bytes.name = file_name
            
            # ✅ Telegram पर भेजें (बड़ी फाइल के लिए)
            try:
                bot.send_document(
                    chat_id=CHANNEL_ID,
                    document=pdf_bytes,
                    caption=f"📚 {file_name}\n\n✅ Uploaded via PSCLive Bot\n📅 {time.strftime('%d-%m-%Y %H:%M')}",
                    timeout=600  # ✅ बड़ी फाइल के लिए Timeout
                )
                
                bot.send_message(
                    chat_id, 
                    f"✅ सफलता! {file_name} सफलतापूर्वक आपके चैनल पर भेज दी गई है।\n\n"
                    "🔗 चैनल देखें: https://t.me/mycoures123\n\n"
                    "📌 अगली PDF के लिए नंबर भेजें या /start करें।",
                    parse_mode='Markdown'
                )
                
                # ✅ स्टेप रीसेट करें
                user_sessions[chat_id]['step'] = 'WAITING_FILE_CHOICE'
                
            except Exception as e:
                if "413" in str(e) or "too large" in str(e):
                    bot.send_message(chat_id, f"❌ फाइल बहुत बड़ी है (50MB से ज्यादा)। Telegram 50MB से बड़ी फाइल अपलोड नहीं कर सकता।")
                else:
                    raise e
                    else:
            bot.send_message(chat_id, f"❌ PDF डाउनलोड विफल (Status Code: {r.status_code})।")
            
    except requests.exceptions.Timeout:
        bot.send_message(chat_id, "⏰ PDF डाउनलोड में टाइम आउट हो गया। फाइल बहुत बड़ी हो सकती है।")
    except Exception as e:
        print(f"❌ Upload Error: {e}")
        bot.send_message(chat_id, f"❌ अपलोड एरर: {str(e)}")

# ✅ बॉट को बैकग्राउंड में चलाने का सही तरीका
def run_bot():
    try:
        print("🤖 Bot is starting...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Bot Error: {e}")
        time.sleep(5)
        run_bot()  # Restart if error

# ✅ Flask के साथ Threading
if name == 'main':
    # बॉट को थ्रेड में चलाएं
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # थोड़ा delay दें ताकि बॉट स्टार्ट हो जाए
    time.sleep(2)
    print("🚀 Flask server starting on Render...")
    
    # Flask सर्वर चलाएं
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
    
            
