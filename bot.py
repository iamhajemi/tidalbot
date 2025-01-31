from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import os
import subprocess
import re
import asyncio
import shutil
import json
import logging
import datetime

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = "8161571681:AAEpj7x4jiNA3ATMg3ajQMEmkcMp4rPYJHc"

def setup_tidal():
    logger.info("Tidal yapılandırması başlatılıyor...")
    config_dir = os.path.expanduser('~/.tidal-dl')
    os.makedirs(config_dir, exist_ok=True)
    
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
    logger.info("Tidal yapılandırması tamamlandı.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"Yeni kullanıcı başladı: {user.first_name} (ID: {user.id})")
    await update.message.reply_text(
        "Merhaba! Müzik indirmek için bana bir Tidal şarkı linki gönderin.\n"
        "Örnek: https://tidal.com/track/12345678"
    )

async def download_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    user = update.effective_user
    
    logger.info(f"İndirme isteği: {url} (Kullanıcı: {user.first_name}, ID: {user.id})")
    
    # Tidal URL kontrolü
    if not 'tidal.com' in url:
        logger.warning(f"Geçersiz URL isteği: {url} (Kullanıcı: {user.first_name})")
        await update.message.reply_text("Lütfen geçerli bir Tidal linki gönderin!")
        return
    
    try:
        # Track ID'yi URL'den çıkar
        track_id = re.search(r'track/(\d+)', url).group(1)
        logger.info(f"Track ID bulundu: {track_id}")
        
        await update.message.reply_text("İndirme başlıyor...")
        
        # İndirme klasörünü oluştur
        download_path = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_path, exist_ok=True)
        
        # tidal-dl komutunu çalıştır
        logger.info(f"İndirme başlatılıyor: {url}")
        download_cmd = f"tidal-dl -l {url} -o \"{download_path}\""
        process = subprocess.Popen(download_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode()
            logger.error(f"İndirme hatası: {error_msg}")
            await update.message.reply_text(f"İndirme hatası: {error_msg}")
            return
        
        logger.info("İndirme tamamlandı, dosya aranıyor...")
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
            file_size = os.path.getsize(newest_file) / (1024 * 1024)  # MB cinsinden
            logger.info(f"Dosya bulundu: {newest_file} ({file_size:.2f} MB)")
            
            await update.message.reply_text("Dosya yükleniyor...")
            
            try:
                # Dosyayı Telegram'a gönder
                logger.info("Dosya Telegram'a yükleniyor...")
                with open(newest_file, 'rb') as audio_file:
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_file,
                        title=os.path.splitext(os.path.basename(newest_file))[0],
                        performer="Tidal Music Bot"
                    )
                logger.info("Dosya başarıyla gönderildi")
                
                # Başarılı indirme sonrası dosyayı ve klasörünü sil
                try:
                    os.remove(newest_file)
                    logger.info(f"Dosya silindi: {newest_file}")
                    # Boş klasörleri temizle
                    for root, dirs, files in os.walk(download_path, topdown=False):
                        for name in dirs:
                            try:
                                os.rmdir(os.path.join(root, name))
                                logger.info(f"Boş klasör silindi: {os.path.join(root, name)}")
                            except:
                                pass
                except Exception as e:
                    logger.error(f"Dosya silme hatası: {str(e)}")
                    
            except Exception as send_error:
                logger.error(f"Dosya gönderme hatası: {str(send_error)}")
                await update.message.reply_text(f"Dosya gönderme hatası: {str(send_error)}")
        else:
            logger.warning("İndirilen dosya bulunamadı!")
            await update.message.reply_text("İndirilen dosya bulunamadı!")
            
    except Exception as e:
        logger.error(f"Genel hata: {str(e)}")
        await update.message.reply_text(f"Hata oluştu: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Hata oluştu: {context.error}")
    if update and update.message:
        await update.message.reply_text("Bir hata oluştu. Lütfen geçerli bir Tidal linki gönderdiğinizden emin olun.")

def main():
    logger.info("Bot başlatılıyor...")
    
    # Tidal yapılandırmasını ayarla
    setup_tidal()
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_music))
    application.add_error_handler(error_handler)
    
    logger.info("Bot hazır, çalışmaya başlıyor...")
    application.run_polling()

if __name__ == '__main__':
    main() 