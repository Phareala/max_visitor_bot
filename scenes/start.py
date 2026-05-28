import os
import database
from maxbot_api_client_python import utils

class StartScene:
    async def start(self, app):
        pass

    async def execute(self, n):
        is_callback = n.type() == "message_callback"
        if is_callback:
            await n.answer_callback("")

        try:
            text = n.text()
        except ValueError:
            text = None

        try:
            user_id = str(n.sender_id())
            display_name = n.sender_name() or f"User {user_id}"
        except ValueError:
            await n.reply("Ошибка: не удалось определить вашего пользователя.")
            return

        # Проверяем, дал ли пользователь согласие ранее
        user = database.get_user(user_id)
        if user and user["consent_given"] == 1:
            # Согласие есть — переходим в главное меню
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        # Обработка нажатия на кнопку согласия
        if text == "/consent_yes":
            admin_ids = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]
            tech_admin_ids = [x.strip() for x in os.getenv("TECH_ADMIN_USER_IDS", "").split(",") if x.strip()]

            role = database.get_user_role(user_id, admin_ids, tech_admin_ids)
            database.give_consent(user_id, display_name, role)

            await n.reply(
                f"✅ Спасибо! Согласие успешно зафиксировано.\n\n"
                f"🪪 Ваш ID в системе: `{user_id}`\n"
                f"_Сохраните его — он понадобится, если вам нужно будет получить права администратора._"
            )

            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        elif text == "/consent_no":
            await n.reply_with_keyboard(
                "❌ Вы отклонили согласие на обработку данных.\n\n"
                "К сожалению, без согласия система не может предоставить доступ к оформлению пропусков. "
                "Вы можете изменить свое решение в любой момент, нажав кнопку ниже.",
                "markdown",
                [[{"type": "callback", "text": "✅ Предоставить согласие", "payload": "/consent_yes"}]]
            )
            return

        # Иначе — показываем приветствие, дисклеймер и запрос согласия
        welcome_text = (
            "👋 **Добро пожаловать в Электронное бюро пропусков!**\n\n"
            "Этот чат-бот предназначен для быстрого оформления разовых гостевых пропусков на конкретную дату.\n\n"
            "⚠️ **Дисклеймер:** Сервис разработан командой хакатона университета и не является официальной функцией платформы.\n\n"
            "🔒 Для начала работы необходимо дать согласие на обработку минимальных данных вашего профиля:\n"
            "- Вашего уникального ID в мессенджере MAX\n"
            "- Вашего отображаемого имени\n\n"
            "Эти данные будут использоваться исключительно в целях создания заявок на пропуска, "
            "их авторизации и ведения журнала аудита событий."
        )

        buttons = [
            [
                {"type": "callback", "text": "✅ Согласен", "payload": "/consent_yes"},
                {"type": "callback", "text": "❌ Не согласен", "payload": "/consent_no"}
            ]
        ]

        await n.reply_with_keyboard(welcome_text, "markdown", buttons)
