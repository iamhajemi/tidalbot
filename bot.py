from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import os
import subprocess
import re
import asyncio
import shutil
import json
import logging
import requests
from datetime import datetime

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

# Kullanıcı istatistikleri için sözlük
user_stats = {}

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
            if not os.path.exists(download_path):
                logger.error(f"İndirme klasörü bulunamadı: {download_path}")
                return []
                
            artist_folders = [d for d in os.listdir(download_path) 
                            if os.path.isdir(os.path.join(download_path, d))]
            
            logger.info(f"Bulunan sanatçı klasörleri: {artist_folders}")
            
            # Tüm klasörlerde müzik dosyalarını ara
            for root, dirs, files in os.walk(download_path):
                for file in files:
                    if file.endswith(('.m4a', '.mp3', '.flac')):
                        full_path = os.path.join(root, file)
                        found_files.append(full_path)
                        logger.info(f"Müzik dosyası bulundu: {full_path}")
            
            # Eğer dosya bulunduysa
            if found_files:
                logger.info(f"Toplam {len(found_files)} müzik dosyası bulundu")
                return found_files
            
        except Exception as e:
            logger.error(f"Klasör okuma hatası: {str(e)}")
        
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

def get_quality_keyboard():
    """Kalite seçenekleri için buton menüsü oluştur"""
    keyboard = [
        [
            InlineKeyboardButton("Normal (AAC 320)", callback_data="quality_normal"),
            InlineKeyboardButton("High (MP3 320)", callback_data="quality_high")
        ],
        [
            InlineKeyboardButton("HiFi (FLAC)", callback_data="quality_hifi"),
            InlineKeyboardButton("Master", callback_data="quality_master")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"Yeni kullanıcı başladı: {user.first_name} (ID: {user.id})")
    await update.message.reply_text(
        "Merhaba! Müzik indirmek için:\n\n"
        "1. Tidal şarkı linki gönderin\n"
        "2. Tidal playlist linki gönderin\n"
        "3. Tidal albüm linki gönderin\n\n"
        "📊 Kalite seçmek için aşağıdaki butonları kullanın:",
        reply_markup=get_quality_keyboard()
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
    # Buton tıklaması mı normal komut mu kontrol et
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        message = update.callback_query.message
    else:
        user_id = update.effective_user.id
        message = update.message
    
    if not context.args or context.args[0].lower() not in QUALITY_OPTIONS:
        await message.reply_text(
            "Lütfen kalite seçin:",
            reply_markup=get_quality_keyboard()
        )
        return
    
    quality = context.args[0].lower()
    quality_value = QUALITY_OPTIONS[quality]
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
        
        # Mesajı güncelle veya yeni mesaj gönder
        response_text = f"✅ Kalite ayarı güncellendi: {quality.upper()}\nYeni kalite: {quality_value}"
        if update.callback_query:
            await message.edit_text(response_text, reply_markup=get_quality_keyboard())
        else:
            await message.reply_text(response_text, reply_markup=get_quality_keyboard())
        
    except Exception as e:
        logger.error(f"Kalite ayarı güncelleme hatası: {str(e)}")
        error_text = "❌ Kalite ayarı güncellenirken hata oluştu"
        if update.callback_query:
            await message.edit_text(error_text, reply_markup=get_quality_keyboard())
        else:
            await message.reply_text(error_text, reply_markup=get_quality_keyboard())

async def download_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.message.chat_id
    user = update.effective_user
    user_id = user.id
    
    logger.info(f"İstek alındı: {url} (Kullanıcı: {user.first_name}, ID: {user_id})")
    
    # İndirme klasörünü tanımla
    download_path = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_path, exist_ok=True)
    
    # İndirme klasörünü temizle
    clean_downloads()
    
    # Tidal URL kontrolü
    if not 'tidal.com' in url:
        await update.message.reply_text(
            "❌ Geçerli bir Tidal linki gönderin",
            reply_markup=get_quality_keyboard()
        )
        return
    
    try:
        # URL tipini kontrol et
        if 'playlist' in url:
            # Playlist indirme işlemi
            await process_playlist(update, context, url, user_id)
        elif 'album' in url:
            # Albüm indirme işlemi
            await process_album(update, context, url, user_id)
        else:
            # Tekli şarkı indirme işlemi
            await process_track(update, context, url, user_id)
            
    except Exception as e:
        logger.error(f"Hata: {str(e)}")
        await update.message.reply_text("❌ İşlem başarısız")
        clean_downloads()

async def process_playlist(update, context, url, user_id):
    """Playlist indirme işlemi"""
    playlist_match = re.search(r'playlist/([a-zA-Z0-9-]+)', url)
    if not playlist_match:
        await update.message.reply_text("❌ Geçerli bir Tidal playlist linki gönderin")
        return
        
    await update.message.reply_text(
        "🔍 Playlist indiriliyor...",
        reply_markup=get_quality_keyboard()
    )
    
    # İndirme işlemi başarılı olursa istatistikleri güncelle
    update_user_stats(user_id, "playlist")
    
    # ... (playlist indirme kodunun geri kalanı aynı kalacak)

async def process_album(update, context, url, user_id):
    """Albüm indirme işlemi"""
    album_match = re.search(r'album/(\d+)', url)
    if not album_match:
        await update.message.reply_text("❌ Geçerli bir Tidal albüm linki gönderin")
        return
        
    await update.message.reply_text(
        "⬇️ Albüm indiriliyor...",
        reply_markup=get_quality_keyboard()
    )
    
    # İndirme işlemi başarılı olursa istatistikleri güncelle
    update_user_stats(user_id, "album")
    
    # ... (albüm indirme kodunun geri kalanı aynı kalacak)

async def process_track(update, context, url, user_id):
    """Tekli şarkı indirme işlemi"""
    track_match = re.search(r'track/(\d+)', url)
    if not track_match:
        await update.message.reply_text("❌ Geçerli bir Tidal linki gönderin")
        return
        
    await update.message.reply_text(
        "⬇️ Şarkı indiriliyor...",
        reply_markup=get_quality_keyboard()
    )
    
    # İndirme işlemi başarılı olursa istatistikleri güncelle
    update_user_stats(user_id, "track")
    
    # ... (şarkı indirme kodunun geri kalanı aynı kalacak)

async def quality_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buton tıklamalarını işle"""
    query = update.callback_query
    await query.answer()  # Butona tıklandığını bildir
    
    # Seçilen kaliteyi al
    quality = query.data.split('_')[1]  # quality_normal -> normal
    
    # /quality komutunu çalıştır
    context.args = [quality]
    await set_quality(update, context)

async def search_tidal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tidal'da arama yap"""
    if not context.args:
        await update.message.reply_text("❌ Arama yapmak için bir şeyler yazın.\nÖrnek: /ara şarkı adı")
        return
        
    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Arıyorum: {query}")
    
    try:
        # tidal-dl ile arama yap
        process = subprocess.Popen(
            ["tidal-dl", "-s", query],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            errors='ignore'
        )
        
        # Sonuçları topla
        results = []
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                output = output.strip()
                if "http" in output.lower():  # Link içeren satırları al
                    results.append(output)
        
        # Sonuçları göster
        if results:
            response = "🎵 Arama Sonuçları:\n\n"
            for i, result in enumerate(results[:5], 1):  # İlk 5 sonucu göster
                response += f"{i}. {result}\n\n"
            response += "\nİndirmek istediğiniz şarkının linkini gönderin."
        else:
            response = "❌ Sonuç bulunamadı."
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Arama hatası: {str(e)}")
        await update.message.reply_text("❌ Arama sırasında bir hata oluştu.")

def update_user_stats(user_id, download_type):
    """Kullanıcı istatistiklerini güncelle"""
    if user_id not in user_stats:
        user_stats[user_id] = {
            "track": 0,
            "album": 0,
            "playlist": 0,
            "total_downloads": 0,
            "last_download": None
        }
    
    user_stats[user_id][download_type] += 1
    user_stats[user_id]["total_downloads"] += 1
    user_stats[user_id]["last_download"] = datetime.now()

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """İstatistikleri göster"""
    user_id = update.effective_user.id
    
    if user_id not in user_stats:
        await update.message.reply_text("📊 Henüz indirme yapmadınız.")
        return
    
    stats = user_stats[user_id]
    last_download = stats["last_download"].strftime("%d.%m.%Y %H:%M") if stats["last_download"] else "Yok"
    
    response = (
        "📊 İndirme İstatistikleriniz:\n\n"
        f"🎵 Tekli Şarkı: {stats['track']}\n"
        f"💿 Albüm: {stats['album']}\n"
        f"📑 Playlist: {stats['playlist']}\n"
        f"📈 Toplam: {stats['total_downloads']}\n"
        f"⏱ Son İndirme: {last_download}"
    )
    
    await update.message.reply_text(response)

def main():
    logger.info("Bot başlatılıyor...")
    
    # GitHub'dan güncelle
    update_from_github()
    
    # Tidal yapılandırmasını ayarla
    setup_tidal()
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("quality", set_quality))
    application.add_handler(CommandHandler("ara", search_tidal))
    application.add_handler(CommandHandler("stats", show_stats))  # İstatistik komutu eklendi
    application.add_handler(CallbackQueryHandler(quality_button, pattern="^quality_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_music))
    application.add_error_handler(error_handler)
    
    logger.info("Bot hazır, çalışmaya başlıyor...")
    application.run_polling()

if __name__ == '__main__':
    main() 