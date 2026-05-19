import os
import re
from datetime import datetime, timedelta
import database

class CreatePassScene:
    async def start(self, app):
        pass

    async def start_wizard(self, n):
        n.state_manager.update_state_data(n.state_id, {
            "step": "visitor_name",
            "wizard_data": {},
            "edit_mode": False
        })
        buttons = [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
        await n.reply_with_keyboard(
            "📋 **Оформление разового пропуска (1/5)**\n\n"
            "Пожалуйста, введите **ФИО гостя** (свободный ввод, только буквы):",
            "markdown",
            buttons
        )

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
        if not state_data or "step" not in state_data:
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        step = state_data["step"]
        wizard_data = state_data.get("wizard_data", {})
        edit_mode = state_data.get("edit_mode", False)

        # Handle cancel action
        if text == "/cancel_wizard":
            # Delete draft if any, but since we didn't save yet it is fine
            # We just go back to main menu
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        # Handle field edit commands from summary screen
        if text.startswith("/edit_"):
            field = text.split("_", 1)[1]
            n.state_manager.update_state_data(n.state_id, {
                "step": field,
                "edit_mode": True
            })
            
            cancel_btn = [[{"type": "callback", "text": "❌ Назад к сводке", "payload": "/back_to_summary"}]]
            
            if field == "visitor_name":
                await n.reply_with_keyboard("Введите новое **ФИО гостя**:", "markdown", cancel_btn)
            elif field == "visit_date":
                await n.reply_with_keyboard(
                    "Выберите или введите новую **дату визита** (ДД.ММ.ГГГГ):",
                    "markdown",
                    self.get_date_buttons() + cancel_btn
                )
            elif field == "visit_time":
                await n.reply_with_keyboard(
                    "Выберите или введите новое **время визита** (ЧЧ:ММ):",
                    "markdown",
                    self.get_time_buttons() + cancel_btn
                )
            elif field == "visit_zone":
                await n.reply_with_keyboard(
                    "Выберите новую **зону/корпус посещения**:",
                    "markdown",
                    self.get_zone_buttons() + cancel_btn
                )
            elif field == "visit_purpose":
                await n.reply_with_keyboard("Введите новую **цель визита**:", "markdown", cancel_btn)
            return

        # Back to summary button
        if text == "/back_to_summary":
            n.state_manager.update_state_data(n.state_id, {
                "step": "summary",
                "edit_mode": False
            })
            await self.show_summary(n, wizard_data)
            return

        # Handle confirm submission
        if text == "/confirm_wizard" and step == "summary":
            user_id = str(n.sender_id())
            # Save request as draft first
            req_id = database.create_request(
                initiator_id=user_id,
                visitor_name=wizard_data["visitor_name"],
                visit_date=wizard_data["visit_date"],
                visit_time=wizard_data["visit_time"],
                visit_zone=wizard_data["visit_zone"],
                visit_purpose=wizard_data["visit_purpose"]
            )
            
            # Immediately transition to "review" status
            database.update_request_status(req_id, "review", user_id)
            
            await n.reply(
                f"✅ **Заявка оформлена!**\n\n"
                f"• Номер заявки: `#{req_id}`\n"
                f"• Текущий статус: `На рассмотрении`\n\n"
                f"Заявка передана в службу безопасности. Мы уведомим вас при изменении статуса."
            )
            
            # Go back to main menu
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        # Process standard step-by-step inputs
        if step == "visitor_name":
            # Validation: not empty, not only digits
            cleaned = text.strip()
            if not cleaned or cleaned.isdigit() or len(cleaned) < 2:
                buttons = [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
                await n.reply_with_keyboard(
                    "❌ **Некорректное ФИО!**\n\n"
                    "ФИО гостя не должно быть пустым, состоять только из цифр или быть слишком коротким.\n"
                    "Пожалуйста, введите ФИО гостя повторно:",
                    "markdown",
                    buttons
                )
                return
            
            wizard_data["visitor_name"] = cleaned
            
            if edit_mode:
                n.state_manager.update_state_data(n.state_id, {"step": "summary", "edit_mode": False})
                await self.show_summary(n, wizard_data)
            else:
                n.state_manager.update_state_data(n.state_id, {
                    "step": "visit_date",
                    "wizard_data": wizard_data
                })
                await n.reply_with_keyboard(
                    "📅 **Оформление разового пропуска (2/5)**\n\n"
                    "Выберите или введите дату визита в формате ДД.ММ.ГГГГ (например, `25.12.2026`):",
                    "markdown",
                    self.get_date_buttons() + [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
                )

        elif step == "visit_date":
            # Calculate quick date options
            today = datetime.now()
            quick_dates = {
                "сегодня": today.strftime("%d.%m.%Y"),
                "завтра": (today + timedelta(days=1)).strftime("%d.%m.%Y"),
                "послезавтра": (today + timedelta(days=2)).strftime("%d.%m.%Y")
            }
            
            input_val = text.strip().lower()
            date_str = None
            
            if input_val in quick_dates:
                date_str = quick_dates[input_val]
            else:
                # Parse manual format
                # Expecting DD.MM.YYYY
                match = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", text.strip())
                if match:
                    try:
                        parsed_date = datetime.strptime(text.strip(), "%d.%m.%Y")
                        # Validate that it is not in the past (only date part)
                        today_date = datetime(today.year, today.month, today.day)
                        if parsed_date >= today_date:
                            date_str = text.strip()
                    except ValueError:
                        pass

            if not date_str:
                cancel_btn = "/back_to_summary" if edit_mode else "/cancel_wizard"
                btn_text = "❌ Назад к сводке" if edit_mode else "❌ Отменить"
                await n.reply_with_keyboard(
                    "❌ **Некорректная дата!**\n\n"
                    "Дата должна быть в формате ДД.ММ.ГГГГ и не может быть в прошлом.\n"
                    "Пожалуйста, выберите или введите дату визита:",
                    "markdown",
                    self.get_date_buttons() + [[{"type": "callback", "text": btn_text, "payload": cancel_btn}]]
                )
                return

            wizard_data["visit_date"] = date_str
            
            if edit_mode:
                n.state_manager.update_state_data(n.state_id, {"step": "summary", "edit_mode": False})
                await self.show_summary(n, wizard_data)
            else:
                n.state_manager.update_state_data(n.state_id, {
                    "step": "visit_time",
                    "wizard_data": wizard_data
                })
                await n.reply_with_keyboard(
                    "🕒 **Оформление разового пропуска (3/5)**\n\n"
                    "Выберите или введите ориентировочное время визита (в формате ЧЧ:ММ):",
                    "markdown",
                    self.get_time_buttons() + [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
                )

        elif step == "visit_time":
            time_val = text.strip()
            # Validate time format loosely (just check HH:MM or similar)
            # Accept any input for flexibility, but warn if format is completely invalid
            if not re.match(r"^\d{2}:\d{2}$", time_val):
                # We can still accept it but suggest clean input, or enforce formatting
                # Let's enforce formatting for consistency
                cancel_btn = "/back_to_summary" if edit_mode else "/cancel_wizard"
                btn_text = "❌ Назад к сводке" if edit_mode else "❌ Отменить"
                await n.reply_with_keyboard(
                    "❌ **Некорректное время!**\n\n"
                    "Пожалуйста, введите время в формате ЧЧ:ММ (например, `14:30`):",
                    "markdown",
                    self.get_time_buttons() + [[{"type": "callback", "text": btn_text, "payload": cancel_btn}]]
                )
                return

            wizard_data["visit_time"] = time_val
            
            if edit_mode:
                n.state_manager.update_state_data(n.state_id, {"step": "summary", "edit_mode": False})
                await self.show_summary(n, wizard_data)
            else:
                n.state_manager.update_state_data(n.state_id, {
                    "step": "visit_zone",
                    "wizard_data": wizard_data
                })
                await n.reply_with_keyboard(
                    "🚪 **Оформление разового пропуска (4/5)**\n\n"
                    "Выберите зону посещения:",
                    "markdown",
                    self.get_zone_buttons() + [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
                )

        elif step == "visit_zone":
            zone_val = text.strip()
            if not zone_val:
                zone_val = "Главный корпус"
            
            wizard_data["visit_zone"] = zone_val
            
            if edit_mode:
                n.state_manager.update_state_data(n.state_id, {"step": "summary", "edit_mode": False})
                await self.show_summary(n, wizard_data)
            else:
                n.state_manager.update_state_data(n.state_id, {
                    "step": "visit_purpose",
                    "wizard_data": wizard_data
                })
                await n.reply_with_keyboard(
                    "🎯 **Оформление разового пропуска (5/5)**\n\n"
                    "Пожалуйста, введите **цель вашего визита** (свободный ввод):",
                    "markdown",
                    [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
                )

        elif step == "visit_purpose":
            purpose_val = text.strip()
            if not purpose_val or len(purpose_val) < 3:
                cancel_btn = "/back_to_summary" if edit_mode else "/cancel_wizard"
                btn_text = "❌ Назад к сводке" if edit_mode else "❌ Отменить"
                await n.reply_with_keyboard(
                    "❌ **Некорректная цель визита!**\n\n"
                    "Цель визита не должна быть пустой или слишком короткой.\n"
                    "Пожалуйста, введите цель визита:",
                    "markdown",
                    [[{"type": "callback", "text": btn_text, "payload": cancel_btn}]]
                )
                return

            wizard_data["visit_purpose"] = purpose_val
            
            n.state_manager.update_state_data(n.state_id, {
                "step": "summary",
                "edit_mode": False,
                "wizard_data": wizard_data
            })
            await self.show_summary(n, wizard_data)

    async def show_summary(self, n, data):
        summary_text = (
            "📝 **Сводка заявки на пропуск**\n\n"
            f"👤 **ФИО гостя:** {data['visitor_name']}\n"
            f"📅 **Дата визита:** {data['visit_date']}\n"
            f"🕒 **Время визита:** {data['visit_time']}\n"
            f"🚪 **Зона посещения:** {data['visit_zone']}\n"
            f"🎯 **Цель визита:** {data['visit_purpose']}\n\n"
            "Пожалуйста, проверьте все данные. Для редактирования конкретного поля нажмите соответствующую кнопку."
        )

        buttons = [
            [
                {"type": "callback", "text": "✅ Подтвердить и отправить", "payload": "/confirm_wizard"}
            ],
            [
                {"type": "callback", "text": "👤 Изменить ФИО", "payload": "/edit_visitor_name"},
                {"type": "callback", "text": "📅 Изменить Дату", "payload": "/edit_visit_date"}
            ],
            [
                {"type": "callback", "text": "🕒 Изменить Время", "payload": "/edit_visit_time"},
                {"type": "callback", "text": "🚪 Изменить Зону", "payload": "/edit_visit_zone"}
            ],
            [
                {"type": "callback", "text": "🎯 Изменить Цель", "payload": "/edit_visit_purpose"},
                {"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}
            ]
        ]

        await n.reply_with_keyboard(summary_text, "markdown", buttons)

    def get_date_buttons(self):
        return [
            [
                {"type": "callback", "text": "Сегодня", "payload": "Сегодня"},
                {"type": "callback", "text": "Завтра", "payload": "Завтра"},
                {"type": "callback", "text": "Послезавтра", "payload": "Послезавтра"}
            ]
        ]

    def get_time_buttons(self):
        return [
            [
                {"type": "callback", "text": "09:00", "payload": "09:00"},
                {"type": "callback", "text": "10:00", "payload": "10:00"},
                {"type": "callback", "text": "12:00", "payload": "12:00"}
            ],
            [
                {"type": "callback", "text": "14:00", "payload": "14:00"},
                {"type": "callback", "text": "16:00", "payload": "16:00"},
                {"type": "callback", "text": "18:00", "payload": "18:00"}
            ]
        ]

    def get_zone_buttons(self):
        return [
            [
                {"type": "callback", "text": "Корпус А", "payload": "Корпус А"},
                {"type": "callback", "text": "Корпус Б", "payload": "Корпус Б"}
            ],
            [
                {"type": "callback", "text": "Лабораторная зона", "payload": "Лабораторная зона"},
                {"type": "callback", "text": "Конференц-зал", "payload": "Конференц-зал"}
            ]
        ]
