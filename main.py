import io
import json
import os
import re
import threading
from flask import Flask
import requests
import telebot

BOTTOKEN = '8984791001:AAEWdpO_Qfgw3d10S69QsMSWkk5SUZwktR8'
TARGETCHANNEL = '@mycoures123'

bot = telebot.TeleBot(BOTTOKEN)
app = Flask("bot")


@app.route('/')
def index():
  return "PSCLive Appx Bot Active"


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
      "user-agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      ),
      "user-id": str(userid),
  }


def get_clean_title(item, default="Content"):
  for k in ['title', 'topic_name', 'name', 'file_name', 'description']:
    val = item.get(k)
    if val and str(val).strip():
      return str(val).strip()
  return default


def extract_direct_url(data_obj):
  raw_str = json.dumps(data_obj)
  full_url_match = re.search(
      r'https?://[^\s"\\]+?\.(?:pdf|mp4|m3u8)[^\s"\\]*', raw_str
  )
  if full_url_match:
    return full_url_match.group(0).replace('\\', '')
  rel_path_match = re.search(
      r'(?:paid_course\d*|uploads|content)/[^\s"\\]+?\.(?:pdf|mp4)', raw_str
  )
  if rel_path_match:
    return f"https://static-db-v2.appx.co.in/{rel_path_match.group(0)}"
  return None


@bot.message_handler(commands=['start'])
def handlestart(message):
  chatid = message.chat.id
  usersessions[chatid] = {'step': 'WAITING_URL'}
  bot.send_message(
      chatid,
      "👋 PSCLive डाउनलोडर बॉट\n\n1️⃣ कोर्स का URL या ID भेजें:\n👉 उदा."
      " https://app.psclive.com/new-courses/221/content",
  )


@bot.message_handler(
    func=lambda msg: usersessions.get(msg.chat.id, {}).get('step')
    == 'WAITING_URL'
)
def handleurl(message):
  chatid = message.chat.id
  url = message.text.strip()
  coursematch = re.search(r'courses/(\d+)', url)
  courseid = (
      coursematch.group(1)
      if coursematch
      else (url if url.isdigit() else None)
  )

  if not courseid:
    bot.send_message(chatid, "❌ गलत URL! कृपया सही कोर्स लिंक भेजें।")
    return

  usersessions[chatid]['courseid'] = courseid
  usersessions[chatid]['step'] = 'WAITING_TOKEN'
  bot.send_message(
      chatid, f"✅ कोर्स ID: {courseid}\n\n2️⃣ अब अपना पूरा Token भेजें:"
  )


