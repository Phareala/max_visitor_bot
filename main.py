import asyncio
import logging
import os
import time
from dotenv import load_dotenv

from maxbot_chatbot_python import Bot, MapStateManager
from maxbot_api_client_python import API, Config
from scenes.start import StartScene
import database

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("max_visitor_bot")

# Monkey-патч: при коллбэках редактировать существующее сообщение вместо отправки нового
from maxbot_chatbot_python import Notification
from maxbot_api_client_python import models, utils

original_reply_with_keyboard = Notification.reply_with_keyboard
original_reply = Notification.reply

async def smart_reply_with_keyboard(self, text: str, format_type: str | None, buttons: list[list[dict]]):
    if self.type() == "message_callback" and getattr(self.update, "message_id", None):
        try:
            req = models.EditMessageReq(
                message_id=self.update.message_id,
                text=text,
                format=format_type if format_type else None,
                attachments=[utils.attach_keyboard(buttons)]
            )
            await self.bot.api.messages.edit_message_async(req)
            return
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение {self.update.message_id}, отправляем новое: {e}")
    await original_reply_with_keyboard(self, text, format_type, buttons)

async def smart_reply(self, text: str, format_type: str | None = "markdown"):
    if self.type() == "message_callback" and getattr(self.update, "message_id", None):
        try:
            req = models.EditMessageReq(
                message_id=self.update.message_id,
                text=text,
                format=format_type if format_type else None,
                attachments=[]
            )
            await self.bot.api.messages.edit_message_async(req)
            return
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение {self.update.message_id}, отправляем новое: {e}")
    await original_reply(self, text, format_type)

Notification.reply_with_keyboard = smart_reply_with_keyboard
Notification.reply = smart_reply


async def main():
    # Загрузка переменных окружения
    load_dotenv()

    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    database.init_db()

    # Чтение конфигурации
    base_url = os.getenv("BASE_URL", "https://platform-api.max.ru")
    token = os.getenv("TOKEN")

    if not token:
        logger.error("TOKEN отсутствует в конфигурации! Укажите TOKEN в файле .env")
        return

    logger.info(f"Запуск бота с base_url: {base_url}")
    
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
            # Игнорируем сообщения, полученные до запуска бота
            if notification.update and getattr(notification.update, 'timestamp', 0) < (start_time * 1000):
                return

            notification.create_state_id()

            if not bot.state_manager.get(notification.state_id):
                bot.state_manager.create(notification.state_id)

            # ── Глобальный перехватчик навигации ─────────────────────────────
            # /start и /menu работают из любой сцены, независимо от состояния.
            try:
                raw_text = notification.text()
            except ValueError:
                raw_text = None

            if raw_text in ("/start", "/menu"):
                # Подтверждаем коллбэк до перенаправления (сцена не будет его обрабатывать)
                if notification.type() == "message_callback":
                    await notification.answer_callback("")
                try:
                    user_id = str(notification.sender_id())
                    user = database.get_user(user_id)
                    if user and user["consent_given"]:
                        from scenes.main_menu import MainMenuScene
                        menu_scene = MainMenuScene()
                        notification.activate_next_scene(menu_scene)
                        await menu_scene.send_main_menu(notification)
                    else:
                        # Согласие ещё не дано — перезапускаем сцену согласия
                        notification.activate_next_scene(start_scene)
                        await start_scene.execute(notification)
                except Exception as e:
                    logger.exception(f"Ошибка в глобальном обработчике навигации: {e}")
                return
            # ─────────────────────────────────────────────────────────────────

            current_scene = notification.get_current_scene()
            if not current_scene:
                current_scene = start_scene
                notification.activate_next_scene(current_scene)

            if hasattr(current_scene, 'execute'):
                try:
                    await current_scene.execute(notification)
                except Exception as e:
                    logger.exception(f"Ошибка при выполнении сцены {type(current_scene).__name__}: {e}")
                    await notification.reply("❌ Произошла внутренняя ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.")
            else:
                logger.error(f"Сцена {type(current_scene).__name__} не реализует метод 'execute'")

        try:
            logger.info("Цикл опроса бота запущен.")
            await bot.start_polling()
        except asyncio.CancelledError:
            logger.info("Цикл опроса бота отменён.")
        except Exception as e:
            logger.exception(f"Неожиданная ошибка в цикле опроса бота: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем (KeyboardInterrupt).")
