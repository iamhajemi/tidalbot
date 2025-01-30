from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import yt_dlp
import os
from flask import Flask
import threading

TELEGRAM_TOKEN = "8161571681:AAEpj7x4jiNA3ATMg3ajQMEmkcMp4rPYJHc"

# Flask app oluştur
app = Flask(__name__)

# Bot uygulamasını global olarak tanımla
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Müzik indirmek için bana bir YouTube linki gönder."
    )

async def download_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    
    # URL kontrolü
    if not ('youtube.com' in url or 'youtu.be' in url):
        await update.message.reply_text("Lütfen geçerli bir YouTube linki gönderin!")
        return
    
    await update.message.reply_text("İndirme başlıyor...")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'outtmpl': f'downloads/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'force_generic_extractor': False,
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'no_check_certificate': True,
        'prefer_insecure': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls'],
                'player_skip': ['js', 'configs', 'webpage']
            }
        }
    }
    
    try:
        # İndirme klasörünü oluştur
        os.makedirs('downloads', exist_ok=True)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Önce video bilgilerini al
            info = ydl.extract_info(url, download=False)
            if info is None:
                await update.message.reply_text("Video bilgileri alınamadı. Lütfen başka bir video deneyin.")
                return
                
            title = info.get('title', 'video')
            # Özel karakterleri temizle
            title = "".join(x for x in title if x.isalnum() or x in (' ', '-', '_'))
            file_path = f"downloads/{title}.mp3"
            
            # Şimdi indirmeyi dene
            ydl.download([url])
            
            await update.message.reply_text("Dosya yükleniyor...")
            
            # Dosyayı Telegram'a gönder
            with open(file_path, 'rb') as audio_file:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    title=title,
                    performer="YouTube Music Bot"
                )
            
            # Geçici dosyayı sil
            os.remove(file_path)
            
    except Exception as e:
        error_message = str(e)
        print(f"Hata detayı: {error_message}")  # Log için
        await update.message.reply_text(f"İndirme başarısız oldu. Lütfen başka bir video deneyin.")
        # Hata durumunda geçici dosyaları temizle
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Update None değilse ve message varsa
    if update and update.message:
        await update.message.reply_text("Bir hata oluştu. Lütfen geçerli bir YouTube linki gönderdiğinizden emin olun.")
    # Eğer effective_chat varsa
    elif update and update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Bir hata oluştu. Lütfen geçerli bir YouTube linki gönderdiğinizden emin olun."
        )
    print(f"Update {update} caused error {context.error}")

def run_bot():
    """Telegram botunu çalıştır"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_music))
    application.add_error_handler(error_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

@app.route('/')
def home():
    return 'Bot çalışıyor!'

def run_flask():
    """Flask uygulamasını çalıştır"""
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Render ortamında çalışıyorsa
    if os.environ.get('RENDER_EXTERNAL_URL'):
        # Bot'u ayrı bir thread'de başlat
        bot_thread = threading.Thread(target=run_bot)
        bot_thread.start()
        # Flask'i ana thread'de çalıştır
        run_flask()
    else:
        # Lokal ortamda sadece bot'u çalıştır
        run_bot() 