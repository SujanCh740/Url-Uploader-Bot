import os
from plugins.config import Config
from pyrogram import Client

if __name__ == "__main__":

    # 🚨 SECURITY WARNING SECTION 🚨
    print("\n" + "=" * 60)
    print("🚨  SECURITY WARNING for Forked Users  🚨")
    print("-" * 60)
    print("⚠️  This is a PUBLIC repository.")
    print("🧠  Do NOT expose your BOT_TOKEN, API_ID, API_HASH, or cookies.txt.")
    print("💡  Always use Heroku Config Vars or a private .env file to store secrets.")
    print("🔒  Never commit sensitive data to your fork — anyone can steal it!")
    print("📢  Support: @Sujan_Ch")
    print("=" * 60 + "\n")

    # Ensure download folder exists
    if not os.path.isdir(Config.DOWNLOAD_LOCATION):
        os.makedirs(Config.DOWNLOAD_LOCATION)

    # Start bot
    plugins = dict(root="plugins")
    Client = Client(
        "@UploaderXNTBot",
        bot_token=Config.BOT_TOKEN,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        upload_boost=True,
        sleep_threshold=300,
        plugins=plugins
    )

    print("🎊 I AM ALIVE 🎊  • Support @Sujan_Ch")
    Client.run()
