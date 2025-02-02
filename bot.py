from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import os
import subprocess
import re
import asyncio
import shutil
import json
import logging
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

# Kalite seçenekleri
QUALITY_OPTIONS = {
    "normal": "Normal",    # Normal kalite (AAC 320kbps)
    "high": "High",        # Yüksek kalite (MP3 320kbps)
    "hifi": "HiFi",        # Hi-Fi kalite (FLAC)
    "master": "Master"     # Master kalite
}

# Kullanıcı kalite ayarları
user_quality = {}

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

def setup_tidal(quality=None):
    logger.info("Tidal yapılandırması başlatılıyor...")
    
    # Config dosyasını botun kendi klasöründe oluştur
    config_dir = os.path.join(os.getcwd(), "default")
    os.makedirs(config_dir, exist_ok=True)
    
    config = {
        "albumFolderFormat": "{ArtistName}/{Flag} {AlbumTitle} [{AlbumID}] [{AlbumYear}]",
        "apiKeyIndex": 4,
        "audioQuality": quality if quality else "Master",
        "checkExist": True,
        "downloadDelay": 2,  # İndirmeler arası 2 saniye bekle
        "downloadPath": "./downloads",
        "includeEP": True,
        "language": "TR",
        "lyricFile": False,
        "multiThread": False,  # Çoklu thread'i kapatalım
        "playlistFolderFormat": "Playlist/{PlaylistName} [{PlaylistUUID}]",
        "saveAlbumInfo": False,
        "saveCovers": True,
        "showProgress": True,
        "showTrackInfo": True,
        "trackFileFormat": "{TrackNumber}. {ArtistName} - {TrackTitle}{ExplicitFlag}",
        "usePlaylistFolder": True,
        "videoFileFormat": "{ArtistName} - {VideoTitle}{ExplicitFlag}",
        "videoQuality": "P360",
        "maxRetryTimes": 5,  # Maksimum yeniden deneme sayısı
        "retryDelay": 5,  # Yeniden denemeler arası 5 saniye bekle
        "requestTimeout": 30,  # İstek zaman aşımı süresi 30 saniye
        "downloadTimeout": 600  # İndirme zaman aşımı süresi 10 dakika
    }
    
    # Ana config dosyasını sil (eğer varsa)
    home_config = os.path.expanduser('~/.tidal-dl.json')
    if os.path.exists(home_config):
        try:
            os.remove(home_config)
            logger.info(f"Eski config dosyası silindi: {home_config}")
        except Exception as e:
            logger.error(f"Eski config dosyası silinemedi: {str(e)}")
    
    # Yeni config dosyasını oluştur
    config_file = os.path.join(config_dir, '.tidal-dl.json')
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)
    
    # Sembolik link oluştur
    try:
        if os.path.exists(home_config):
            os.remove(home_config)
        os.symlink(config_file, home_config)
        logger.info(f"Sembolik link oluşturuldu: {home_config} -> {config_file}")
    except Exception as e:
        logger.error(f"Sembolik link oluşturulamadı: {str(e)}")
        # Sembolik link oluşturulamazsa dosyayı kopyala
        try:
            shutil.copy2(config_file, home_config)
            logger.info(f"Config dosyası kopyalandı: {config_file} -> {home_config}")
        except Exception as e:
            logger.error(f"Config dosyası kopyalanamadı: {str(e)}")
    
    logger.info(f"Tidal yapılandırması tamamlandı. Kalite: {config['audioQuality']}")
    logger.info(f"Config dosyası: {config_file}")

def clean_downloads():
    """İndirme klasörünü temizle"""
    try:
        download_path = os.path.join(os.getcwd(), "downloads")
        if os.path.exists(download_path):
            shutil.rmtree(download_path)
            logger.info("Downloads klasörü temizlendi")
    except Exception as e:
        logger.error(f"Downloads klasörü temizleme hatası: {str(e)}")

