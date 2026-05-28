import os
import re
from datetime import datetime, timedelta
import database
import notifications

# Порог накопления очереди — предупреждаем администраторов, когда заявок накопится столько
QUEUE_ALERT_THRESHOLD = 5


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

        # Обработка отмены
        if text == "/cancel_wizard":
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        # Обработка команд редактирования стандартных полей с экрана сводки
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

        # Обработка команд редактирования кастомных полей с экрана сводки
        if text.startswith("/edit_cf_"):
            field_name = text.split("_", 2)[2]
            n.state_manager.update_state_data(n.state_id, {
                "step": f"editcf_{field_name}",
                "edit_mode": True
            })

            f_def = database.get_custom_field_by_name(field_name, wizard_data.get("visit_zone", ""))
            desc = f_def["description"] if f_def else f"Введите новое значение для {field_name}:"

            cancel_btn = [[{"type": "callback", "text": "❌ Назад к сводке", "payload": "/back_to_summary"}]]
            await n.reply_with_keyboard(desc, "markdown", cancel_btn)
            return

        # Кнопка возврата к сводке
        if text == "/back_to_summary":
            n.state_manager.update_state_data(n.state_id, {
                "step": "summary",
                "edit_mode": False
            })
            await self.show_summary(n, wizard_data)
            return

        # Обработка подтверждения и отправки заявки
        if text == "/confirm_wizard" and step == "summary":
            user_id = str(n.sender_id())
            # Сохраняем заявку как черновик
            req_id = database.create_request(
                initiator_id=user_id,
                visitor_name=wizard_data["visitor_name"],
                visit_date=wizard_data["visit_date"],
                visit_time=wizard_data["visit_time"],
                visit_zone=wizard_data["visit_zone"],
                visit_purpose=wizard_data["visit_purpose"]
            )

            # Сохраняем значения кастомных полей
            for name, val in wizard_data.get("custom_fields", {}).items():
                database.save_request_custom_field_value(req_id, name, val)

            # Сразу переводим в статус «На рассмотрении»
            database.update_request_status(req_id, "review", user_id)

            await n.reply(
                f"✅ **Заявка оформлена!**\n\n"
                f"• Номер заявки: `#{req_id}`\n"
                f"• Текущий статус: `На рассмотрении`\n\n"
                f"Заявка передана в службу безопасности. Мы уведомим вас при изменении статуса."
            )

            # Уведомляем администраторов ИБ о новой заявке
            await self._notify_admins_new_request(n, req_id, wizard_data)

            # Уведомляем об истёкших заявках (если срок вышел пока заполнялся мастер)
            await notifications.send_expiry_notifications(n)

            # Возвращаемся в главное меню
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        # Обработка изменений кастомных полей в режиме редактирования
        if step.startswith("editcf_"):
            field_name = step.split("_", 1)[1]
            val = text.strip()

            f_def = database.get_custom_field_by_name(field_name, wizard_data.get("visit_zone", ""))
            if f_def and f_def["is_required"] and not val:
                cancel_btn = [[{"type": "callback", "text": "❌ Назад к сводке", "payload": "/back_to_summary"}]]
                await n.reply_with_keyboard(
                    f"❌ **Это поле является обязательным!**\n\n"
                    f"{f_def['description']}",
                    "markdown",
                    cancel_btn
                )
                return

            if "custom_fields" not in wizard_data:
                wizard_data["custom_fields"] = {}
            wizard_data["custom_fields"][field_name] = val

            n.state_manager.update_state_data(n.state_id, {
                "step": "summary",
                "edit_mode": False
            })
            await self.show_summary(n, wizard_data)
            return

        # Обработка пошагового ввода стандартных полей
        if step == "visitor_name":
            # Валидация: не пустое, не только цифры
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
            # Вычисляем быстрые варианты дат
            today = datetime.now()
            today_date = datetime(today.year, today.month, today.day)
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
                # Парсинг вручную введённой даты в формате ДД.ММ.ГГГГ
                match = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", text.strip())
                if match:
                    try:
                        parsed_date = datetime.strptime(text.strip(), "%d.%m.%Y")
                        one_year_limit = today_date + timedelta(days=365)
                        if today_date <= parsed_date <= one_year_limit:
                            date_str = text.strip()
                    except ValueError:
                        pass

            if not date_str:
                cancel_btn = "/back_to_summary" if edit_mode else "/cancel_wizard"
                btn_text = "❌ Назад к сводке" if edit_mode else "❌ Отменить"
                await n.reply_with_keyboard(
                    "❌ **Некорректная дата!**\n\n"
                    "Дата должна быть в формате ДД.ММ.ГГГГ, не может быть в прошлом и не может быть более чем на 1 год вперед.\n"
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
            match = re.match(r"^([0-9]|0[0-9]|1[0-9]|2[0-3]):([0-5][0-9])$", time_val)
            if not match:
                cancel_btn = "/back_to_summary" if edit_mode else "/cancel_wizard"
                btn_text = "❌ Назад к сводке" if edit_mode else "❌ Отменить"
                await n.reply_with_keyboard(
                    "❌ **Некорректное время!**\n\n"
                    "Пожалуйста, введите время в диапазоне от 00:00 до 23:59 в формате ЧЧ:ММ (например, `14:30` или `9:00`):",
                    "markdown",
                    self.get_time_buttons() + [[{"type": "callback", "text": btn_text, "payload": cancel_btn}]]
                )
                return

            hour = int(match.group(1))
            minute = int(match.group(2))
            wizard_data["visit_time"] = f"{hour:02d}:{minute:02d}"

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
                    "Выберите зону посещения (корпус):",
                    "markdown",
                    self.get_zone_buttons() + [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
                )

        elif step == "visit_zone":
            zones = database.get_zones()
            zone_val = text.strip()
            if zone_val not in zones:
                cancel_btn = "/back_to_summary" if edit_mode else "/cancel_wizard"
                btn_text = "❌ Назад к сводке" if edit_mode else "❌ Отменить"
                await n.reply_with_keyboard(
                    "❌ **Некорректная зона посещения!**\n\n"
                    "Пожалуйста, выберите одну из предложенных зон с помощью кнопок:",
                    "markdown",
                    self.get_zone_buttons() + [[{"type": "callback", "text": btn_text, "payload": cancel_btn}]]
                )
                return

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

            if edit_mode:
                n.state_manager.update_state_data(n.state_id, {"step": "summary", "edit_mode": False})
                await self.show_summary(n, wizard_data)
            else:
                # Динамическая проверка настроенных кастомных полей для выбранной зоны
                custom_fields = database.get_custom_fields(wizard_data["visit_zone"])
                if custom_fields:
                    n.state_manager.update_state_data(n.state_id, {
                        "step": f"custom_{custom_fields[0]['field_id']}",
                        "wizard_data": wizard_data,
                        "custom_fields_to_ask": [f["field_id"] for f in custom_fields],
                        "current_cf_idx": 0
                    })
                    first_f = custom_fields[0]
                    buttons = [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
                    await n.reply_with_keyboard(
                        f"📋 **Заполнение дополнительных полей (1/{len(custom_fields)})**\n\n"
                        f"{first_f['description']}",
                        "markdown",
                        buttons
                    )
                else:
                    n.state_manager.update_state_data(n.state_id, {
                        "step": "summary",
                        "edit_mode": False,
                        "wizard_data": wizard_data
                    })
                    await self.show_summary(n, wizard_data)

        # Обработка шагов сбора кастомных полей
        elif step.startswith("custom_"):
            field_id = int(step.split("_")[1])
            custom_fields_to_ask = state_data["custom_fields_to_ask"]
            current_idx = state_data["current_cf_idx"]

            f_def = database.get_custom_field(field_id)
            val = text.strip()

            if f_def:
                if f_def["is_required"] and not val:
                    buttons = [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
                    await n.reply_with_keyboard(
                        f"❌ **Это поле обязательно для заполнения!**\n\n"
                        f"{f_def['description']}",
                        "markdown",
                        buttons
                    )
                    return

                if "custom_fields" not in wizard_data:
                    wizard_data["custom_fields"] = {}
                wizard_data["custom_fields"][f_def["field_name"]] = val

            next_idx = current_idx + 1
            if next_idx < len(custom_fields_to_ask):
                next_field_id = custom_fields_to_ask[next_idx]
                next_f_def = database.get_custom_field(next_field_id)
                n.state_manager.update_state_data(n.state_id, {
                    "step": f"custom_{next_field_id}",
                    "current_cf_idx": next_idx,
                    "wizard_data": wizard_data
                })
                buttons = [[{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}]]
                await n.reply_with_keyboard(
                    f"📋 **Заполнение дополнительных полей ({next_idx+1}/{len(custom_fields_to_ask)})**\n\n"
                    f"{next_f_def['description'] if next_f_def else 'Введите значение:'}",
                    "markdown",
                    buttons
                )
            else:
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
            f"🎯 **Цель визита:** {data['visit_purpose']}\n"
        )

        custom_fields = data.get("custom_fields", {})
        for name, val in custom_fields.items():
            summary_text += f"📋 **{name}:** {val}\n"

        summary_text += "\nПожалуйста, проверьте все данные. Для редактирования нажмите соответствующую кнопку."

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
                {"type": "callback", "text": "🎯 Изменить Цель", "payload": "/edit_visit_purpose"}
            ]
        ]

        custom_edit_row = []
        for name in custom_fields.keys():
            custom_edit_row.append({"type": "callback", "text": f"✏️ {name}", "payload": f"/edit_cf_{name}"})
            if len(custom_edit_row) == 2:
                buttons.append(custom_edit_row)
                custom_edit_row = []
        if custom_edit_row:
            buttons.append(custom_edit_row)

        buttons.append([{"type": "callback", "text": "❌ Отменить", "payload": "/cancel_wizard"}])

        await n.reply_with_keyboard(summary_text, "markdown", buttons)

    async def _notify_admins_new_request(self, n, req_id: int, wizard_data: dict):
        """Уведомляет всех администраторов ИБ о новой поступившей заявке."""
        admin_ids = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]
        if not admin_ids:
            return

        queue = database.get_admin_queue()
        queue_size = len(queue)

        notify_text = (
            f"🔔 **Новая заявка на пропуск №{req_id}!**\n\n"
            f"👤 Гость: {wizard_data['visitor_name']}\n"
            f"📅 Дата визита: {wizard_data['visit_date']}\n"
            f"🕒 Время визита: {wizard_data['visit_time']}\n"
            f"🚪 Корпус/Зона: {wizard_data['visit_zone']}\n"
            f"🎯 Цель визита: {wizard_data['visit_purpose']}"
        )

        if queue_size >= QUEUE_ALERT_THRESHOLD:
            notify_text += (
                f"\n\n⚠️ **Внимание!** В очереди накопилось **{queue_size}** заявок, "
                f"ожидающих рассмотрения."
            )

        await notifications.notify_admins(n, admin_ids, notify_text)

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
        zones = database.get_zones()
        return [[{"type": "callback", "text": database.zone_btn_label(z), "payload": z}] for z in zones]
