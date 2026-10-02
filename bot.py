import os
import sys
import asyncio
import logging
import warnings

# Suppress harmless pydub ffmpeg warning
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict
from shazamio import Shazam
import yt_dlp

# Replace this string with your actual bot token from BotFather
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
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f"{output_path}.%(ext)s",
        'quiet': False,
        'no_warnings': True,
        'default_search': 'ytsearch1:',
        'noplaylist': True,
        # Force yt-dlp to use YouTube Android/iOS client APIs to bypass cloud IP bot checks
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Android 14; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0'
        },
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([query])
        return True
    except Exception as e:
        print(f"yt-dlp download exception: {e}")
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
        search_query = f"{title} - {subtitle}"
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
    
    print("samzyslib bot is running...")
    app.run_polling(drop_pending_updates=True)

