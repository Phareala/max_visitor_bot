import os
import database
from maxbot_api_client_python.types import models

class AdminQueueScene:
    async def start(self, app):
        pass

    async def show_queue(self, n, idx=0):
        queue = database.get_admin_queue()
        total = len(queue)
        
        if total == 0:
            n.state_manager.update_state_data(n.state_id, {"step": "idle"})
            buttons = [[{"type": "callback", "text": "◀️ В меню", "payload": "/menu"}]]
            await n.reply_with_keyboard("📥 **Очередь заявок**\n\nВ данный момент активных заявок на рассмотрении нет.", "markdown", buttons)
            return

        # Constrain index
        if idx < 0:
            idx = 0
        if idx >= total:
            idx = total - 1

        req = queue[idx]
        
        n.state_manager.update_state_data(n.state_id, {
            "step": "browsing",
            "idx": idx,
            "requests": queue
        })

        custom_fields = database.get_request_custom_fields(req['request_id'])
        cf_text = ""
        for k, v in custom_fields.items():
            cf_text += f"📋 **{k}:** {v}\n"

        card_text = (
            f"📥 **Очередь заявок на рассмотрении** (Заявка {idx+1} из {total}):\n\n"
            f"🎫 **Номер:** `#{req['request_id']}`\n"
            f"👤 **ФИО гостя:** {req['visitor_name']}\n"
            f"📅 **Дата визита:** {req['visit_date']}\n"
            f"🕒 **Время визита:** {req['visit_time']}\n"
            f"🚪 **Зона посещения:** {req['visit_zone']}\n"
            f"🎯 **Цель визита:** {req['visit_purpose']}\n"
        )
        if cf_text:
            card_text += cf_text
            
        card_text += f"👤 **Инициатор:** {req['initiator_name'] or 'Неизвестно'} (ID: {req['initiator_id']})"

        buttons = [
            [
                {"type": "callback", "text": "✅ Согласовать", "payload": f"/admin_approve_{req['request_id']}"},
                {"type": "callback", "text": "❌ Отклонить", "payload": f"/admin_reject_prompt_{req['request_id']}"}
            ],
            [
                {"type": "callback", "text": "❓ Запрос уточнения", "payload": f"/admin_clarify_prompt_{req['request_id']}"}
            ]
        ]

        # Add navigation buttons if total > 1
        nav_row = []
        if idx > 0:
            nav_row.append({"type": "callback", "text": "◀️ Предыдущая", "payload": "/admin_prev"})
        if idx < total - 1:
            nav_row.append({"type": "callback", "text": "▶️ Следующая", "payload": "/admin_next"})
        
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

        # Handle menu action
        if text == "/menu":
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        # Queue navigation
        if text == "/admin_prev":
            await self.show_queue(n, idx - 1)
            return
        elif text == "/admin_next":
            await self.show_queue(n, idx + 1)
            return
        elif text == "/admin_queue":
            await self.show_queue(n, idx)
            return

        # Approve action
        if text.startswith("/admin_approve_"):
            req_id = int(text.split("_")[2])
            req = database.get_request(req_id)
            if req:
                admin_id = str(n.sender_id())
                database.update_request_status(req_id, "approved", admin_id, "Согласовано администратором")
                await n.reply(f"✅ Заявка `#{req_id}` успешно согласована.")
                
                # Notify initiator
                notify_text = (
                    f"🔔 **Ваша заявка №{req_id} одобрена!**\n\n"
                    f"👤 Гость: {req['visitor_name']}\n"
                    f"📅 Дата визита: {req['visit_date']}\n"
                    f"🕒 Время визита: {req['visit_time']}\n"
                    f"🚪 Корпус/Зона: {req['visit_zone']}"
                )
                await self.send_user_notification(n, req["initiator_id"], notify_text)
            
            await self.show_queue(n, idx)
            return

        # Reject prompt
        if text.startswith("/admin_reject_prompt_"):
            req_id = int(text.split("_")[3])
            n.state_manager.update_state_data(n.state_id, {
                "step": "reject_reason",
                "target_req_id": req_id
            })
            
            reasons = [
                {"type": "callback", "text": "❓ Цель визита не ясна", "payload": f"/admin_reject_reason_{req_id}_1"},
                {"type": "callback", "text": "🚪 Указанная зона закрыта", "payload": f"/admin_reject_reason_{req_id}_2"},
                {"type": "callback", "text": "❌ Введены некорректные данные", "payload": f"/admin_reject_reason_{req_id}_3"}
            ]
            
            buttons = [[r] for r in reasons]
            buttons.append([{"type": "callback", "text": "❌ Отмена", "payload": "/admin_queue"}])
            
            await n.reply_with_keyboard(
                f"❌ **Отклонение заявки #{req_id}**\n\nПожалуйста, выберите причину отказа из списка:",
                "markdown",
                buttons
            )
            return

        # Reject reason selected
        if text.startswith("/admin_reject_reason_"):
            parts = text.split("_")
            req_id = int(parts[3])
            reason_idx = int(parts[4])
            
            reasons_map = {
                1: "Цель визита не ясна",
                2: "Указанная зона закрыта для посещения",
                3: "Введены некорректные данные в заявке"
            }
            reason = reasons_map.get(reason_idx, "Другая причина")
            
            n.state_manager.update_state_data(n.state_id, {
                "step": "reject_comment",
                "target_req_id": req_id,
                "reason": reason
            })
            
            buttons = [[{"type": "callback", "text": "⏭️ Пропустить комментарий", "payload": "/admin_reject_skip_comment"}]]
            await n.reply_with_keyboard(
                "✍️ Вы можете ввести краткий комментарий к отказу (или нажать кнопку ниже, чтобы пропустить):",
                "markdown",
                buttons
            )
            return

        # Skip comment or process comment
        if step == "reject_comment":
            req_id = state_data["target_req_id"]
            reason = state_data["reason"]
            admin_id = str(n.sender_id())
            
            comment = None
            if text != "/admin_reject_skip_comment":
                comment = text.strip()
                
            database.update_request_status(req_id, "rejected", admin_id, comment, reason)
            await n.reply(f"❌ Заявка `#{req_id}` отклонена.")
            
            # Notify initiator
            notify_text = (
                f"🔕 **Ваша заявка №{req_id} отклонена.**\n\n"
                f"• Причина: {reason}\n"
            )
            if comment:
                notify_text += f"• Комментарий: {comment}"
                
            await self.send_user_notification(n, state_data["target_req_id"], notify_text)
            
            await self.show_queue(n, idx)
            return

        # Clarification prompt
        if text.startswith("/admin_clarify_prompt_"):
            req_id = int(text.split("_")[3])
            n.state_manager.update_state_data(n.state_id, {
                "step": "clarification_question",
                "target_req_id": req_id
            })
            
            buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/admin_queue"}]]
            await n.reply_with_keyboard(
                f"❓ **Запрос уточнения по заявке #{req_id}**\n\n"
                "Пожалуйста, напишите сообщение для инициатора с вопросами по его визиту:",
                "markdown",
                buttons
            )
            return

        # Process clarification question text
        if step == "clarification_question":
            req_id = state_data["target_req_id"]
            admin_id = str(n.sender_id())
            question_text = text.strip()
            
            req = database.get_request(req_id)
            if req:
                database.set_clarification_question(req_id, question_text, admin_id)
                await n.reply(f"📨 Запрос уточнения отправлен инициатору заявки `#{req_id}`.")
                
                # Notify initiator
                notify_text = (
                    f"⚠️ **По вашей заявке №{req_id} требуется уточнение.**\n\n"
                    f"💬 Вопрос службы безопасности:\n"
                    f"_{question_text}_\n\n"
                    f"Пожалуйста, ответьте на это сообщение, чтобы вернуть заявку на рассмотрение."
                )
                await self.send_user_notification(n, req["initiator_id"], notify_text)
            
            await self.show_queue(n, idx)
            return

        await n.reply("Неизвестное действие. Используйте кнопки для управления очередью.")
        await self.show_queue(n, idx)

    async def send_user_notification(self, n, target_user_id, text):
        try:
            req = models.SendMessageReq(
                user_id=int(target_user_id),
                text=text,
                format="markdown"
            )
            await n.bot.api.messages.send_message_async(req)
        except Exception as e:
            # Silence error or print for diagnostics (avoid blocking bot execution)
            print(f"Error sending notification to {target_user_id}: {e}")
