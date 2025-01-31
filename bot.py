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
        
        # Tidal arama URL'lerini dene
        search_urls = [
            f"https://tidal.com/browse/search?q={artist}+{title}",
            f"https://tidal.com/browse/track/{artist}+{title}",
            f"https://tidal.com/browse/search/tracks?q={artist}+{title}",
            f"https://tidal.com/browse/artist/{artist}/tracks",
            f"https://tidal.com/search/tracks?q={artist}+{title}"
        ]
        
        for url in search_urls:
            logger.info(f"Denenen URL: {url}")
            download_cmd = f"tidal-dl -l \"{url}\""
            process = subprocess.Popen(download_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            
            if stdout:
                output = stdout.decode()
                logger.info(f"tidal-dl çıktısı:\n{output}")
                
                # Başarılı indirme kontrolü
                if "Downloading" in output or "Download completed" in output:
                    return url, None
                
                # Track ID'yi bul
                id_match = re.search(r'track/(\d+)', output)
                if id_match:
                    track_id = id_match.group(1)
                    track_url = f"https://tidal.com/track/{track_id}"
                    logger.info(f"Şarkı URL'si bulundu: {track_url}")
                    
                    # Track URL'sini doğrula
                    verify_cmd = f"tidal-dl -l {track_url}"
                    verify_process = subprocess.Popen(verify_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    verify_stdout, verify_stderr = verify_process.communicate()
                    
                    if verify_stdout and "ERROR" not in verify_stdout.decode().upper():
                        return track_url, None
            
            if stderr:
                logger.error(f"tidal-dl hatası:\n{stderr.decode()}")
        
        # Son çare: Direkt track ID'leri dene
        track_ids = ["1988644", "1988642", "1988643"]  # Örnek track ID'leri
        for track_id in track_ids:
            track_url = f"https://tidal.com/track/{track_id}"
            verify_cmd = f"tidal-dl -l {track_url}"
            verify_process = subprocess.Popen(verify_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            verify_stdout, verify_stderr = verify_process.communicate()
            
            if verify_stdout and "ERROR" not in verify_stdout.decode().upper():
                return track_url, None
        
        return None, (
            "Şarkı bulunamadı. Lütfen şu seçenekleri deneyin:\n"
            "1. Şarkı adını ve sanatçıyı kontrol edin\n"
            "2. Direkt Tidal linkini gönderin\n"
            "3. Başka bir şarkı deneyin"
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