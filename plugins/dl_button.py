# @Shrimadhav Uk | @LISA_FAN_LK

import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
import asyncio
import aiohttp
import json
import math
import os
import shutil
import time
import re
from datetime import datetime
from urllib.parse import urlparse, unquote
from plugins.config import Config
from plugins.script import Translation
from plugins.thumbnail import *
from plugins.database.database import db
logging.getLogger("pyrogram").setLevel(logging.WARNING)
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes, TimeFormatter
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image
from pyrogram import enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.functions.unzip import handle_auto_unzip, is_zip_file, fix_unknown_video_extension

# Global dictionary to track active downloads for cancellation
active_downloads = {}


async def get_real_filename_from_url(session, url):
    """
    Get the real filename from URL by checking Content-Disposition header.
    Falls back to URL basename if no Content-Disposition header is found.
    """
    try:
        async with session.head(url, allow_redirects=True, timeout=30) as response:
            # Check Content-Disposition header for filename
            content_disposition = response.headers.get('Content-Disposition', '')
            if content_disposition:
                # Try to extract filename from Content-Disposition
                # Format: attachment; filename="filename.mkv" or attachment; filename*=UTF-8''filename.mkv
                filename_match = re.findall(r"filename[*]?=[\"']?(?:UTF-8'')?([^\"';]+)[\"']?", content_disposition)
                if filename_match:
                    filename = filename_match[-1].strip()
                    # URL decode the filename
                    filename = unquote(filename)
                    # Remove any path components, keep only the filename
                    filename = os.path.basename(filename)
                    if filename:
                        logger.info(f"Found filename from Content-Disposition: {filename}")
                        return filename

            # Fallback: try to get filename from URL
            parsed_url = urlparse(response.url)
            url_filename = os.path.basename(unquote(parsed_url.path))
            if url_filename and '.' in url_filename:
                logger.info(f"Using filename from URL: {url_filename}")
                return url_filename

    except Exception as e:
        logger.warning(f"Error getting filename from headers: {e}")

    # Final fallback: use URL basename
    parsed_url = urlparse(url)
    return os.path.basename(unquote(parsed_url.path)) or "unknown_file"


