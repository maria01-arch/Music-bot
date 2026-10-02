import os
import sys
import asyncio
import logging
import warnings
import requests

# Suppress harmless pydub ffmpeg warning
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict
from shazamio import Shazam
import yt_dlp

BOT_TOKEN = "8979038991:AAG9p9kDMsbOVfO61nKWTOaMInrE_wIYzkQ"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🎧 Search Tips", callback_data="btn_help"),
            InlineKeyboardButton("🔥 Trending", callback_data="btn_info")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "✨ **Welcome to Music Identifier & Downloader!** ✨\n\n"
        "Send or forward me:\n"
        "• 🎵 Song / Artist Name\n"
        "• 🎙️ Voice Note or Audio File\n"
        "• 🎥 Video Clip",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def download_audio_yt(query: str, output_path: str) -> bool:
    mp3_path = f"{output_path}.mp3"

    # STRATEGY 1: Public Cobalt API (Bypasses Datacenter IP Blocks)
    try:
        ydl_meta_opts = {
            'default_search': 'ytsearch1:',
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
        }
        
        video_url = None
        with yt_dlp.YoutubeDL(ydl_meta_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if info and 'entries' in info and len(info['entries']) > 0:
                video_url = info['entries'][0].get('webpage_url')
            elif info and 'webpage_url' in info:
                video_url = info['webpage_url']

        if video_url:
            cobalt_payload = {
                "url": video_url,
                "downloadMode": "audio",
                "audioFormat": "mp3"
            }
            cobalt_headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            cobalt_response = requests.post("https://api.cobalt.tools/", json=cobalt_payload, headers=cobalt_headers, timeout=15)
            
            if cobalt_response.status_code == 200:
                data = cobalt_response.json()
                media_link = data.get("url")
                
                if media_link:
                    audio_res = requests.get(media_link, stream=True, timeout=30)
                    if audio_res.status_code == 200:
                        with open(mp3_path, 'wb') as f:
                            for chunk in audio_res.iter_content(chunk_size=8192):
                                f.write(chunk)
                        if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                            return True
    except Exception as e:
        print(f"Cobalt API extraction failed: {e}")

    # STRATEGY 2: yt-dlp direct fallback with Android client spoofing
    fallback_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f"{output_path}.%(ext)s",
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'ignoreerrors': True,
        'default_search': 'ytsearch1:',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
            }
        },
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        with yt_dlp.YoutubeDL(fallback_opts) as ydl:
            ydl.extract_info(query, download=True)
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                return True
    except Exception as e:
        print(f"yt-dlp fallback failed: {e}")

    return False

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    audio = msg.audio or msg.voice or msg.video
    if not audio:
        return

    status_msg = await msg.reply_text("🎧 *Identifying audio with Shazam...*", parse_mode='Markdown')

    file = await context.bot.get_file(audio.file_id)
    temp_input = f"temp_{audio.file_id}.ogg"
    await file.download_to_drive(temp_input)

    shazam = Shazam()
    out = await shazam.recognize(temp_input)

    if os.path.exists(temp_input):
        os.remove(temp_input)

    track = out.get('track')
    if track:
        title = track.get('title', 'Unknown')
        subtitle = track.get('subtitle', 'Unknown')
        search_query = f"{title} {subtitle}"
        await process_and_send_audio(status_msg, search_query)
    else:
        await status_msg.edit_text("❌ *Could not recognize audio.*", parse_mode='Markdown')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    search_query = update.message.text
    status_msg = await update.message.reply_text(f"🔍 *Searching for:* `{search_query}`...", parse_mode='Markdown')
    await process_and_send_audio(status_msg, search_query)

async def process_and_send_audio(status_msg, search_query: str):
    await status_msg.edit_text(f"🎵 *Found:* `{search_query}`\n📥 *Downloading audio...*", parse_mode='Markdown')
    
    output_filename = f"download_{status_msg.message_id}"
    mp3_filepath = f"{output_filename}.mp3"

    success = await asyncio.to_thread(download_audio_yt, search_query, output_filename)

    if success and os.path.exists(mp3_filepath):
        await status_msg.edit_text("📤 *Uploading track...*", parse_mode='Markdown')
        
        keyboard = [
            [InlineKeyboardButton("🔄 Search Another", callback_data="btn_again")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        with open(mp3_filepath, 'rb') as audio_file:
            await status_msg.reply_audio(
                audio=audio_file,
                title=search_query,
                caption=f"🎶 **Track:** {search_query}",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        await status_msg.delete()
        os.remove(mp3_filepath)
    else:
        await status_msg.edit_text("❌ Failed to download track from server.", parse_mode='Markdown')

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "btn_help":
        await query.message.reply_text("💡 Send a voice message or type a song title to search.")
    elif query.data == "btn_info":
        await query.message.reply_text("🔥 Fast audio identification and high-quality MP3 downloads.")
    elif query.data == "btn_again":
        await query.message.reply_text("🎵 Send another title or audio file!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, Conflict):
        logging.warning("Temporary conflict error caught during deployment rebuild.")
        return
    logging.error("Exception occurred:", exc_info=context.error)

if __name__ == '__main__':
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        raise ValueError("Please replace YOUR_TELEGRAM_BOT_TOKEN_HERE with your actual bot token!")
        
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.VIDEO, handle_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_error_handler(error_handler)
    
    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

