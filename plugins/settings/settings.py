import asyncio
from pyrogram import types, errors, filters
from pyrogram.types import Message
from plugins.config import Config
from plugins.database.database import db
from plugins.database.add import AddUser
from pyrogram import Client

async def OpenSettings(m: "types.Message", user_id: int = None):
    usr_id = user_id if user_id else m.chat.id
    user_data = await db.get_user_data(usr_id)
    if not user_data:
        await m.edit("Failed to fetch your data from database!")
        return
    thumbnail = user_data.get("thumbnail", None)
    
    # Check if user is admin
    is_admin = usr_id in Config.ADMIN
    
    buttons_markup = [
        [types.InlineKeyboardButton("👤 USER COMMANDS", callback_data="userCommands")],
    ]
    
    # Only show Admin Commands button for admins
    if is_admin:
        buttons_markup.append([types.InlineKeyboardButton("🔐 ADMIN COMMANDS", callback_data="adminCommands")])
    
    buttons_markup.append([types.InlineKeyboardButton(f"{'🏞 CHANGE' if thumbnail else '🏞 SET'} THUMBNAIL",
                                    callback_data="setThumbnail")])
    if thumbnail:
        buttons_markup.append([types.InlineKeyboardButton("🏞 SHOW THUMBNAIL",
                                                          callback_data="showThumbnail")])
    buttons_markup.append([types.InlineKeyboardButton("🔙 BACK", 
                                                      callback_data="home")])

    try:
        await m.edit(
            text="**CURRENT SETTINGS 👇**",
            reply_markup=types.InlineKeyboardMarkup(buttons_markup),
            disable_web_page_preview=True,
        )
    except errors.MessageNotModified: pass
    except errors.FloodWait as e:
        await asyncio.sleep(e.x)
        await show_settings(m)
    except Exception as err:
        Config.LOGGER.getLogger(__name__).error(err)


async def OpenUserCommands(m: "types.Message", user_id: int = None):
    """Open User Commands submenu"""
    usr_id = user_id if user_id else m.chat.id
    user_data = await db.get_user_data(usr_id)
    if not user_data:
        await m.edit("Failed to fetch your data from database!")
        return
    
    upload_as_doc = user_data.get("upload_as_doc", False)
    auto_unzip = user_data.get("auto_unzip", False)
    auto_caption = user_data.get("auto_caption", False)
    
    buttons_markup = [
        [types.InlineKeyboardButton(f"{'📁 UPLOAD AS DOCUMENT' if upload_as_doc else '📹 UPLOAD AS VIDEO'}",
                                    callback_data="triggerUploadMode")],
        [types.InlineKeyboardButton(f"{'📝 AUTO CAPTION: ON ✅' if auto_caption else '📝 AUTO CAPTION: OFF ❌'}",
                                    callback_data="triggerAutoCaption")],
        [types.InlineKeyboardButton(f"{'📦 AUTO UNZIP: ON ✅' if auto_unzip else '📦 AUTO UNZIP: OFF ❌'}",
                                    callback_data="triggerAutoUnzip")],
        [types.InlineKeyboardButton("🔙 BACK TO SETTINGS", callback_data="OpenSettings")],
    ]

    try:
        await m.edit(
            text="**USER COMMANDS 👇**\n\nCustomize your upload preferences here:",
            reply_markup=types.InlineKeyboardMarkup(buttons_markup),
            disable_web_page_preview=True,
        )
    except errors.MessageNotModified: pass
    except Exception as err:
        Config.LOGGER.getLogger(__name__).error(err)


async def OpenAdminCommands(m: "types.Message", user_id: int = None):
    """Open Admin Commands submenu - only accessible by admins"""
    usr_id = user_id if user_id else m.chat.id
    
    # Check if user is admin
    if usr_id not in Config.ADMIN:
        await m.edit("⛔ You are not authorized to access this menu!")
        return
    
    user_data = await db.get_user_data(usr_id)
    if not user_data:
        await m.edit("Failed to fetch your data from database!")
        return
    
    private_mode = user_data.get("private_mode", False)
    
    buttons_markup = [
        [types.InlineKeyboardButton(f"{'🔒 PRIVATE MODE: ON ✅' if private_mode else '🌐 PUBLIC MODE: ON ✅'}",
                                    callback_data="triggerPrivateMode")],
        [types.InlineKeyboardButton("📊 BOT STATUS", callback_data="botStatus")],
        [types.InlineKeyboardButton("👥 TOTAL USERS", callback_data="totalUsers")],
        [types.InlineKeyboardButton("📢 BROADCAST", callback_data="broadcastMenu")],
        [types.InlineKeyboardButton("🔙 BACK TO SETTINGS", callback_data="OpenSettings")],
    ]

    try:
        await m.edit(
            text="**🔐 ADMIN COMMANDS 👇**\n\nManage bot settings and view statistics:",
            reply_markup=types.InlineKeyboardMarkup(buttons_markup),
            disable_web_page_preview=True,
        )
    except errors.MessageNotModified: pass
    except Exception as err:
        Config.LOGGER.getLogger(__name__).error(err)



@Client.on_message(filters.private & filters.command("settings"))
async def settings_handler(bot: Client, m: Message):
    await AddUser(bot, m)
    editable = await m.reply_text("**Checking...**", quote=True)
    await OpenSettings(editable, user_id=m.from_user.id)
