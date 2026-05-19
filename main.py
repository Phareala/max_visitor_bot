import asyncio
import logging
import os
import time
from dotenv import load_dotenv

from maxbot_chatbot_python import Bot, MapStateManager
from maxbot_api_client_python import API, Config
from scenes.start import StartScene
import database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("max_visitor_bot")

async def main():
    # Load environment variables
    load_dotenv()
    
    # Initialize database
    logger.info("Initializing database...")
    database.init_db()
    
    # Read configuration
    base_url = os.getenv("BASE_URL", "https://platform-api.max.ru")
    token = os.getenv("TOKEN")
    
    if not token:
        logger.error("API TOKEN is missing in configuration! Please specify TOKEN in .env file.")
        return
        
    logger.info(f"Starting bot using base_url: {base_url}")
    
    cfg = Config(
        base_url=base_url,
        token=token,
        ratelimiter=25,
        timeout=30
    )

    async with API(cfg) as api_client:
        bot = Bot(api_client)
        
        start_scene = StartScene()
        bot.state_manager = MapStateManager(init_data={})
        bot.state_manager.set_start_scene(start_scene)

        start_time = time.time()

        @bot.router.register("message_created")
        @bot.router.register("message_callback")
        async def scene_handler(notification):
            # Ignore messages received before bot startup
            if notification.update and getattr(notification.update, 'timestamp', 0) < (start_time * 1000):
                return
            
            notification.create_state_id()

            if not bot.state_manager.get(notification.state_id):
                bot.state_manager.create(notification.state_id)

            current_scene = notification.get_current_scene()
            if not current_scene:
                current_scene = start_scene
                notification.activate_next_scene(current_scene)

            if hasattr(current_scene, 'execute'):
                try:
                    await current_scene.execute(notification)
                except Exception as e:
                    logger.exception(f"Error executing scene {type(current_scene).__name__}: {e}")
                    await notification.reply("❌ Произошла внутренняя ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.")
            else:
                logger.error(f"Current scene {type(current_scene).__name__} does not implement 'execute'")

        try:
            logger.info("Bot polling loop started.")
            await bot.start_polling()
        except asyncio.CancelledError:
            logger.info("The bot polling has been cancelled.")
        except Exception as e:
            logger.exception(f"Unexpected error in bot polling: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by User (KeyboardInterrupt).")
