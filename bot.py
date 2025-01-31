from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import os
import subprocess
import re
import asyncio
import shutil
import json

TELEGRAM_TOKEN = "8161571681:AAEpj7x4jiNA3ATMg3ajQMEmkcMp4rPYJHc"

def setup_tidal():
    # Tidal yapılandırma klasörünü oluştur
    config_dir = os.path.expanduser('~/.tidal-dl')
    os.makedirs(config_dir, exist_ok=True)
    
    # Tidal yapılandırma dosyasını oluştur
    config = {
        "loginByWeb": False,
        "apiKeyIndex": 4,
        "addExplicitTag": True,
        "addHyphen": True,
        "addYear": False,
        "includeEP": True,
        "saveCovers": True,
        "language": "TR",
        "lyricFile": False,
        "multiThread": True,
        "downloadPath": "./downloads",
        "quality": "Master",
        "usePlaylistFolder": True,
        "albumFolderFormat": "{ArtistName}/{Flag} {AlbumTitle} [{AlbumID}] [{AlbumYear}]",
        "trackFileFormat": "{TrackNumber}. {ArtistName} - {TrackTitle}{ExplicitFlag}",
        "videoFileFormat": "{ArtistName} - {VideoTitle}{ExplicitFlag}",
        "checkExist": True,
        "artistBeforeTitle": False,
        "showProgress": True,
        "showTrackInfo": True,
        "saveAlbumInfo": False,
        "lyricProvider": "Local",
        "apiKeys": {
            "platform": "Android",
            "formats": "AAC_320,AAC_96,AAC_160,AAC_PLUS,MP3_320,MP3_128,MP3_192,MP3_256",
            "clientId": "zU4XHVVkc2tDPo4t",
            "clientSecret": "VJKhDFqJPqvsPVNBV6ukXTJmwlvbttP7wlMlrc72se4="
        }
    }
    
    config_file = os.path.join(config_dir, 'tidal-dl.json')
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba! Müzik indirmek için bana bir Tidal şarkı linki gönderin.\n"
        "Örnek: https://tidal.com/track/12345678"
    )

async def download_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    
    # Tidal URL kontrolü
    if not 'tidal.com' in url:
        await update.message.reply_text("Lütfen geçerli bir Tidal linki gönderin!")
        return
    
    try:
        # Track ID'yi URL'den çıkar
        track_id = re.search(r'track/(\d+)', url).group(1)
        
        await update.message.reply_text("İndirme başlıyor...")
        
        # İndirme klasörünü oluştur
        download_path = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_path, exist_ok=True)
        
        # tidal-dl komutunu çalıştır
        download_cmd = f"tidal-dl -l {url} -o \"{download_path}\""
        process = subprocess.Popen(download_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            await update.message.reply_text(f"İndirme hatası: {stderr.decode()}")
            return
        
        await asyncio.sleep(2)
        
        # Tüm alt klasörleri dahil ederek M4A dosyalarını bul
        audio_files = []
        for root, dirs, files in os.walk(download_path):
            for file in files:
                if file.endswith('.m4a'):
                    full_path = os.path.join(root, file)
                    audio_files.append(full_path)
        
        if audio_files:
            newest_file = max(audio_files, key=os.path.getctime)
            
            await update.message.reply_text("Dosya yükleniyor...")
            
            try:
                # Dosyayı Telegram'a gönder
                with open(newest_file, 'rb') as audio_file:
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_file,
                        title=os.path.splitext(os.path.basename(newest_file))[0],
                        performer="Tidal Music Bot"
                    )
                
                # Başarılı indirme sonrası dosyayı ve klasörünü sil
                try:
                    os.remove(newest_file)
                    # Boş klasörleri temizle
                    for root, dirs, files in os.walk(download_path, topdown=False):
                        for name in dirs:
                            try:
                                os.rmdir(os.path.join(root, name))
                            except:
                                pass
                except:
                    pass
                    
            except Exception as send_error:
                await update.message.reply_text(f"Dosya gönderme hatası: {str(send_error)}")
        else:
            await update.message.reply_text("İndirilen dosya bulunamadı!")
            
    except Exception as e:
        await update.message.reply_text(f"Hata oluştu: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update and update.message:
        await update.message.reply_text("Bir hata oluştu. Lütfen geçerli bir Tidal linki gönderdiğinizden emin olun.")
    else:
        print(f"Hata oluştu: {context.error}")

def main():
    # Tidal yapılandırmasını ayarla
    setup_tidal()
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_music))
    application.add_error_handler(error_handler)
    
    application.run_polling()

if __name__ == '__main__':
    main() 