@bot.message_handler(
    func=lambda msg: usersessions.get(msg.chat.id, {}).get('step')
    == 'WAITING_TOKEN'
)
def handletoken(message):
  chatid = message.chat.id
  token = message.text.strip()

  if not token.startswith("eyJ"):
    bot.send_message(chatid, "❌ अमान्य टोकन!")
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
      bot.send_message(chatid, "⚠️ कोई सामग्री नहीं मिली।")
      return

    usersessions[chatid]['items'] = valid_items
    usersessions[chatid]['step'] = 'WAITING_SELECTION'

    msgtext = "📁 मुख्य सूची:\n\n"
    for idx, item in enumerate(valid_items, start=1):
      title = get_clean_title(item, f"Item {idx}")
      msgtext += f"{idx}. 📁 {title}\n"

    msgtext += "\n👉 नंबर भेजें:"
    bot.send_message(chatid, msgtext)
  except Exception as e:
    bot.send_message(chatid, f"❌ एरर: {str(e)}")
      @bot.message_handler(
    func=lambda msg: usersessions.get(msg.chat.id, {}).get('step')
    == 'WAITING_SELECTION'
)
def handleselection(message):
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

  selected_id = (
      selected.get('id')
      or selected.get('folder_id')
      or selected.get('content_id')
      or 0
  )
  file_title = get_clean_title(selected, f"Item_{choice}")

  # 1. पहले सब-फ़ोल्डर्स चेक करना
  sub_url = f"https://psclivepawansirapi.akamai.net.in/get/folder_contentsv3?course_id={courseid}&parent_id={selected_id}&start=0"
  try:
    res = requests.get(sub_url, headers=headers, timeout=20)
    sub_items = res.json().get('data', [])
    valid_sub = [i for i in sub_items if isinstance(i, dict)]

    if valid_sub and len(valid_sub) > 0:
      usersessions[chatid]['items'] = valid_sub
      msgtext = f"📂 {file_title} के अंदर सामग्री:\n\n"
      for fidx, item in enumerate(valid_sub, start=1):
        title = get_clean_title(item, f"Item {fidx}")
        msgtext += f"{fidx}. 📄 {title}\n"
      msgtext += "\n👉 डाउनलोड या खोलने के लिए नंबर भेजें:"
      bot.send_message(chatid, msgtext)
      return
  except Exception:
    pass

  # 2. फ़ाइल डाउनलोड लिंक निकालना
  bot.send_message(chatid, f"⏳ {file_title} का लिंक प्रोसेस किया जा रहा है...")

  file_url = extract_direct_url(selected)

  if not file_url and selected_id:
    endpoints = [
        f"https://psclivepawansirapi.akamai.net.in/get/single_folder_content?course_id={courseid}&content_id={selected_id}",
        f"https://psclivepawansirapi.akamai.net.in/get/pdf_details?course_id={courseid}&content_id={selected_id}",
        f"https://psclivepawansirapi.akamai.net.in/get/content_details?course_id={courseid}&content_id={selected_id}",
    ]
    for ep in endpoints:
      try:
        res = requests.get(ep, headers=headers, timeout=15)
        found = extract_direct_url(res.json())
        if found:
          file_url = found
          break
      except Exception:
        continue

  if not file_url:
    debug_str = json.dumps(selected, ensure_ascii=False)
    bot.send_message(chatid, f"⚠️ सीधा लिंक नहीं मिला। सर्वर डेटा:\n{debug_str[:400]}")
    return

  is_video = any(ext in file_url.lower() for ext in ['.mp4', '.m3u8'])
  ext = ".mp4" if is_video else ".pdf"
  if not file_title.lower().endswith(ext):
    file_title += ext

  bot.send_message(chatid, f"⬇️ {file_title} डाउनलोड की जा रही है...")

  try:
    r = requests.get(file_url, headers=headers, stream=True, timeout=600)
    content_size = len(r.content)
    size_mb = content_size / (1024 * 1024)

    if size_mb > 49:
      bot.send_message(
          chatid,
          f"ℹ️ फ़ाइल का साइज़ {size_mb:.2f} MB है (Telegram सीमा 50 MB से"
          " बड़ा)।\n\n🔗 डायरेक्ट डाउनलोड लिंक आपके चैनल पर भेज दिया गया है।",
      )
      bot.send_message(
          TARGETCHANNEL,
          f"📚 {file_title}\n📦 साइज़: {size_mb:.2f} MB\n\n🔗 डाउनलोड"
          f" लिंक:\n{file_url}",
      )
      bot.send_message(
          chatid,
          f"✅ सफलता! फ़ाइल का लिंक चैनल {TARGETCHANNEL} पर भेज दिया गया है।",
      )
      return

    file_bytes = io.BytesIO(r.content)
    file_bytes.name = file_title

    if is_video:
      bot.send_video(
          chat_id=TARGETCHANNEL,
          video=file_bytes,
          caption=f"🎥 {file_title}",
          timeout=600,
      )
    else:
      bot.send_document(
          chat_id=TARGETCHANNEL,
          document=file_bytes,
          caption=f"📚 {file_title}",
          timeout=600,
      )

    bot.send_message(
        chatid,
        f"✅ सफलता! {file_title} चैनल पर भेज दी गई है।\n\n👉 अगली फ़ाइल का"
        " नंबर भेजें।",
    )
      except Exception as e:
    bot.send_message(chatid, f"❌ एरर: {str(e)}")


def runpolling():
  bot.infinity_polling(skip_pending=True)


threading.Thread(target=runpolling, daemon=True).start()

if __name__ == '__main__':
  port = int(os.environ.get("PORT", 5000))
  app.run(host='0.0.0.0', port=port)