async def ddl_call_back(bot, update):
    logger.info(update)
    cb_data = update.data
    # youtube_dl extractors
    tg_send_type, youtube_dl_format, youtube_dl_ext = cb_data.split("=")
    thumb_image_path = Config.DOWNLOAD_LOCATION + "/" + str(update.from_user.id) + ".jpg"
    youtube_dl_url = update.message.reply_to_message.text

    # Extract URL properly
    if "|" in youtube_dl_url:
        url_parts = youtube_dl_url.split("|")
        if len(url_parts) == 2:
            youtube_dl_url = url_parts[0].strip()
        else:
            for entity in update.message.reply_to_message.entities:
                if entity.type == "text_link":
                    youtube_dl_url = entity.url
                elif entity.type == "url":
                    o = entity.offset
                    l = entity.length
                    youtube_dl_url = youtube_dl_url[o:o + l]
    else:
        for entity in update.message.reply_to_message.entities:
            if entity.type == "text_link":
                youtube_dl_url = entity.url
            elif entity.type == "url":
                o = entity.offset
                l = entity.length
                youtube_dl_url = youtube_dl_url[o:o + l]

    # Get the real filename from URL headers
    async with aiohttp.ClientSession() as session:
        custom_file_name = await get_real_filename_from_url(session, youtube_dl_url)

    # Check if user provided custom name via URL format "url | custom_name"
    original_text = update.message.reply_to_message.text
    if "|" in original_text:
        url_parts = original_text.split("|")
        if len(url_parts) == 2:
            custom_file_name = url_parts[1].strip()

    description = Translation.CUSTOM_CAPTION_UL_FILE
    # Fallback to empty string if None (caption will be handled during upload)
    if not description:
        description = ""
    start = datetime.now()

    # Generate unique cancel ID
    cancel_id = f"{update.from_user.id}_{int(time.time())}"

    # Add cancel button
    cancel_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⛔ Cancel", callback_data=f"cancel_dl_{cancel_id}")]
    ])

    await update.message.edit_caption(
        caption=Translation.DOWNLOAD_START.format(custom_file_name),
        reply_markup=cancel_markup,
        parse_mode=enums.ParseMode.HTML
    )

    tmp_directory_for_each_user = Config.DOWNLOAD_LOCATION + "/" + str(update.from_user.id)
    if not os.path.isdir(tmp_directory_for_each_user):
        os.makedirs(tmp_directory_for_each_user)
    download_directory = tmp_directory_for_each_user + "/" + custom_file_name

    # Register active download for cancellation
    active_downloads[cancel_id] = {"cancelled": False}

    download_success = False
    async with aiohttp.ClientSession() as session:
        c_time = time.time()
        try:
            download_success = await download_coroutine(
                bot,
                session,
                youtube_dl_url,
                download_directory,
                update.message.chat.id,
                update.message.id,
                c_time,
                cancel_id,
                custom_file_name
            )
        except asyncio.TimeoutError:
            await bot.edit_message_text(
                text=Translation.SLOW_URL_DECED,
                chat_id=update.message.chat.id,
                message_id=update.message.id
            )
            if cancel_id in active_downloads:
                del active_downloads[cancel_id]
            return False
        except Exception as e:
            logger.error(f"Download error: {e}")
            if cancel_id in active_downloads:
                del active_downloads[cancel_id]
            return False

    # Check if download was cancelled
    if cancel_id in active_downloads and active_downloads[cancel_id].get("cancelled"):
        await update.message.edit_caption(
            caption="⛔ Download Cancelled",
            reply_markup=None,
            parse_mode=enums.ParseMode.HTML
        )
        # Clean up partial file
        if os.path.exists(download_directory):
            try:
                os.remove(download_directory)
            except:
                pass
        del active_downloads[cancel_id]
        return False

    # Remove from active downloads
    if cancel_id in active_downloads:
        del active_downloads[cancel_id]

    if download_success and os.path.exists(download_directory):
        end_one = datetime.now()

        # Fix _0.unknown_video extension if present
        download_directory = fix_unknown_video_extension(download_directory)
        custom_file_name = os.path.basename(download_directory)

        # Check for auto unzip
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
        upload_cancel_id = f"{update.from_user.id}_{int(time.time())}_upload"
        upload_cancel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⛔ Cancel Upload", callback_data=f"cancel_ul_{upload_cancel_id}")]
        ])

        await update.message.edit_caption(
            caption=Translation.UPLOAD_START,
            reply_markup=upload_cancel_markup,
            parse_mode=enums.ParseMode.HTML
        )

        # Register active upload for cancellation
        active_downloads[upload_cancel_id] = {"cancelled": False}

        file_size = Config.TG_MAX_FILE_SIZE + 1
        try:
            file_size = os.stat(download_directory).st_size
        except FileNotFoundError as exc:
            # Check for _0.unknown_video file
            unknown_video_path = os.path.splitext(download_directory)[0] + "_0.unknown_video"
            mkv_path = os.path.splitext(download_directory)[0] + ".mkv"

            if os.path.isfile(unknown_video_path):
                try:
                    os.rename(unknown_video_path, mkv_path)
                    download_directory = mkv_path
                    custom_file_name = os.path.basename(mkv_path)
                    file_size = os.stat(download_directory).st_size
                except Exception as e:
                    logger.error(f"Error renaming file: {e}")
                    download_directory = os.path.splitext(download_directory)[0] + "." + "mkv"
                    file_size = os.stat(download_directory).st_size
            elif os.path.isfile(mkv_path):
                download_directory = mkv_path
                custom_file_name = os.path.basename(mkv_path)
                file_size = os.stat(download_directory).st_size
            else:
                download_directory = os.path.splitext(download_directory)[0] + "." + "mkv"
                file_size = os.stat(download_directory).st_size

        if file_size > Config.TG_MAX_FILE_SIZE:
            await update.message.edit_caption(
                caption=Translation.RCHD_TG_API_LIMIT,
                reply_markup=None,
                parse_mode=enums.ParseMode.HTML
            )
            if upload_cancel_id in active_downloads:
                del active_downloads[upload_cancel_id]
        else:
            start_time = time.time()
            upload_cancelled = False

            # Determine caption: auto_caption uses filename with underscores removed
            auto_caption_enabled = await db.get_auto_caption(update.from_user.id)
            if auto_caption_enabled:
                upload_caption = custom_file_name.replace("_", " ")
            else:
                upload_caption = description if description else custom_file_name

            try:
                if (await db.get_upload_as_doc(update.from_user.id)) is False:
                    thumbnail = await Gthumb01(bot, update)
                    await update.message.reply_document(
                        document=download_directory,
                        file_name=custom_file_name,
                        thumb=thumbnail,
                        caption=upload_caption,
                        parse_mode=enums.ParseMode.HTML,
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
                        parse_mode=enums.ParseMode.HTML,
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
                        parse_mode=enums.ParseMode.HTML,
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
                    logger.info("Did this happen? :\\")

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
                    caption="⛔ Upload Cancelled",
                    reply_markup=None,
                    parse_mode=enums.ParseMode.HTML
                )
            else:
                time_taken_for_download = (end_one - start).seconds
                time_taken_for_upload = (end_two - end_one).seconds
                await update.message.edit_caption(
                    caption=Translation.AFTER_SUCCESSFUL_UPLOAD_MSG_WITH_TS.format(time_taken_for_download, time_taken_for_upload),
                    reply_markup=None,
                    parse_mode=enums.ParseMode.HTML
                )

            # Cleanup
            try:
                if os.path.exists(download_directory):
                    os.remove(download_directory)
                if os.path.exists(thumb_image_path):
                    os.remove(thumb_image_path)
            except:
                pass
    else:
        await update.message.edit_caption(
            caption=Translation.NO_VOID_FORMAT_FOUND.format("Download Failed"),
            reply_markup=None,
            parse_mode=enums.ParseMode.HTML
        )