async def find_music_file(download_path):
    """İndirilen müzik dosyasını bul"""
    max_attempts = 5  # Maksimum deneme sayısı
    attempt = 0
    
    while attempt < max_attempts:
        logger.info(f"Dosya arama denemesi {attempt + 1}/{max_attempts}")
        
        # Tüm müzik dosyalarını bul
        found_files = []
        
        # Önce sanatçı klasörlerini bul
        try:
            artist_folders = [d for d in os.listdir(download_path) 
                            if os.path.isdir(os.path.join(download_path, d))]
            
            logger.info(f"Bulunan sanatçı klasörleri: {artist_folders}")
            
            for artist_folder in artist_folders:
                artist_path = os.path.join(download_path, artist_folder)
                logger.info(f"Sanatçı klasörü kontrol ediliyor: {artist_folder}")
                
                try:
                    # Albüm klasörlerini bul
                    album_folders = [d for d in os.listdir(artist_path) 
                                   if os.path.isdir(os.path.join(artist_path, d))]
                    
                    logger.info(f"Bulunan albüm klasörleri: {album_folders}")
                    
                    for album_folder in album_folders:
                        album_path = os.path.join(artist_path, album_folder)
                        logger.info(f"Albüm klasörü kontrol ediliyor: {album_folder}")
                        
                        try:
                            # Müzik dosyalarını bul
                            for file in os.listdir(album_path):
                                if file.endswith(('.m4a', '.mp3', '.flac')):
                                    full_path = os.path.join(album_path, file)
                                    found_files.append(full_path)
                                    logger.info(f"Müzik dosyası bulundu: {full_path}")
                        except Exception as e:
                            logger.error(f"Albüm klasörü okuma hatası: {str(e)}")
                            continue
                except Exception as e:
                    logger.error(f"Sanatçı klasörü okuma hatası: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"Downloads klasörü okuma hatası: {str(e)}")
        
        # Eğer dosya bulunduysa
        if found_files:
            logger.info(f"Toplam {len(found_files)} müzik dosyası bulundu")
            
            # En son değiştirilen dosyayı bul
            newest_file = max(found_files, key=os.path.getmtime)
            logger.info(f"En son değiştirilen dosya: {newest_file}")
            return [newest_file]
        
        attempt += 1
        if attempt < max_attempts:
            logger.info("Dosya bulunamadı, 3 saniye bekleniyor...")
            await asyncio.sleep(3)
    
    logger.error("Hiç müzik dosyası bulunamadı!")
    return []  # Dosya bulunamadı

async def try_download_with_quality(cmd_base, quality, update):
    """Belirli bir kalitede indirmeyi dene"""
    quality_param = f"-q {quality}"
    download_cmd = f"{cmd_base} {quality_param}"
    
    logger.info(f"İndirme deneniyor: {quality}")
    
    process = subprocess.Popen(
        download_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=subprocess.STARTUPINFO() if os.name == 'nt' else None,
        encoding='cp1254',
        errors='ignore'
    )
    
    stdout, stderr = process.communicate()
    
    # İndirme sonrası biraz bekle
    await asyncio.sleep(3)
    
    # İndirilen dosyaları kontrol et
    download_path = os.path.join(os.getcwd(), "downloads")
    if not os.path.exists(download_path):
        logger.info(f"{quality} kalitesinde indirme başarısız - Klasör yok")
        return False
        
    # Sanatçı klasörlerini kontrol et
    artist_folders = [d for d in os.listdir(download_path) 
                     if os.path.isdir(os.path.join(download_path, d))]
                     
    if not artist_folders:
        logger.info(f"{quality} kalitesinde indirme başarısız - Sanatçı klasörü yok")
        return False
        
    # Her sanatçı klasöründe albüm ve şarkı ara
    for artist_folder in artist_folders:
        artist_path = os.path.join(download_path, artist_folder)
        album_folders = [d for d in os.listdir(artist_path) 
                        if os.path.isdir(os.path.join(artist_path, d))]
                        
        for album_folder in album_folders:
            album_path = os.path.join(artist_path, album_folder)
            music_files = [f for f in os.listdir(album_path) 
                          if f.endswith(('.m4a', '.mp3', '.flac'))]
                          
            if music_files:
                logger.info(f"{quality} kalitesinde indirme başarılı - Dosyalar bulundu")
                return True
                
    logger.info(f"{quality} kalitesinde indirme başarısız - Müzik dosyası yok")
    return False

async def get_playlist_tracks(playlist_id):
    """Playlist'teki şarkıları al"""
    try:
        # Önce playlist URL'sini oluştur
        playlist_url = f"https://tidal.com/browse/playlist/{playlist_id}"
        
        # tidal-dl ile playlist bilgilerini al
        process = subprocess.run(
            ["tidal-dl", "-p", playlist_id],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        
        if process.returncode != 0:
            logger.error(f"Playlist bilgileri alınamadı: {process.stderr}")
            return []
            
        # İndirme klasörünü kontrol et
        download_path = os.path.join(os.getcwd(), "downloads")
        if os.path.exists(download_path):
            # Playlist klasörünü bul
            playlist_folders = [d for d in os.listdir(download_path) 
                              if os.path.isdir(os.path.join(download_path, d)) and "Playlist" in d]
            
            if playlist_folders:
                playlist_path = os.path.join(download_path, playlist_folders[0])
                # Playlist içindeki şarkıları bul
                track_files = []
                for root, dirs, files in os.walk(playlist_path):
                    for file in files:
                        if file.endswith(('.m4a', '.mp3', '.flac')):
                            track_files.append(os.path.join(root, file))
                
                # Dosya yollarından track ID'lerini çıkar
                track_ids = []
                for file_path in track_files:
                    track_match = re.search(r'\[(\d+)\]', file_path)
                    if track_match:
                        track_ids.append(track_match.group(1))
                
                return track_ids
        
        return []
        
    except Exception as e:
        logger.error(f"Playlist track listesi alınamadı: {str(e)}")
        return []

async def download_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    user = update.effective_user
    
    logger.info(f"İstek alındı: {url} (Kullanıcı: {user.first_name}, ID: {user.id})")
    
    # İndirme klasörünü temizle
    clean_downloads()
    
    # Tidal URL kontrolü
    if not 'tidal.com' in url:
        await update.message.reply_text("❌ Geçerli bir Tidal linki gönderin")
        return
    
    try:
        # URL tipini kontrol et
        if 'playlist' in url:
            playlist_match = re.search(r'playlist/([a-zA-Z0-9-]+)', url)
            if not playlist_match:
                await update.message.reply_text("❌ Geçerli bir Tidal playlist linki gönderin")
                return
            
            playlist_id = playlist_match.group(1)
            await update.message.reply_text("🔍 Playlist indiriliyor...")
            
            # Maksimum 3 deneme yap
            max_retries = 3
            for retry in range(max_retries):
                try:
                    # tidal-dl komutunu çalıştır
                    process = subprocess.Popen(
                        ["tidal-dl", "-l", url],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        encoding='utf-8',
                        errors='ignore'
                    )
                    
                    # Çıktıyı gerçek zamanlı olarak kontrol et
                    while True:
                        output = process.stdout.readline()
                        if output == '' and process.poll() is not None:
                            break
                        if output:
                            output = output.strip()
                            logger.info(output)
                            # Önemli hata mesajlarını kullanıcıya bildir
                            if "ERROR" in output or "Error" in output or "failed" in output.lower():
                                await update.message.reply_text(f"⚠️ {output}")
                    
                    # İşlem tamamlandı, çıktıyı kontrol et
                    stdout, stderr = process.communicate()
                    
                    if process.returncode == 0:
                        # İndirme başarılı oldu, dosyaları kontrol et
                        await asyncio.sleep(5)  # Dosyaların yazılması için bekle
                        
                        # İndirilen dosyaları bul
                        download_path = os.path.join(os.getcwd(), "downloads")
                        if not os.path.exists(download_path):
                            if retry < max_retries - 1:
                                logger.info(f"Deneme {retry + 1}/{max_retries} başarısız, tekrar deneniyor...")
                                await update.message.reply_text(f"⚠️ Deneme {retry + 1} başarısız, tekrar deneniyor...")
                                await asyncio.sleep(3)
                                continue
                            else:
                                await update.message.reply_text("❌ İndirme klasörü bulunamadı")
                                return
                        
                        # Tüm müzik dosyalarını bul
                        all_files = []
                        for root, dirs, files in os.walk(download_path):
                            for file in files:
                                if file.endswith(('.m4a', '.mp3', '.flac')):
                                    all_files.append(os.path.join(root, file))
                        
                        if not all_files:
                            if retry < max_retries - 1:
                                logger.info(f"Deneme {retry + 1}/{max_retries} başarısız, tekrar deneniyor...")
                                await update.message.reply_text(f"⚠️ Deneme {retry + 1} başarısız, tekrar deneniyor...")
                                await asyncio.sleep(3)
                                continue
                            else:
                                await update.message.reply_text("❌ İndirilen şarkı bulunamadı")
                                return
                        
                        # Şarkılar bulundu, göndermeye başla
                        await update.message.reply_text(f"📝 Toplam {len(all_files)} şarkı bulundu, gönderiliyor...")
                        
                        # Her şarkıyı gönder
                        for index, file_path in enumerate(all_files, 1):
                            try:
                                # Dosya bilgilerini al
                                file_name = os.path.basename(file_path)
                                path_parts = file_path.split(os.sep)
                                artist = path_parts[-2].split('[')[0].strip() if len(path_parts) > 2 else "Bilinmeyen Sanatçı"
                                
                                # Dosyayı Telegram'a gönder
                                with open(file_path, 'rb') as audio_file:
                                    await context.bot.send_audio(
                                        chat_id=chat_id,
                                        audio=audio_file,
                                        title=os.path.splitext(file_name)[0],
                                        performer=artist,
                                        caption=f"🎵 {file_name}\n👤 {artist}\n📊 {index}/{len(all_files)}"
                                    )
                            except Exception as e:
                                logger.error(f"Dosya gönderme hatası: {str(e)}")
                                continue
                        
                        await update.message.reply_text("✅ Playlist gönderme tamamlandı!")
                        clean_downloads()
                        return
                    
                    else:
                        # İndirme başarısız oldu
                        if retry < max_retries - 1:
                            logger.info(f"Deneme {retry + 1}/{max_retries} başarısız, tekrar deneniyor...")
                            await update.message.reply_text(f"⚠️ Deneme {retry + 1} başarısız, tekrar deneniyor...")
                            await asyncio.sleep(3)
                            continue
                        else:
                            logger.error(f"Playlist indirme hatası: {stderr}")
                            await update.message.reply_text("❌ Playlist indirme başarısız")
                            return
                
                except Exception as e:
                    logger.error(f"İndirme hatası: {str(e)}")
                    if retry < max_retries - 1:
                        await update.message.reply_text(f"⚠️ Bağlantı hatası, tekrar deneniyor... ({retry + 1}/{max_retries})")
                        await asyncio.sleep(3)
                        continue
                    else:
                        await update.message.reply_text("❌ Maksimum deneme sayısına ulaşıldı, indirme başarısız")
                        return
            
        elif 'album' in url:
            album_match = re.search(r'album/(\d+)', url)
            if not album_match:
                await update.message.reply_text("❌ Geçerli bir Tidal albüm linki gönderin")
                return
            album_id = album_match.group(1)
            await update.message.reply_text("⬇️ Albüm indiriliyor...")
            
            # tidal-dl komutunu çalıştır
            process = subprocess.Popen(
                ["tidal-dl", "-l", f"https://tidal.com/browse/album/{album_id}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',
                errors='ignore'
            )
            
            # Çıktıyı gerçek zamanlı olarak kontrol et
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    logger.info(output.strip())
                    if "ERROR" in output or "Error" in output:
                        await update.message.reply_text(f"❌ Hata: {output.strip()}")
            
            # İşlem tamamlandı, çıktıyı kontrol et
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Albüm indirme hatası: {stderr}")
                await update.message.reply_text("❌ Albüm indirme başarısız")
                return
            
            # İndirme sonrası biraz bekle
            await asyncio.sleep(5)
            
            # İndirilen dosyaları bul ve gönder
            new_files = await find_music_file(download_path)
            
            if new_files:
                for file_path in new_files:
                    try:
                        # Dosya bilgilerini al
                        file_name = os.path.basename(file_path)
                        path_parts = file_path.split(os.sep)
                        artist = path_parts[-2].split('[')[0].strip() if len(path_parts) > 2 else "Bilinmeyen Sanatçı"
                        
                        # Dosyayı Telegram'a gönder
                        with open(file_path, 'rb') as audio_file:
                            await context.bot.send_audio(
                                chat_id=chat_id,
                                audio=audio_file,
                                title=os.path.splitext(file_name)[0],
                                performer=artist,
                                caption=f"🎵 {file_name}\n👤 {artist}"
                            )
                    except Exception as e:
                        logger.error(f"Dosya gönderme hatası: {str(e)}")
                        continue
                
                await update.message.reply_text("✅ Albüm gönderme tamamlandı!")
                clean_downloads()
            else:
                await update.message.reply_text("❌ İndirme başarısız")
                clean_downloads()
            
        else:
            track_match = re.search(r'track/(\d+)', url)
            if not track_match:
                await update.message.reply_text("❌ Geçerli bir Tidal linki gönderin")
                return
            track_id = track_match.group(1)
            await update.message.reply_text("⬇️ Şarkı indiriliyor...")
            
            # tidal-dl komutunu çalıştır
            process = subprocess.Popen(
                ["tidal-dl", "-l", f"https://tidal.com/browse/track/{track_id}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',
                errors='ignore'
            )
            
            # Çıktıyı gerçek zamanlı olarak kontrol et
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    logger.info(output.strip())
                    if "ERROR" in output or "Error" in output:
                        await update.message.reply_text(f"❌ Hata: {output.strip()}")
            
            # İşlem tamamlandı, çıktıyı kontrol et
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Şarkı indirme hatası: {stderr}")
                await update.message.reply_text("❌ Şarkı indirme başarısız")
                return
            
            # İndirme sonrası biraz bekle
            await asyncio.sleep(5)
            
            # İndirilen dosyaları bul ve gönder
            new_files = await find_music_file(download_path)
            
            if new_files:
                for file_path in new_files:
                    try:
                        # Dosya bilgilerini al
                        file_name = os.path.basename(file_path)
                        path_parts = file_path.split(os.sep)
                        artist = path_parts[-2].split('[')[0].strip() if len(path_parts) > 2 else "Bilinmeyen Sanatçı"
                        
                        # Dosyayı Telegram'a gönder
                        with open(file_path, 'rb') as audio_file:
                            await context.bot.send_audio(
                                chat_id=chat_id,
                                audio=audio_file,
                                title=os.path.splitext(file_name)[0],
                                performer=artist,
                                caption=f"🎵 {file_name}\n👤 {artist}"
                            )
                    except Exception as e:
                        logger.error(f"Dosya gönderme hatası: {str(e)}")
                        continue
                
                await update.message.reply_text("✅ Şarkı gönderme tamamlandı!")
                clean_downloads()
            else:
                await update.message.reply_text("❌ İndirme başarısız")
                clean_downloads()
            
    except Exception as e:
        logger.error(f"Hata: {str(e)}")
        await update.message.reply_text("❌ İşlem başarısız")
        clean_downloads()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"Yeni kullanıcı başladı: {user.first_name} (ID: {user.id})")
    await update.message.reply_text(
        "Merhaba! Müzik indirmek için:\n\n"
        "1. Tidal şarkı linki gönderin\n"
        "2. Tidal playlist linki gönderin\n"
        "3. Tidal albüm linki gönderin\n\n"
        "Kalite ayarı için:\n"
        "/quality normal - AAC 320kbps\n"
        "/quality high - MP3 320kbps\n"
        "/quality hifi - FLAC\n"
        "/quality master - Master"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hata yönetimi"""
    try:
        logger.error(f"Hata oluştu: {context.error}")
        if update and update.message:
            await update.message.reply_text("Bir hata oluştu. Lütfen geçerli bir Tidal linki gönderdiğinizden emin olun.")
    except Exception as e:
        logger.error(f"Hata işlenirken yeni hata oluştu: {str(e)}")

async def set_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kalite ayarını değiştir"""
    user_id = update.effective_user.id
    
    if not context.args or context.args[0].lower() not in QUALITY_OPTIONS:
        await update.message.reply_text(
            "Lütfen kalite seçin:\n\n"
            "/quality normal - AAC 320kbps\n"
            "/quality high - MP3 320kbps\n"
            "/quality hifi - FLAC\n"
            "/quality master - Master"
        )
        return
    
    quality = context.args[0].lower()
    quality_value = QUALITY_OPTIONS[quality]  # Direkt olarak doğru formatta al
    user_quality[user_id] = quality_value
    
    # Config dosyasını güncelle
    config_dir = os.path.join(os.getcwd(), "default")
    config_file = os.path.join(config_dir, '.tidal-dl.json')
    home_config = os.path.expanduser('~/.tidal-dl.json')
    
    try:
        # Önce botun klasöründeki config'i güncelle
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        config['audioQuality'] = quality_value
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
            
        # Ana dizindeki config'i de güncelle
        if os.path.exists(home_config):
            with open(home_config, 'w') as f:
                json.dump(config, f, indent=4)
        
        await update.message.reply_text(
            f"✅ Kalite ayarı güncellendi: {quality.upper()}\n"
            f"Yeni kalite: {quality_value}"
        )
        
    except Exception as e:
        logger.error(f"Kalite ayarı güncelleme hatası: {str(e)}")
        await update.message.reply_text("❌ Kalite ayarı güncellenirken hata oluştu")

def main():
    logger.info("Bot başlatılıyor...")
    
    # GitHub'dan güncelle
    update_from_github()
    
    # Tidal yapılandırmasını ayarla
    setup_tidal()
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("quality", set_quality))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_music))
    application.add_error_handler(error_handler)
    
    logger.info("Bot hazır, çalışmaya başlıyor...")
    application.run_polling()

if __name__ == '__main__':
    main() 