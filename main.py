import telebot
import requests
import io
import os
import re

# --- कॉन्फिगरेशन ---
BOT_TOKEN = '8984791001:AAEWdpO_Qfgw3d10S69QsMSWkk5SUZwktR8'
# प्राइवेट चैनल के लिए ID के आगे -100 लगाना जरूरी होता है
CHANNEL_ID = -1003946396225

bot = telebot.TeleBot(BOT_TOKEN)

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
    
    # Classplus / Edtech API लॉगिन
    login_url = "https://api.classplusapp.com/v2/users/login"
    login_payload = {
        "email": username if "@" in username else "",
        "mobile": username if "@" not in username else "",
        "password": password,
        "orgId": ""
    }
    
    try:
        res = session.post(login_url, json=login_payload, timeout=15)
        data = res.json()
        
        token = data.get('data', {}).get('token')
        if not token:
            token = data.get('token')
            
        if not token:
            bot.send_message(chat_id, "❌ लॉगिन विफल! यूजर ID या पासवर्ड गलत है। कृपया पुनः /start करें।")
            return
            
        user_sessions[chat_id]['token'] = token
        session.headers.update({"x-access-token": token, "Authorization": f"Bearer {token}"})
        
        # फोल्डर लिस्ट निकालना
        course_id = user_sessions[chat_id]['course_id']
        content_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={course_id}&folderId=0"
        
        c_res = session.get(content_url, timeout=15)
        c_data = c_res.json()
        
        items = c_data.get('data', {}).get('courseContent', [])
        folders = [item for item in items if item.get('type') == 'folder' or item.get('contentType') == 1]
        
        if not folders:
            # बैकअप: अगर डायरेक्ट फाइल्स हों
