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
import requests

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = "8161571681:AAEpj7x4jiNA3ATMg3ajQMEmkcMp4rPYJHc"
TIDAL_API_TOKEN = "zU4XHVVkc2tDPo4t"  # Tidal API token

def update_from_github():
    logger.info("GitHub'dan güncel kod alınıyor...")
    try:
        # Git pull komutunu çalıştır
        process = subprocess.Popen(["git", "pull", "origin", "main"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            logger.info("GitHub'dan güncelleme başarılı!")
            if stdout:
                logger.info(f"Git çıktısı:\n{stdout.decode()}")
        else:
            logger.error(f"Git pull hatası: {stderr.decode()}")
    except Exception as e:
        logger.error(f"GitHub güncelleme hatası: {str(e)}")

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

async def search_tidal_track(query):
    """Tidal'da şarkı ara"""
    try:
        # Şarkıcı ve şarkı adını ayır
        parts = query.split(' ', 1)
        if len(parts) != 2:
            return None, "Lütfen 'Sanatçı Şarkı' formatında yazın. Örnek: 'Zamiq Kaman'"
        
        artist, title = parts
        logger.info(f"Şarkı aranıyor - Sanatçı: {artist}, Şarkı: {title}")
        
        # Bilinen Tidal track ID'leri
        known_tracks = {
            "Tarkan Kuzu Kuzu": "251338778",  # Örnek
            "Zamiq Kaman": "150853251",       # Örnek
        }
        
        # Önce bilinen şarkılarda ara
        search_key = f"{artist} {title}"
        if search_key in known_tracks:
            track_url = f"https://tidal.com/track/{known_tracks[search_key]}"
            logger.info(f"Bilinen şarkı bulundu: {track_url}")
            return track_url, None
        
        # Farklı URL formatlarını dene
        search_urls = [
            f"https://tidal.com/browse/track/{artist.replace(' ', '%20')}%20{title.replace(' ', '%20')}",
            f"https://tidal.com/search/track/{artist.replace(' ', '%20')}%20{title.replace(' ', '%20')}",
            f"https://tidal.com/search?q={artist.replace(' ', '+')}+{title.replace(' ', '+')}",
            f"https://listen.tidal.com/search?q={artist.replace(' ', '%20')}%20{title.replace(' ', '%20')}"
        ]
        
        for url in search_urls:
            logger.info(f"URL deneniyor: {url}")
            try:
                # Web sitesinden içeriği al
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    content = response.text
                    # Track ID'yi bul
                    matches = re.findall(r'track[/"](\d+)', content)
                    for track_id in matches:
                        track_url = f"https://tidal.com/track/{track_id}"
                        # Track'i doğrula
                        verify_cmd = f"tidal-dl -l {track_url}"
                        process = subprocess.Popen(verify_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        stdout, stderr = process.communicate()
                        
                        if stdout and 'ERROR' not in stdout.decode().upper():
                            logger.info(f"Şarkı URL'si bulundu: {track_url}")
                            return track_url, None
            except Exception as e:
                logger.error(f"URL hatası ({url}): {str(e)}")
                continue
        
        # Hiçbir şey bulunamadıysa, kullanıcıdan Tidal linki isteyelim
        return None, (
            "Şarkı Tidal'da bulunamadı.\n\n"
            "Lütfen şu adımları izleyin:\n"
            "1. Tidal web sitesine gidin (tidal.com)\n"
            "2. Şarkıyı arayın\n"
            "3. Şarkının linkini kopyalayıp buraya gönderin"
        )
        
    except Exception as e:
        logger.error(f"Şarkı arama hatası: {str(e)}")
        return None, f"Arama sırasında hata oluştu: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"Yeni kullanıcı başladı: {user.first_name} (ID: {user.id})")
    await update.message.reply_text(
        "Merhaba! Müzik indirmek için:\n"
        "1. Tidal şarkı linki gönderin\n"
        "2. Veya 'Sanatçı Şarkı' formatında yazın\n\n"
        "Örnekler:\n"
        "- https://tidal.com/track/12345678\n"
        "- Zamiq Kaman"
    )

async def download_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    user = update.effective_user
    
    logger.info(f"İstek alındı: {url} (Kullanıcı: {user.first_name}, ID: {user.id})")
    
    # Tidal URL kontrolü
    if not 'tidal.com' in url:
        # URL değilse, şarkı araması yap
        track_url, error = await search_tidal_track(url)
        if error:
            await update.message.reply_text(error)
            return
        url = track_url
        await update.message.reply_text(f"Şarkı bulundu: {url}\nİndirme başlıyor...")
    
    try:
        # Track ID'yi URL'den çıkar
        track_id = re.search(r'track/(\d+)', url).group(1)
        logger.info(f"Track ID bulundu: {track_id}")
        
        await update.message.reply_text("İndirme başlıyor...")
        
        # İndirme klasörünü oluştur
        download_path = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_path, exist_ok=True)
        logger.info(f"İndirme klasörü: {download_path}")
        
        # tidal-dl komutunu çalıştır
        logger.info(f"İndirme başlatılıyor: {url}")
        download_cmd = f"tidal-dl -l {url} -o \"{download_path}\""
        logger.info(f"Çalıştırılan komut: {download_cmd}")
        process = subprocess.Popen(download_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        # tidal-dl çıktısını logla
        if stdout:
            logger.info(f"tidal-dl stdout:\n{stdout.decode()}")
        if stderr:
            logger.info(f"tidal-dl stderr:\n{stderr.decode()}")
        
        if process.returncode != 0:
            error_msg = stderr.decode()
            logger.error(f"İndirme hatası (kod: {process.returncode}): {error_msg}")
            await update.message.reply_text(f"İndirme hatası: {error_msg}")
            return
        
        logger.info("İndirme tamamlandı, dosya aranıyor...")
        logger.info(f"Mevcut çalışma dizini: {os.getcwd()}")
        logger.info(f"Downloads klasörü tam yolu: {os.path.abspath(download_path)}")
        
        # Dosya araması öncesi klasör içeriğini kontrol et
        logger.info("=== Klasör içeriği detayları ===")
        for root, dirs, files in os.walk(download_path):
            logger.info(f"\nKlasör: {root}")
            if dirs:
                logger.info(f"Alt klasörler: {', '.join(dirs)}")
            if files:
                logger.info(f"Dosyalar: {', '.join(files)}")
                for file in files:
                    file_path = os.path.join(root, file)
                    file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                    logger.info(f"- {file}: {file_size:.2f} MB")
            else:
                logger.info("Bu klasörde dosya yok")
        logger.info("=== Klasör içeriği sonu ===")
        
        await asyncio.sleep(2)
        
        # Tüm alt klasörleri dahil ederek M4A dosyalarını bul
        audio_files = []
        logger.info("\nM4A dosyaları aranıyor...")
        for root, dirs, files in os.walk(download_path):
            for file in files:
                if file.endswith('.m4a'):
                    full_path = os.path.join(root, file)
                    audio_files.append(full_path)
                    logger.info(f"M4A dosyası bulundu: {full_path}")
        
        if not audio_files:
            logger.warning(f"Hiç M4A dosyası bulunamadı! Aranan klasör: {download_path}")
            logger.info("Desteklenen tüm ses dosyaları aranıyor...")
            for root, dirs, files in os.walk(download_path):
                for file in files:
                    if file.endswith(('.m4a', '.mp3', '.flac', '.wav')):
                        logger.info(f"Ses dosyası bulundu: {os.path.join(root, file)}")
            await update.message.reply_text("İndirilen dosya bulunamadı!")
            return
        
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
    
    # GitHub'dan güncelle
    update_from_github()
    
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