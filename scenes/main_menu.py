import os
import database

class MainMenuScene:
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

        if not text:
            await self.send_main_menu(n)
            return

        user_id = str(n.sender_id())
        admin_ids = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]
        tech_admin_ids = [x.strip() for x in os.getenv("TECH_ADMIN_USER_IDS", "").split(",") if x.strip()]
        role = database.get_user_role(user_id, admin_ids, tech_admin_ids)

        match text:
            case "/create_pass":
                from scenes.create_pass import CreatePassScene
                next_scene = CreatePassScene()
                n.activate_next_scene(next_scene)
                await next_scene.start_wizard(n)
                
            case "/my_requests":
                from scenes.user_requests import UserRequestsScene
                next_scene = UserRequestsScene()
                n.activate_next_scene(next_scene)
                await next_scene.show_user_requests(n)

            case "/admin_queue":
                if role == "admin":
                    from scenes.admin_queue import AdminQueueScene
                    next_scene = AdminQueueScene()
                    n.activate_next_scene(next_scene)
                    await next_scene.show_queue(n)
                else:
                    await n.reply("⛔ Доступ ограничен. Эта функция доступна только администраторам ИБ.")
                    await self.send_main_menu(n)

            case "/delete_my_data":
                buttons = [
                    [
                        {"type": "callback", "text": "💥 Да, удалить всё", "payload": "/confirm_delete_data"},
                        {"type": "callback", "text": "❌ Отмена", "payload": "/menu"}
                    ]
                ]
                await n.reply_with_keyboard(
                    "⚠️ **Внимание!**\n\nВы действительно хотите полностью удалить все свои персональные данные и созданные заявки из нашей базы?\n"
                    "Это действие является окончательным и не может быть отменено.",
                    "markdown",
                    buttons
                )

            case "/confirm_delete_data":
                database.delete_user_data(user_id)
                await n.reply("🗑 Все ваши персональные данные и заявки успешно удалены из системы.")
                from scenes.start import StartScene
                next_scene = StartScene()
                n.activate_next_scene(next_scene)
                await next_scene.execute(n)

            case "/tech_stats":
                if role == "tech_admin":
                    stats = database.get_system_stats()
                    stats_msg = (
                        "📊 **Статистика системы**\n\n"
                        f"👥 Всего пользователей: {stats['total_users']}\n"
                        f"🔒 С согласием: {stats['consented_users']}\n"
                        f"📝 Всего заявок: {stats['total_requests']}\n\n"
                        "📈 Статусы заявок:\n"
                    )
                    for status, count in stats["status_stats"].items():
                        stats_msg += f"- `{status}`: {count}\n"
                    
                    buttons = [[{"type": "callback", "text": "◀️ В меню", "payload": "/menu"}]]
                    await n.reply_with_keyboard(stats_msg, "markdown", buttons)
                else:
                    await n.reply("⛔ Доступ ограничен. Эта функция доступна только техническим администраторам.")
                    await self.send_main_menu(n)

            case "/tech_logs":
                if role == "tech_admin":
                    logs = database.get_audit_logs()
                    log_msg = "📋 **Журнал событий аудита (последние 20):**\n\n"
                    for log in logs[:20]:
                        # Sanitize comment if it contains sensitive details, but our db comment is just status update info
                        # Ensure we don't display sensitive request details directly
                        req_id_str = f"Заявка #{log['request_id']}" if log['request_id'] > 0 else "Общее действие"
                        # Format timestamp nicely
                        time_str = log['event_time'][:16].replace('T', ' ')
                        log_msg += f"• `{time_str}` [{req_id_str}] | *{log['event_type']}* | роль: {log['new_status'] or '-'}\n"
                        if log['comment']:
                            log_msg += f"  _Детали:_ {log['comment'][:40]}\n"
                    
                    buttons = [[{"type": "callback", "text": "◀️ В меню", "payload": "/menu"}]]
                    await n.reply_with_keyboard(log_msg, "markdown", buttons)
                else:
                    await n.reply("⛔ Доступ ограничен. Эта функция доступна только техническим администраторам.")
                    await self.send_main_menu(n)

            case "/menu" | "/start":
                await self.send_main_menu(n)

            case _:
                await n.reply("Неизвестная команда. Пожалуйста, воспользуйтесь меню бота.")
                await self.send_main_menu(n)

    async def send_main_menu(self, n):
        user_id = str(n.sender_id())
        admin_ids = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]
        tech_admin_ids = [x.strip() for x in os.getenv("TECH_ADMIN_USER_IDS", "").split(",") if x.strip()]
        role = database.get_user_role(user_id, admin_ids, tech_admin_ids)

        if role == "admin":
            text = (
                "🛡️ **Панель Администратора ИБ**\n\n"
                "Добро пожаловать! Вам доступны функции управления заявками на пропуск."
            )
            buttons = [
                [
                    {"type": "callback", "text": "📥 Очередь заявок", "payload": "/admin_queue"},
                    {"type": "callback", "text": "📝 Создать пропуск", "payload": "/create_pass"}
                ],
                [
                    {"type": "callback", "text": "🗂 Мои пропуски", "payload": "/my_requests"},
                    {"type": "callback", "text": "🗑 Удалить мои данные", "payload": "/delete_my_data"}
                ]
            ]
        elif role == "tech_admin":
            text = (
                "⚙️ **Панель Технического Администратора**\n\n"
                "Добро пожаловать! Вам доступна техническая диагностика системы ."
            )
            buttons = [
                [
                    {"type": "callback", "text": "📊 Статистика", "payload": "/tech_stats"},
                    {"type": "callback", "text": "📋 Журнал событий", "payload": "/tech_logs"}
                ],
                [
                    {"type": "callback", "text": "📝 Создать пропуск", "payload": "/create_pass"},
                    {"type": "callback", "text": "🗂 Мои пропуски", "payload": "/my_requests"}
                ],
                [
                    {"type": "callback", "text": "🗑 Удалить мои данные", "payload": "/delete_my_data"}
                ]
            ]
        else:
            text = (
                "📋 **Главное меню**\n\n"
                "Вы находитесь в системе электронного заказа пропусков. Пожалуйста, выберите действие:"
            )
            buttons = [
                [
                    {"type": "callback", "text": "📝 Оформить разовый пропуск", "payload": "/create_pass"},
                    {"type": "callback", "text": "🗂 Мои заявки", "payload": "/my_requests"}
                ],
                [
                    {"type": "callback", "text": "🗑 Удалить мои данные", "payload": "/delete_my_data"}
                ]
            ]

        await n.reply_with_keyboard(text, "markdown", buttons)
