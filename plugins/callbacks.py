import os
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes
from plugins.config import Config
from plugins.dl_button import ddl_call_back, handle_cancel_callback
from plugins.button import youtube_dl_call_back, handle_ytdl_cancel, active_ytdlp_processes
from plugins.settings.settings import OpenSettings
from plugins.script import Translation
from pyrogram import Client, types
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.database.database import db
import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)



@Client.on_callback_query()
async def button(bot, update):
    cb_data = update.data

    # Handle cancel callbacks first
    if cb_data.startswith("cancel_dl_"):
        await handle_cancel_callback(bot, update)
        return
    elif cb_data.startswith("cancel_ul_"):
        await handle_cancel_callback(bot, update)
        return
    elif cb_data.startswith("cancel_ytdl_"):
        cancel_id = cb_data.replace("cancel_ytdl_", "")
        await handle_ytdl_cancel(bot, update, cancel_id)
        return

    if cb_data == "home":
        await update.message.edit(
            text=Translation.START_TEXT.format(update.from_user.mention),
            reply_markup=Translation.START_BUTTONS,
        )
    elif cb_data == "help":
        await update.message.edit(
            text=Translation.HELP_TEXT,
            reply_markup=Translation.HELP_BUTTONS,
        )
    elif cb_data == "about":
        await update.message.edit(
            text=Translation.ABOUT_TEXT,
            reply_markup=Translation.ABOUT_BUTTONS,
        )
    elif "refreshForceSub" in cb_data:
        if Config.UPDATES_CHANNEL:
            if str(Config.UPDATES_CHANNEL).startswith("-100"):
                channel_chat_id = int(Config.UPDATES_CHANNEL)
            else:
                channel_chat_id = Config.UPDATES_CHANNEL
            try:
                user = await bot.get_chat_member(channel_chat_id, update.message.chat.id)
                if user.status == "kicked":
                    await update.message.edit(
                        text="Sorry Sir, You are Banned. Contact My [Support Group](https://t.me/NT_BOTS_SUPPORT)",
                        disable_web_page_preview=True
                    )
                    return
            except UserNotParticipant:
                chat_id = channel_chat_id
                await update.message.edit(
                    text="**I like Your Smartness But Don't Be Oversmart! 😑**\n\n",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton("🤖 Join Updates Channel", url=invite_link.invite_link)
                            ],
                            [
                                InlineKeyboardButton("🔄 Refresh 🔄", callback_data="refreshForceSub")
                            ]
                        ]
                    )
                )
                return
            except Exception:
                await update.message.edit(
                    text="Something Went Wrong. Contact My [Support Group](https://t.me/NT_BOTS_SUPPORT)",
                    disable_web_page_preview=True
                )
                return
        await update.message.edit(
            text=Translation.START_TEXT.format(update.from_user.mention),
            reply_markup=Translation.START_BUTTONS,
        )
    elif cb_data == "OpenSettings":
        await update.answer()
        await OpenSettings(update.message)
    elif cb_data == "showThumbnail":
        thumbnail = await db.get_thumbnail(update.from_user.id)
        if not thumbnail:
            await update.answer("You didn't set any custom thumbnail!", show_alert=True)
        else:
            await update.answer()
            await bot.send_photo(update.message.chat.id, thumbnail, "Custom Thumbnail",
                               reply_markup=types.InlineKeyboardMarkup([[
                                   types.InlineKeyboardButton("Delete Thumbnail",
                                                              callback_data="deleteThumbnail")
                               ]]))
    elif cb_data == "deleteThumbnail":
        await db.set_thumbnail(update.from_user.id, None)
        await update.answer("Okay, I deleted your custom thumbnail. Now I will apply default thumbnail.", show_alert=True)
        await update.message.delete(True)
    elif cb_data == "setThumbnail":
        await update.message.edit(
            text=Translation.TEXT,
            reply_markup=Translation.BUTTONS,
            disable_web_page_preview=True
        )

    elif cb_data == "triggerGenSS":
        await update.answer()
        generate_ss = await db.get_generate_ss(update.from_user.id)
        if generate_ss:
            await db.set_generate_ss(update.from_user.id, False)
        else:
            await db.set_generate_ss(update.from_user.id, True)
        await OpenSettings(update.message)

    elif cb_data == "triggerGenSample":
        await update.answer()
        generate_sample_video = await db.get_generate_sample_video(update.from_user.id)
        if generate_sample_video:
            await db.set_generate_sample_video(update.from_user.id, False)
        else:
            await db.set_generate_sample_video(update.from_user.id, True)
        await OpenSettings(update.message)

    elif cb_data == "triggerUploadMode":
        await update.answer()
        upload_as_doc = await db.get_upload_as_doc(update.from_user.id)
        if upload_as_doc:
            await db.set_upload_as_doc(update.from_user.id, False)
        else:
            await db.set_upload_as_doc(update.from_user.id, True)
        await OpenSettings(update.message)

    elif cb_data == "triggerAutoUnzip":
        await update.answer()
        auto_unzip = await db.get_auto_unzip(update.from_user.id)
        if auto_unzip:
            await db.set_auto_unzip(update.from_user.id, False)
        else:
            await db.set_auto_unzip(update.from_user.id, True)
        await OpenSettings(update.message)

    elif cb_data == "triggerAutoCaption":
        await update.answer()
        auto_caption = await db.get_auto_caption(update.from_user.id)
        if auto_caption:
            await db.set_auto_caption(update.from_user.id, False)
        else:
            await db.set_auto_caption(update.from_user.id, True)
        await OpenSettings(update.message)

    elif "close" in cb_data:
        await update.message.delete(True)

    elif "|" in cb_data:
        await youtube_dl_call_back(bot, update)
    elif "=" in cb_data:
        await ddl_call_back(bot, update)

    else:
        await update.message.delete()
