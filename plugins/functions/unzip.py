# Auto Unzip Utility for URL Uploader Bot

import os
import zipfile
import logging
import shutil
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.functions.display_progress import progress_for_pyrogram
from plugins.script import Translation
from plugins.database.database import db
from plugins.thumbnail import Gthumb01

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def is_zip_file(file_path):
    """Check if a file is a ZIP archive"""
    try:
        return zipfile.is_zipfile(file_path)
    except Exception as e:
        logger.error(f"Error checking if file is ZIP: {e}")
        return False


def extract_zip(zip_path, extract_to):
    """
    Extract a ZIP file to the specified directory.
    Returns a list of extracted file paths.
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

            # Get list of extracted files
            for root, dirs, files in os.walk(extract_to):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Skip the original zip file
                    if file_path != zip_path:
                        extracted_files.append(file_path)

        logger.info(f"Extracted {len(extracted_files)} files from {zip_path}")
        return extracted_files
    except zipfile.BadZipFile:
        logger.error(f"Bad ZIP file: {zip_path}")
        return []
    except Exception as e:
        logger.error(f"Error extracting ZIP: {e}")
        return []


async def upload_extracted_files(bot, update, extracted_files, start_time, tmp_directory):
    """
    Upload extracted files to Telegram.
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

    for file_path in extracted_files:
        if not os.path.exists(file_path):
            failed_count += 1
            continue

        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            # Skip empty files
            if file_size == 0:
                continue

            await update.message.edit_caption(
                caption=f"📤 Uploading: {file_name}\n\nFile {uploaded_count + 1} of {len(extracted_files)}",
                reply_markup=None
            )

            # Upload as document
            await update.message.reply_document(
                document=file_path,
                file_name=file_name,
                thumb=thumbnail,
                caption=Translation.CUSTOM_CAPTION_UL_FILE,
                progress=progress_for_pyrogram,
                progress_args=(
                    Translation.UPLOAD_START,
                    update.message,
                    start_time
                )
            )
            uploaded_count += 1

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
            caption=f"📦 Extraction Complete!\n📁 Found {len(extracted_files)} files\n📤 Starting upload...",
            reply_markup=None
        )

        await upload_extracted_files(bot, update, extracted_files, start_time, tmp_directory_for_each_user)
        return True

    except Exception as e:
        logger.error(f"Error in auto unzip: {e}")
        return False
