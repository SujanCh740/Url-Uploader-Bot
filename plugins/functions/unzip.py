# Auto Unzip Utility for URL Uploader Bot

import os
import zipfile
import logging
import shutil
import re
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.functions.display_progress import progress_for_pyrogram
from plugins.script import Translation
from plugins.database.database import db
from plugins.thumbnail import Gthumb01, Mdata01, Gthumb02
from pyrogram import enums

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Video file extensions
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp'}


def is_zip_file(file_path):
    """Check if a file is a ZIP archive"""
    try:
        return zipfile.is_zipfile(file_path)
    except Exception as e:
        logger.error(f"Error checking if file is ZIP: {e}")
        return False


def fix_unknown_video_extension(file_path):
    """
    Fix files with '_0.unknown_video' extension to .mkv
    Returns the new file path if renamed, otherwise original path
    """
    if file_path.endswith('_0.unknown_video'):
        new_path = file_path.replace('_0.unknown_video', '.mkv')
        try:
            os.rename(file_path, new_path)
            logger.info(f"Renamed {file_path} to {new_path}")
            return new_path
        except Exception as e:
            logger.error(f"Error renaming file: {e}")
            return file_path
    return file_path


def extract_episode_info(filename):
    """
    Extract season and episode numbers from filename.
    Supports formats like: S01EP01, S01E01, Season 1 Episode 1, etc.
    Returns tuple (season_num, episode_num) for sorting
    """
    # Patterns to match: S01EP01, S01E01, s01e01, S1EP1, etc.
    patterns = [
        r'[Ss](\d+)[Ee][Pp]?(\d+)',  # S01EP01, S01E01, S1EP1
        r'[Ss]eason\s*(\d+).*?[Ee]pisode\s*(\d+)',  # Season 1 Episode 1
        r'[Ss](\d+)\s*[Ee](\d+)',  # S01 E01
        r'(\d+)x(\d+)',  # 1x01 format
        r'[Ee][Pp]?(\d+)',  # EP01 or E01 (episode only)
    ]

    filename_lower = filename.lower()

    for pattern in patterns:
        match = re.search(pattern, filename_lower)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                season = int(groups[0]) if groups[0] else 0
                episode = int(groups[1]) if groups[1] else 0
                return (season, episode)
            elif len(groups) == 1:
                # Episode only pattern
                episode = int(groups[0]) if groups[0] else 0
                return (0, episode)

    # If no pattern matches, return high values to put at end
    return (9999, 9999)


def sort_files_by_episode(files):
    """
    Sort files by season and episode numbers.
    Files without episode info will be placed at the end, sorted alphabetically.
    """
    def sort_key(file_path):
        filename = os.path.basename(file_path)
        season, episode = extract_episode_info(filename)
        # Sort by season, then episode, then filename for tie-breaking
        return (season, episode, filename.lower())

    return sorted(files, key=sort_key)


