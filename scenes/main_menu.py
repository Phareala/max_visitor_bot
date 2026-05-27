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
                if role == "initiator":
                    from scenes.create_pass import CreatePassScene
                    next_scene = CreatePassScene()
                    n.activate_next_scene(next_scene)
                    await next_scene.start_wizard(n)
                else:
                    await n.reply("⛔ Доступ ограничен. Вы не можете создавать заявки.")
                    await self.send_main_menu(n)

            case "/my_requests":
                if role == "initiator":
                    from scenes.user_requests import UserRequestsScene
                    next_scene = UserRequestsScene()
                    n.activate_next_scene(next_scene)
                    await next_scene.show_user_requests(n)
                else:
                    await n.reply("⛔ Доступ ограничен. У вас нет роли инициатора.")
                    await self.send_main_menu(n)

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
                if role == "initiator":
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
                else:
                    await n.reply("⛔ Удаление персональных данных доступно только инициаторам.")
                    await self.send_main_menu(n)

            case "/confirm_delete_data":
                if role == "initiator":
                    database.delete_user_data(user_id)
                    await n.reply("🗑 Все ваши персональные данные и заявки успешно удалены из системы.")
                    from scenes.start import StartScene
                    next_scene = StartScene()
                    n.activate_next_scene(next_scene)
                    await next_scene.execute(n)
                else:
                    await n.reply("⛔ Действие недоступно.")
                    await self.send_main_menu(n)

            case "/tech_stats":
                if role == "tech_admin":
                    text_menu = (
                        "📊 **Статистика системы**\n\n"
                        "Выберите период для отображения подробных показателей или экспортируйте данные в CSV:"
                    )
                    buttons = [
                        [
                            {"type": "callback", "text": "📅 За сегодня", "payload": "/stats_p_1"},
                            {"type": "callback", "text": "📅 За неделю", "payload": "/stats_p_7"}
                        ],
                        [
                            {"type": "callback", "text": "📅 За месяц", "payload": "/stats_p_30"},
                            {"type": "callback", "text": "📅 За год", "payload": "/stats_p_365"}
                        ],
                        [
                            {"type": "callback", "text": "🌐 За всё время", "payload": "/stats_p_all"}
                        ],
                        [
                            {"type": "callback", "text": "📤 Экспорт в CSV", "payload": "/stats_export"}
                        ],
                        [
                            {"type": "callback", "text": "◀️ В меню", "payload": "/menu"}
                        ]
                    ]
                    await n.reply_with_keyboard(text_menu, "markdown", buttons)
                else:
                    await n.reply("⛔ Доступ ограничен. Эта функция доступна только техническим администраторам.")
                    await self.send_main_menu(n)

            case "/stats_p_1" | "/stats_p_7" | "/stats_p_30" | "/stats_p_365" | "/stats_p_all":
                if role == "tech_admin":
                    days_map = {
                        "/stats_p_1": 1,
                        "/stats_p_7": 7,
                        "/stats_p_30": 30,
                        "/stats_p_365": 365,
                        "/stats_p_all": None
                    }
                    days = days_map[text]
                    period_label = {
                        1: "за сегодня",
                        7: "за неделю",
                        30: "за месяц",
                        365: "за год",
                        None: "за всё время"
                    }[days]

                    stats = database.get_period_stats(days)
                    stats_msg = (
                        f"📊 **Статистика системы {period_label}**\n\n"
                        f"👥 Новых пользователей с согласием: `{stats['total_users']}`\n"
                        f"📝 Всего создано заявок: `{stats['total_requests']}`\n\n"
                        f"📈 **Статусы заявок:**\n"
                    )

                    total_reqs = stats['total_requests']
                    STATUS_MAP_LOCAL = {
                        "draft": "Черновик 📝",
                        "review": "На рассмотрении 📥",
                        "clarification": "Требуется уточнение ⚠️",
                        "approved": "Согласована ✅",
                        "rejected": "Отклонена ❌",
                        "closed": "Закрыта 🔒",
                        "canceled": "Отменена 🔕",
                        "expired": "Просрочена ⏳"
                    }

                    if total_reqs > 0:
                        for st, name in STATUS_MAP_LOCAL.items():
                            count = stats["status_stats"].get(st, 0)
                            pct = (count / total_reqs) * 100
                            bar_len = int(round(pct / 10))
                            bar = "█" * bar_len + "░" * (10 - bar_len)
                            stats_msg += f"- {name}: `{count}` ({pct:.1f}%)\n  `{bar}`\n"
                    else:
                        stats_msg += "Заявок за этот период нет.\n"

                    stats_msg += f"\n🚪 **Популярность корпусов:**\n"
                    if total_reqs > 0 and stats["campus_stats"]:
                        for campus, count in stats["campus_stats"].items():
                            pct = (count / total_reqs) * 100
                            bar_len = int(round(pct / 10))
                            bar = "█" * bar_len + "░" * (10 - bar_len)
                            short_campus = campus[:30] + "..." if len(campus) > 30 else campus
                            stats_msg += f"- *{short_campus}*: `{count}` ({pct:.1f}%)\n  `{bar}`\n"
                    else:
                        stats_msg += "Данные о корпусах отсутствуют.\n"

                    buttons = [
                        [{"type": "callback", "text": "◀️ Выбор периода", "payload": "/tech_stats"}],
                        [{"type": "callback", "text": "◀️ Главное меню", "payload": "/menu"}]
                    ]
                    await n.reply_with_keyboard(stats_msg, "markdown", buttons)
                else:
                    await n.reply("⛔ Доступ ограничен.")
                    await self.send_main_menu(n)

            case "/stats_export":
                if role == "tech_admin":
                    import csv
                    import io
                    import tempfile
                    from maxbot_api_client_python.types.models import SendMessageReq, Attachment, FileAttachmentPayload
                    from maxbot_api_client_python.types.constants import UploadType, AttachmentType
                    import logging
                    logger = logging.getLogger("max_visitor_bot")

                    requests_data = database.get_all_requests_for_export()
                    if not requests_data:
                        await n.reply("Нет данных для экспорта.")
                        return

                    output = io.StringIO()
                    output.write('﻿')  # UTF-8 BOM
                    writer = csv.writer(output, delimiter=';')
                    writer.writerow([
                        "ID заявки", "ID инициатора", "ФИО инициатора", "ФИО гостя",
                        "Дата визита", "Время визита", "Корпус / Зона", "Цель визита",
                        "Статус", "Комментарий ИБ", "Причина отказа", "Создана в", "Дополнительные поля"
                    ])

                    for r in requests_data:
                        cf_str = ", ".join([f"{k}: {v}" for k, v in r["custom_fields"].items()])
                        writer.writerow([
                            r["request_id"], r["initiator_id"], r["initiator_name"] or "", r["visitor_name"],
                            r["visit_date"], r["visit_time"], r["visit_zone"], r["visit_purpose"],
                            r["status"], r["admin_comment"] or "", r["rejection_reason"] or "", r["created_at"],
                            cf_str
                        ])

                    csv_content = output.getvalue()
                    try:
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as temp_file:
                            temp_file.write(csv_content)
                            temp_path = temp_file.name

                        try:
                            upload_resp = await n.bot.api.uploads.get_upload_url_async(UploadType.FILE)
                            uploaded_info = await n.bot.api.uploads.upload_multipart_async(upload_resp.url, temp_path)

                            if uploaded_info and uploaded_info.token:
                                req = SendMessageReq(
                                    user_id=int(n.sender_id()),
                                    text="📊 Экспорт всех заявок в формат CSV завершен. Файл прикреплен ниже:",
                                    attachments=[
                                        Attachment(
                                            type=AttachmentType.FILE,
                                            payload=FileAttachmentPayload(
                                                token=uploaded_info.token,
                                                filename="requests_export.csv"
                                            )
                                        )
                                    ]
                                )
                                await n.bot.api.messages.send_message_async(req)
                            else:
                                raise Exception("Empty upload response/token")
                        finally:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                    except Exception as e:
                        logger.exception(f"Failed to export CSV as file: {e}")
                        preview_csv = csv_content[:1500]
                        if len(csv_content) > 1500:
                            preview_csv += "\n... [остальные строки обрезаны]"

                        await n.reply_with_keyboard(
                            "⚠️ Не удалось отправить файл из-за ошибки. Превью данных:\n\n"
                            f"```csv\n{preview_csv}\n```",
                            "markdown",
                            [[{"type": "callback", "text": "◀️ Назад к статистике", "payload": "/tech_stats"}]]
                        )
                else:
                    await n.reply("⛔ Доступ ограничен.")
                    await self.send_main_menu(n)

            case "/custom_fields":
                if role == "tech_admin":
                    from scenes.custom_fields_mgmt import CustomFieldsMgmtScene
                    next_scene = CustomFieldsMgmtScene()
                    n.activate_next_scene(next_scene)
                    await next_scene.show_choose_zone(n)
                else:
                    await n.reply("⛔ Доступ ограничен. Эта функция доступна только техническим администраторам.")
                    await self.send_main_menu(n)

            case "/zones_mgmt":
                if role == "tech_admin":
                    from scenes.zones_mgmt import ZonesMgmtScene
                    next_scene = ZonesMgmtScene()
                    n.activate_next_scene(next_scene)
                    await next_scene.show_zones_list(n)
                else:
                    await n.reply("⛔ Доступ ограничен. Эта функция доступна только техническим администраторам.")
                    await self.send_main_menu(n)

            case "/tech_logs":
                if role == "tech_admin":
                    logs = database.get_audit_logs()
                    log_msg = "📋 **Журнал событий аудита (последние 20):**\n\n"
                    for log in logs[:20]:
                        req_id_str = f"Заявка #{log['request_id']}" if log['request_id'] > 0 else "Общее действие"
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
            # Show queue size in the admin panel header
            queue = database.get_admin_queue()
            queue_size = len(queue)
            queue_hint = f" (`{queue_size}` в очереди)" if queue_size > 0 else ""
            text = (
                f"🛡️ **Панель Администратора ИБ**\n\n"
                f"Добро пожаловать! Вам доступны функции управления заявками на пропуск.{queue_hint}"
            )
            buttons = [
                [
                    {"type": "callback", "text": f"📥 Очередь заявок{(' (' + str(queue_size) + ')') if queue_size else ''}", "payload": "/admin_queue"}
                ]
            ]

        elif role == "tech_admin":
            text = (
                "⚙️ **Панель Технического Администратора**\n\n"
                "Добро пожаловать! Вам доступны функции настройки системы и просмотр статистики."
            )
            buttons = [
                [
                    {"type": "callback", "text": "📊 Статистика", "payload": "/tech_stats"},
                    {"type": "callback", "text": "📋 Журнал событий", "payload": "/tech_logs"}
                ],
                [
                    {"type": "callback", "text": "⚙️ Настройка полей", "payload": "/custom_fields"},
                    {"type": "callback", "text": "🗺️ Зоны посещения", "payload": "/zones_mgmt"}
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
