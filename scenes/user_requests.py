import os
import database
from maxbot_api_client_python.types import models

STATUS_MAP = {
    "draft": "Черновик 📝",
    "review": "На рассмотрении 📥",
    "clarification": "Требуется уточнение ⚠️",
    "approved": "Согласована ✅",
    "rejected": "Отклонена ❌",
    "closed": "Закрыта 🔒",
    "canceled": "Отменена 🔕"
}

class UserRequestsScene:
    async def start(self, app):
        pass

    async def show_user_requests(self, n, idx=0):
        user_id = str(n.sender_id())
        user_requests = database.get_user_requests(user_id)
        total = len(user_requests)

        if total == 0:
            n.state_manager.update_state_data(n.state_id, {"step": "idle"})
            buttons = [[{"type": "callback", "text": "◀️ В меню", "payload": "/menu"}]]
            await n.reply_with_keyboard("🗂 **Ваши заявки**\n\nУ вас пока нет созданных заявок на пропуска.", "markdown", buttons)
            return

        if idx < 0:
            idx = 0
        if idx >= total:
            idx = total - 1

        req = user_requests[idx]
        
        n.state_manager.update_state_data(n.state_id, {
            "step": "browsing",
            "idx": idx,
            "requests": user_requests
        })

        status_text = STATUS_MAP.get(req["status"], req["status"])
        card_text = (
            f"🗂 **Ваши заявки на пропуск** (Заявка {idx+1} из {total}):\n\n"
            f"🎫 **Номер:** `#{req['request_id']}`\n"
            f"👤 **ФИО гостя:** {req['visitor_name']}\n"
            f"📅 **Дата визита:** {req['visit_date']}\n"
            f"🕒 **Время визита:** {req['visit_time']}\n"
            f"🚪 **Зона посещения:** {req['visit_zone']}\n"
            f"🎯 **Цель визита:** {req['visit_purpose']}\n"
            f"🏷️ **Статус:** {status_text}\n"
        )

        if req["status"] == "clarification":
            card_text += f"\n💬 **Запрос уточнения от ИБ:**\n_{req['clarification_question']}_\n"
        elif req["status"] == "rejected":
            card_text += (
                f"\n• **Причина отказа:** {req['rejection_reason']}\n"
            )
            if req["admin_comment"]:
                card_text += f"• **Комментарий ИБ:** {req['admin_comment']}\n"
        elif req["status"] == "approved" and req["admin_comment"]:
            card_text += f"\n• **Комментарий ИБ:** {req['admin_comment']}\n"

        buttons = []
        action_row = []

        # Cancel button (available before final decision)
        if req["status"] in ["draft", "review", "clarification"]:
            action_row.append({"type": "callback", "text": "❌ Отменить заявку", "payload": f"/user_cancel_{req['request_id']}"})
        
        # Clarification answer button
        if req["status"] == "clarification":
            action_row.append({"type": "callback", "text": "✍️ Ответить", "payload": f"/user_reply_prompt_{req['request_id']}"})

        # Close button (for admins and tech admins on approved/rejected requests)
        admin_ids = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]
        tech_admin_ids = [x.strip() for x in os.getenv("TECH_ADMIN_USER_IDS", "").split(",") if x.strip()]
        role = database.get_user_role(user_id, admin_ids, tech_admin_ids)
        
        if role in ["admin", "tech_admin"] and req["status"] in ["approved", "rejected"]:
            action_row.append({"type": "callback", "text": "🔒 Закрыть заявку", "payload": f"/user_close_{req['request_id']}"})

        if action_row:
            buttons.append(action_row)

        # Navigation row
        nav_row = []
        if idx > 0:
            nav_row.append({"type": "callback", "text": "◀️ Предыдущая", "payload": "/user_prev"})
        if idx < total - 1:
            nav_row.append({"type": "callback", "text": "▶️ Следующая", "payload": "/user_next"})
        
        if nav_row:
            buttons.append(nav_row)

        buttons.append([{"type": "callback", "text": "◀️ Главное меню", "payload": "/menu"}])

        await n.reply_with_keyboard(card_text, "markdown", buttons)

    async def execute(self, n):
        is_callback = n.type() == "message_callback"
        if is_callback:
            await n.answer_callback("")

        try:
            text = n.text()
        except ValueError:
            text = None

        if not text:
            await n.reply("Пожалуйста, отправьте текстовый ответ или воспользуйтесь кнопками.")
            return

        state_data = n.state_manager.get_state_data(n.state_id)
        if not state_data:
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        step = state_data.get("step", "idle")
        idx = state_data.get("idx", 0)

        # Menu navigation
        if text == "/menu":
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        # List navigation
        if text == "/user_prev":
            await self.show_user_requests(n, idx - 1)
            return
        elif text == "/user_next":
            await self.show_user_requests(n, idx + 1)
            return
        elif text == "/my_requests":
            await self.show_user_requests(n, idx)
            return

        # Cancel request
        if text.startswith("/user_cancel_"):
            req_id = int(text.split("_")[2])
            req = database.get_request(req_id)
            if req and req["status"] in ["draft", "review", "clarification"]:
                user_id = str(n.sender_id())
                database.update_request_status(req_id, "canceled", user_id, "Отменено инициатором")
                await n.reply(f"🔕 Заявка `#{req_id}` отменена.")
            else:
                await n.reply("❌ Невозможно отменить эту заявку: по ней уже принято окончательное решение.")
            await self.show_user_requests(n, idx)
            return

        # Close request (admin only)
        if text.startswith("/user_close_"):
            req_id = int(text.split("_")[2])
            req = database.get_request(req_id)
            user_id = str(n.sender_id())
            
            admin_ids = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]
            tech_admin_ids = [x.strip() for x in os.getenv("TECH_ADMIN_USER_IDS", "").split(",") if x.strip()]
            role = database.get_user_role(user_id, admin_ids, tech_admin_ids)
            
            if role in ["admin", "tech_admin"]:
                if req and req["status"] in ["approved", "rejected"]:
                    database.update_request_status(req_id, "closed", user_id, "Закрыто администратором")
                    await n.reply(f"🔒 Заявка `#{req_id}` успешно закрыта.")
                else:
                    await n.reply("❌ Заявку можно закрыть только после согласования или отклонения.")
            else:
                await n.reply("⛔ Закрытие заявок доступно только администраторам.")
            await self.show_user_requests(n, idx)
            return

        # Reply prompt
        if text.startswith("/user_reply_prompt_"):
            req_id = int(text.split("_")[3])
            n.state_manager.update_state_data(n.state_id, {
                "step": "clarification_reply",
                "target_req_id": req_id,
                "idx": idx
            })
            
            buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/my_requests"}]]
            await n.reply_with_keyboard(
                f"✍️ **Ответ на уточнение по заявке #{req_id}**\n\n"
                "Пожалуйста, введите ваш ответ на вопросы службы безопасности в текстовом поле:",
                "markdown",
                buttons
            )
            return

        # Process clarification reply text
        if step == "clarification_reply":
            req_id = state_data["target_req_id"]
            user_id = str(n.sender_id())
            answer_text = text.strip()
            
            req = database.get_request(req_id)
            if req:
                database.submit_clarification_answer(req_id, answer_text, user_id)
                await n.reply("✅ Ваш ответ успешно отправлен. Заявка возвращена на рассмотрение в службу безопасности.")
                
                # Notify administrators
                admin_ids = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]
                notify_text = (
                    f"🔔 **Инициатор ответил на запрос уточнения по заявке №{req_id}!**\n\n"
                    f"• Гость: {req['visitor_name']}\n"
                    f"• Ответ инициатора:\n"
                    f"_{answer_text}_"
                )
                for admin_id in admin_ids:
                    await self.send_user_notification(n, admin_id, notify_text)
            
            await self.show_user_requests(n, idx)
            return

        await n.reply("Неизвестное действие. Используйте кнопки для управления заявками.")
        await self.show_user_requests(n, idx)

    async def send_user_notification(self, n, target_user_id, text):
        try:
            req = models.SendMessageReq(
                user_id=int(target_user_id),
                text=text,
                format="markdown"
            )
            await n.bot.api.messages.send_message_async(req)
        except Exception as e:
            # Silence notification errors
            print(f"Error sending notification to {target_user_id}: {e}")
