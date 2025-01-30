from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from pytube import YouTube
import os
from threading import Thread
from flask import Flask, request

TELEGRAM_TOKEN = "8161571681:AAEpj7x4jiNA3ATMg3ajQMEmkcMp4rPYJHc"

# Flask uygulaması
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot çalışıyor!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

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
    
    try:
        # İndirme klasörünü oluştur
        os.makedirs('downloads', exist_ok=True)
        
        # YouTube videosunu indir
        yt = YouTube(url)
        audio_stream = yt.streams.filter(only_audio=True).first()
        
        # Önce mp4 olarak indir
        downloaded_file = audio_stream.download(output_path='downloads')
        base, ext = os.path.splitext(downloaded_file)
        file_path = base + '.mp3'
        
        # MP4'ü MP3'e dönüştür
        os.system(f'ffmpeg -i "{downloaded_file}" -vn -ab 320k "{file_path}"')
        os.remove(downloaded_file)  # MP4 dosyasını sil
        
        await update.message.reply_text("Dosya yükleniyor...")
        
        # Dosyayı Telegram'a gönder
        with open(file_path, 'rb') as audio_file:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=audio_file,
                title=yt.title,
                performer="YouTube Music Bot"
            )
        
        # Geçici dosyayı sil
        os.remove(file_path)
        
    except Exception as e:
        await update.message.reply_text(f"Hata oluştu: {str(e)}")
        # Hata durumunda geçici dosyaları temizle
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Update null kontrolü
    if update and update.message:
        await update.message.reply_text("Bir hata oluştu. Lütfen geçerli bir YouTube linki gönderdiğinizden emin olun.")
    else:
        print(f"Bir hata oluştu: {context.error}")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_music))
    application.add_error_handler(error_handler)
    
    # Flask'ı ayrı bir thread'de çalıştır
    Thread(target=run_flask).start()
    
    # Polling'i başlat
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 