def is_video_file(file_path):
    """Check if a file is a video based on extension"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in VIDEO_EXTENSIONS


def extract_zip(zip_path, extract_to):
    """
    Extract a ZIP file to the specified directory.
    Returns a list of extracted file paths with fixed extensions.
    """
    extracted_files = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Check for potential zip bomb (zip slip attack)
            for member in zip_ref.namelist():
                member_path = os.path.join(extract_to, member)
                if not os.path.commonpath([extract_to, member_path]).startswith(extract_to):
                    logger.warning(f"Potential zip slip attack detected: {member}")
                    continue

            # Extract all files
            zip_ref.extractall(extract_to)

            # Get list of extracted files and fix extensions
            for root, dirs, files in os.walk(extract_to):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Skip the original zip file
                    if file_path != zip_path:
                        # Fix _0.unknown_video extension
                        fixed_path = fix_unknown_video_extension(file_path)
                        extracted_files.append(fixed_path)

        # Sort files by episode sequence
        extracted_files = sort_files_by_episode(extracted_files)

        logger.info(f"Extracted and sorted {len(extracted_files)} files from {zip_path}")
        return extracted_files
    except zipfile.BadZipFile:
        logger.error(f"Bad ZIP file: {zip_path}")
        return []
    except Exception as e:
        logger.error(f"Error extracting ZIP: {e}")
        return []


async def upload_file_with_smart_type(bot, update, file_path, file_name, thumbnail, start_time):
    """
    Upload a file as video or document based on file type.
    Returns True if upload successful.
    """
    try:
        # Determine caption: auto_caption uses filename with underscores removed
        auto_caption_enabled = await db.get_auto_caption(update.from_user.id)
        if auto_caption_enabled:
            caption = file_name.replace("_", " ")
        else:
            # Use CUSTOM_CAPTION_UL_FILE or fallback to filename
            caption = Translation.CUSTOM_CAPTION_UL_FILE
            if not caption or caption.strip() == "":
                caption = file_name

        if is_video_file(file_path):
            # Upload as video
            try:
                width, height, duration = await Mdata01(file_path)
                thumb_image_path = await Gthumb02(bot, update, duration, file_path)
                await update.message.reply_video(
                    video=file_path,
                    file_name=file_name,
                    caption=caption,
                    duration=duration,
                    width=width,
                    height=height,
                    supports_streaming=True,
                    thumb=thumb_image_path,
                    parse_mode=enums.ParseMode.HTML,
                    progress=progress_for_pyrogram,
                    progress_args=(
                        Translation.UPLOAD_START,
                        update.message,
                        start_time
                    )
                )
                # Clean up thumbnail
                if os.path.exists(thumb_image_path):
                    os.remove(thumb_image_path)
                return True
            except Exception as e:
                logger.warning(f"Failed to upload as video, falling back to document: {e}")
                # Fall back to document upload

        # Upload as document (default for non-video files or if video upload failed)
        await update.message.reply_document(
            document=file_path,
            file_name=file_name,
            thumb=thumbnail,
            caption=caption,
            parse_mode=enums.ParseMode.HTML,
            progress=progress_for_pyrogram,
            progress_args=(
                Translation.UPLOAD_START,
                update.message,
                start_time
            )
        )
        return True

    except Exception as e:
        logger.error(f"Error uploading file {file_path}: {e}")
        return False


async def upload_extracted_files(bot, update, extracted_files, start_time, tmp_directory):
    """
    Upload extracted files to Telegram in episode sequence.
    Returns True if all files uploaded successfully.
    """
    if not extracted_files:
        await update.message.edit_caption(
            caption="❌ No files found in the ZIP archive",
            reply_markup=None
        )
        return False

    thumbnail = await Gthumb01(bot, update)
    uploaded_count = 0
    failed_count = 0

    total_files = len(extracted_files)

    for index, file_path in enumerate(extracted_files, 1):
        if not os.path.exists(file_path):
            failed_count += 1
            continue

        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            # Skip empty files
            if file_size == 0:
                continue

            # Show episode info if detected
            season, episode = extract_episode_info(file_name)
            episode_info = ""
            if season < 9999 or episode < 9999:
                episode_info = f" (S{season:02d}EP{episode:02d})"

            await update.message.edit_caption(
                caption=f"📤 Uploading: {file_name}{episode_info}\n\nFile {index} of {total_files}",
                reply_markup=None
            )

            # Upload with smart type detection
            success = await upload_file_with_smart_type(
                bot, update, file_path, file_name, thumbnail, start_time
            )

            if success:
                uploaded_count += 1
            else:
                failed_count += 1

        except Exception as e:
            logger.error(f"Error uploading file {file_path}: {e}")
            failed_count += 1

    # Cleanup extracted files
    try:
        if os.path.exists(tmp_directory):
            shutil.rmtree(tmp_directory)
    except Exception as e:
        logger.error(f"Error cleaning up: {e}")

    # Final status message
    if uploaded_count > 0:
        await update.message.edit_caption(
            caption=f"✅ Auto Unzip Complete!\n\n📤 Uploaded: {uploaded_count} files\n❌ Failed: {failed_count} files",
            reply_markup=None
        )
        return True
    else:
        await update.message.edit_caption(
            caption="❌ Failed to upload any files from the ZIP archive",
            reply_markup=None
        )
        return False


async def handle_auto_unzip(bot, update, download_directory, tmp_directory_for_each_user, start_time):
    """
    Handle auto unzip functionality after download.
    Returns True if unzip was performed and files were uploaded.
    """
    try:
        # Check if file is a ZIP
        if not is_zip_file(download_directory):
            return False

        logger.info(f"ZIP file detected: {download_directory}")

        # Get user's auto_unzip setting
        auto_unzip = await db.get_auto_unzip(update.from_user.id)

        if not auto_unzip:
            logger.info("Auto unzip is disabled for this user")
            return False

        logger.info("Auto unzip is enabled, extracting...")

        # Create extraction directory
        extract_dir = os.path.join(tmp_directory_for_each_user, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        # Update message
        await update.message.edit_caption(
            caption="📦 ZIP file detected!\n🔄 Extracting files...",
            reply_markup=None
        )

        # Extract ZIP file
        extracted_files = extract_zip(download_directory, extract_dir)

        if not extracted_files:
            await update.message.edit_caption(
                caption="❌ Failed to extract ZIP file",
                reply_markup=None
            )
            return False

        # Delete the original ZIP file after extraction
        try:
            os.remove(download_directory)
        except Exception as e:
            logger.error(f"Error removing ZIP file: {e}")

        # Upload extracted files
        await update.message.edit_caption(
            caption=f"📦 Extraction Complete!\n📁 Found {len(extracted_files)} files\n📤 Starting upload in sequence...",
            reply_markup=None
        )

        await upload_extracted_files(bot, update, extracted_files, start_time, tmp_directory_for_each_user)
        return True

    except Exception as e:
        logger.error(f"Error in auto unzip: {e}")
        return False