async def download_coroutine(bot, session, url, file_name, chat_id, message_id, start, cancel_id, display_file_name):
    downloaded = 0
    display_message = ""

    try:
        async with session.get(url, timeout=Config.PROCESS_MAX_TIMEOUT) as response:
            total_length = int(response.headers.get("Content-Length", 0))
            content_type = response.headers.get("Content-Type", "")

            if "text" in content_type and total_length < 500:
                return await response.release()

            # Update message with cancel button
            cancel_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⛔ Cancel", callback_data=f"cancel_dl_{cancel_id}")]
            ])

            try:
                await bot.edit_message_text(
                    chat_id,
                    message_id,
                    text=f"""📥 Downloading...

File Name: {display_file_name}
File Size: {humanbytes(total_length)}
Progress: 0%""",
                    reply_markup=cancel_markup
                )
            except Exception as e:
                logger.warning(f"Could not update message: {e}")

            with open(file_name, "wb") as f_handle:
                while True:
                    # Check if cancelled
                    if cancel_id in active_downloads and active_downloads[cancel_id].get("cancelled"):
                        return False

                    chunk = await response.content.read(Config.CHUNK_SIZE)
                    if not chunk:
                        break

                    f_handle.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    diff = now - start

                    if round(diff % 5.00) == 0 or downloaded == total_length:
                        percentage = downloaded * 100 / total_length if total_length > 0 else 0
                        speed = downloaded / diff if diff > 0 else 0
                        elapsed_time = round(diff) * 1000
                        time_to_completion = round((total_length - downloaded) / speed) * 1000 if speed > 0 else 0
                        estimated_total_time = elapsed_time + time_to_completion

                        try:
                            current_message = f"""📥 Downloading...

File Name: {display_file_name}
File Size: {humanbytes(total_length)}
Downloaded: {humanbytes(downloaded)}
Progress: {percentage:.1f}%
Speed: {humanbytes(speed)}/s
ETA: {TimeFormatter(estimated_total_time)}"""

                            if current_message != display_message:
                                await bot.edit_message_text(
                                    chat_id,
                                    message_id,
                                    text=current_message,
                                    reply_markup=cancel_markup
                                )
                                display_message = current_message
                        except Exception as e:
                            logger.info(str(e))
                            pass

            return True

    except Exception as e:
        logger.error(f"Download coroutine error: {e}")
        return False


# Handler for cancel callbacks
async def handle_cancel_callback(bot, update):
    """Handle cancel download/upload callbacks"""
    cb_data = update.data

    if cb_data.startswith("cancel_dl_"):
        cancel_id = cb_data.replace("cancel_dl_", "")
        if cancel_id in active_downloads:
            active_downloads[cancel_id]["cancelled"] = True
            await update.answer("Cancelling download...", show_alert=False)
        else:
            await update.answer("Download not found or already completed", show_alert=True)

    elif cb_data.startswith("cancel_ul_"):
        cancel_id = cb_data.replace("cancel_ul_", "")
        if cancel_id in active_downloads:
            active_downloads[cancel_id]["cancelled"] = True
            await update.answer("Cancelling upload...", show_alert=False)
        else:
            await update.answer("Upload not found or already completed", show_alert=True)
