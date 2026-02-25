# ©️ LISA-KOREA | @LISA_FAN_LK | NT_BOT_CHANNEL

import logging
import asyncio
import json
import os
import shutil
import time
import signal
from datetime import datetime
from pyrogram import enums
from pyrogram.types import InputMediaPhoto
from plugins.config import Config
from plugins.script import Translation
from plugins.thumbnail import *
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes
from plugins.database.database import db
from PIL import Image
from plugins.functions.ran_text import random_char
from plugins.functions.unzip import handle_auto_unzip, is_zip_file, fix_unknown_video_extension
cookies_file = 'cookies.txt'
# Set up logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# Global dictionary to track active yt-dlp processes for cancellation
active_ytdlp_processes = {}


async def youtube_dl_call_back(bot, update):
    cb_data = update.data
    tg_send_type, youtube_dl_format, youtube_dl_ext, ranom = cb_data.split("|")
    random1 = random_char(5)

    save_ytdl_json_path = os.path.join(Config.DOWNLOAD_LOCATION, f"{update.from_user.id}{ranom}.json")

    try:
        with open(save_ytdl_json_path, "r", encoding="utf8") as f:
            response_json = json.load(f)
    except FileNotFoundError as e:
        logger.error(f"JSON file not found: {e}")
        await update.message.delete()
        return False

    youtube_dl_url = update.message.reply_to_message.text
    custom_file_name = f"{response_json.get('title')}_{youtube_dl_format}.{youtube_dl_ext}"
    youtube_dl_username = None
    youtube_dl_password = None

    if "|" in youtube_dl_url:
        url_parts = youtube_dl_url.split("|")
        if len(url_parts) == 2:
            youtube_dl_url, custom_file_name = url_parts
        elif len(url_parts) == 4:
            youtube_dl_url, custom_file_name, youtube_dl_username, youtube_dl_password = url_parts
        else:
            for entity in update.message.reply_to_message.entities:
                if entity.type == "text_link":
                    youtube_dl_url = entity.url
                elif entity.type == "url":
                    o = entity.offset
                    l = entity.length
                    youtube_dl_url = youtube_dl_url[o:o + l]

        youtube_dl_url = youtube_dl_url.strip()
        custom_file_name = custom_file_name.strip()
        if youtube_dl_username:
            youtube_dl_username = youtube_dl_username.strip()
        if youtube_dl_password:
            youtube_dl_password = youtube_dl_password.strip()

        logger.info(youtube_dl_url)
        logger.info(custom_file_name)
    else:
        for entity in update.message.reply_to_message.entities:
            if entity.type == "text_link":
                youtube_dl_url = entity.url
            elif entity.type == "url":
                o = entity.offset
                l = entity.length
                youtube_dl_url = youtube_dl_url[o:o + l]

    # Generate cancel ID
    cancel_id = f"{update.from_user.id}_{int(time.time())}_ytdl"

    # Add cancel button
    cancel_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Download", callback_data=f"cancel_ytdl_{cancel_id}")]
    ])

    await update.message.edit_caption(
        caption=Translation.DOWNLOAD_START.format(custom_file_name),
        reply_markup=cancel_markup
    )

    description = Translation.CUSTOM_CAPTION_UL_FILE
    if "fulltitle" in response_json:
        description = response_json["fulltitle"][0:1021]
    # Fallback to empty string if None (caption will be handled during upload)
    if not description:
        description = ""

    tmp_directory_for_each_user = os.path.join(Config.DOWNLOAD_LOCATION, f"{update.from_user.id}{random1}")
    os.makedirs(tmp_directory_for_each_user, exist_ok=True)
    download_directory = os.path.join(tmp_directory_for_each_user, custom_file_name)

    command_to_exec = [
        "yt-dlp",
        "-c",
        "--max-filesize", str(Config.TG_MAX_FILE_SIZE),
        "--embed-subs",
        "-f", f"{youtube_dl_format}bestvideo+bestaudio/best",
        "--hls-prefer-ffmpeg",
        "--cookies", cookies_file,
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        youtube_dl_url,
        "-o", download_directory
    ]

    if tg_send_type == "audio":
        command_to_exec = [
            "yt-dlp",
            "-c",
            "--max-filesize", str(Config.TG_MAX_FILE_SIZE),
            "--bidi-workaround",
            "--extract-audio",
            "--cookies", cookies_file,
            "--audio-format", youtube_dl_ext,
            "--audio-quality", youtube_dl_format,
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            youtube_dl_url,
            "-o", download_directory
        ]

    if Config.HTTP_PROXY:
        command_to_exec.extend(["--proxy", Config.HTTP_PROXY])
    if youtube_dl_username:
        command_to_exec.extend(["--username", youtube_dl_username])
    if youtube_dl_password:
        command_to_exec.extend(["--password", youtube_dl_password])

    command_to_exec.append("--no-warnings")

    logger.info(command_to_exec)
    start = datetime.now()

    # Create subprocess
    process = await asyncio.create_subprocess_exec(
        *command_to_exec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Register process for cancellation
    active_ytdlp_processes[cancel_id] = {"process": process, "cancelled": False}

    stdout, stderr = await process.communicate()
    e_response = stderr.decode().strip()
    t_response = stdout.decode().strip()
    logger.info(e_response)
    logger.info(t_response)

    # Check if cancelled
    if cancel_id in active_ytdlp_processes and active_ytdlp_processes[cancel_id].get("cancelled"):
        await update.message.edit_caption(
            caption="❌ Download Cancelled",
            reply_markup=None
        )
        # Clean up
        try:
            if os.path.exists(tmp_directory_for_each_user):
                shutil.rmtree(tmp_directory_for_each_user)
        except:
            pass
        if cancel_id in active_ytdlp_processes:
            del active_ytdlp_processes[cancel_id]
        return False

    # Remove from active processes
    if cancel_id in active_ytdlp_processes:
        del active_ytdlp_processes[cancel_id]

    if process.returncode != 0:
        logger.error(f"yt-dlp command failed with return code {process.returncode}")
        await update.message.edit_caption(
            caption=f"Error: {e_response}"
        )
        return False

    ad_string_to_replace = "**Invalid link !**"
    if e_response and ad_string_to_replace in e_response:
        error_message = e_response.replace(ad_string_to_replace, "")
        await update.message.edit_caption(
            text=error_message
        )
        return False

    if t_response:
        logger.info(t_response)
        try:
            os.remove(save_ytdl_json_path)
        except FileNotFoundError:
            pass

        end_one = datetime.now()
        time_taken_for_download = (end_one - start).seconds

        if os.path.isfile(download_directory):
            file_size = os.stat(download_directory).st_size
        else:
            # Check for _0.unknown_video file
            unknown_video_path = os.path.splitext(download_directory)[0] + "_0.unknown_video"
            mkv_path = os.path.splitext(download_directory)[0] + ".mkv"

            if os.path.isfile(unknown_video_path):
                # Rename to .mkv
                try:
                    os.rename(unknown_video_path, mkv_path)
                    download_directory = mkv_path
                    custom_file_name = os.path.basename(mkv_path)
                    file_size = os.stat(download_directory).st_size
                except Exception as e:
                    logger.error(f"Error renaming file: {e}")
                    download_directory = os.path.splitext(download_directory)[0] + ".mkv"
                    if os.path.isfile(download_directory):
                        file_size = os.stat(download_directory).st_size
                    else:
                        logger.error(f"Downloaded file not found: {download_directory}")
                        await update.message.edit_caption(
                            caption=Translation.DOWNLOAD_FAILED
                        )
                        return False
            elif os.path.isfile(mkv_path):
                download_directory = mkv_path
                custom_file_name = os.path.basename(mkv_path)
                file_size = os.stat(download_directory).st_size
            else:
                logger.error(f"Downloaded file not found: {download_directory}")
                await update.message.edit_caption(
                    caption=Translation.DOWNLOAD_FAILED
                )
                return False

        # Fix _0.unknown_video extension if still present
        download_directory = fix_unknown_video_extension(download_directory)
        custom_file_name = os.path.basename(download_directory)

        if file_size > Config.TG_MAX_FILE_SIZE:
            await update.message.edit_caption(
                caption=Translation.RCHD_TG_API_LIMIT.format(time_taken_for_download, humanbytes(file_size))
            )
        else:
            # Check for auto unzip first
            auto_unzip_done = await handle_auto_unzip(
                bot, 
                update, 
                download_directory, 
                tmp_directory_for_each_user, 
                time.time()
            )

            if auto_unzip_done:
                # Auto unzip was performed and files were uploaded
                return True

            # Add cancel button for upload
            upload_cancel_id = f"{update.from_user.id}_{int(time.time())}_ytdl_upload"
            upload_cancel_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel Upload", callback_data=f"cancel_ul_{upload_cancel_id}")]
            ])

            await update.message.edit_caption(
                caption=Translation.UPLOAD_START.format(custom_file_name),
                reply_markup=upload_cancel_markup
            )

            # Import active downloads from dl_button
            from plugins.dl_button import active_downloads
            active_downloads[upload_cancel_id] = {"cancelled": False}

            start_time = time.time()
            upload_cancelled = False

            # Determine caption: auto_caption uses filename with underscores removed
            auto_caption_enabled = await db.get_auto_caption(update.from_user.id)
            if auto_caption_enabled:
                upload_caption = custom_file_name.replace("_", " ")
            else:
                upload_caption = description if description else custom_file_name

            try:
                if not await db.get_upload_as_doc(update.from_user.id):
                    thumbnail = await Gthumb01(bot, update)
                    await update.message.reply_document(
                        document=download_directory,
                        file_name=custom_file_name,
                        thumb=thumbnail,
                        caption=upload_caption,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            Translation.UPLOAD_START,
                            update.message,
                            start_time
                        )
                    )
                else:
                    width, height, duration = await Mdata01(download_directory)
                    thumb_image_path = await Gthumb02(bot, update, duration, download_directory)
                    await update.message.reply_video(
                        video=download_directory,
                        file_name=custom_file_name,
                        caption=upload_caption,
                        duration=duration,
                        width=width,
                        height=height,
                        supports_streaming=True,
                        thumb=thumb_image_path,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            Translation.UPLOAD_START,
                            update.message,
                            start_time
                        )
                    )

                if tg_send_type == "audio":
                    duration = await Mdata03(download_directory)
                    thumbnail = await Gthumb01(bot, update)
                    await update.message.reply_audio(
                        audio=download_directory,
                        file_name=custom_file_name,
                        caption=upload_caption,
                        duration=duration,
                        thumb=thumbnail,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            Translation.UPLOAD_START,
                            update.message,
                            start_time
                        )
                    )
                elif tg_send_type == "vm":
                    width, duration = await Mdata02(download_directory)
                    thumbnail = await Gthumb02(bot, update, duration, download_directory)
                    await update.message.reply_video_note(
                        video_note=download_directory,
                        duration=duration,
                        length=width,
                        thumb=thumbnail,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            Translation.UPLOAD_START,
                            update.message,
                            start_time
                        )
                    )
                else:
                    logger.info("✅ " + custom_file_name)

            except Exception as e:
                logger.error(f"Upload error: {e}")
                upload_cancelled = True

            end_two = datetime.now()

            # Check if upload was cancelled
            if upload_cancel_id in active_downloads and active_downloads[upload_cancel_id].get("cancelled"):
                upload_cancelled = True

            if upload_cancel_id in active_downloads:
                del active_downloads[upload_cancel_id]

            if upload_cancelled:
                await update.message.edit_caption(
                    caption="❌ Upload Cancelled",
                    reply_markup=None
                )
            else:
                time_taken_for_upload = (end_two - end_one).seconds
                await update.message.edit_caption(
                    caption=Translation.AFTER_SUCCESSFUL_UPLOAD_MSG_WITH_TS.format(time_taken_for_download, time_taken_for_upload)
                )

                logger.info(f"✅ Downloaded in: {time_taken_for_download} seconds")
                logger.info(f"✅ Uploaded in: {time_taken_for_upload} seconds")

            # Cleanup
            try:
                shutil.rmtree(tmp_directory_for_each_user)
                if os.path.exists(thumbnail):
                    os.remove(thumbnail)
            except Exception as e:
                logger.error(f"Error cleaning up: {e}")


async def handle_ytdl_cancel(bot, update, cancel_id):
    """Handle cancel for yt-dlp downloads"""
    if cancel_id in active_ytdlp_processes:
        active_ytdlp_processes[cancel_id]["cancelled"] = True
        process = active_ytdlp_processes[cancel_id]["process"]
        try:
            process.terminate()
            await asyncio.sleep(1)
            if process.returncode is None:
                process.kill()
        except:
            pass
        await update.answer("Cancelling download...", show_alert=False)
    else:
        await update.answer("Download not found or already completed", show_alert=True)
