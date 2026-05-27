import os
import database
from maxbot_api_client_python import utils

# Kept for reference / seed data only — runtime uses database.get_zones()
DEFAULT_ZONES = database.DEFAULT_ZONES

# Backward-compat alias used in a few places that import CAMPUSES
def get_campuses():
    """Return current active zones from the database."""
    return database.get_zones()

# Module-level CAMPUSES is kept for any legacy imports; refreshed each call via get_campuses()
CAMPUSES = DEFAULT_ZONES  # initial fallback; scenes should call database.get_zones() directly


class CustomFieldsMgmtScene:
    async def start(self, app):
        pass

    async def show_choose_zone(self, n):
        n.state_manager.update_state_data(n.state_id, {
            "step": "choose_zone"
        })
        campuses = database.get_zones()
        buttons = []
        for campus in campuses:
            buttons.append([{"type": "callback", "text": database.zone_btn_label(campus), "payload": f"/cf_zone_{campus}"}])
        buttons.append([{"type": "callback", "text": "🌐 Все корпуса", "payload": "/cf_zone_Все корпуса"}])
        buttons.append([{"type": "callback", "text": "◀️ В меню", "payload": "/menu"}])

        await n.reply_with_keyboard(
            "⚙️ **Настройка кастомных полей**\n\n"
            "Выберите зону посещения (корпус) для настройки дополнительных полей заявок:",
            "markdown",
            buttons
        )

    async def show_zone_menu(self, n, zone_name):
        n.state_manager.update_state_data(n.state_id, {
            "step": "zone_menu",
            "zone_name": zone_name
        })
        fields = database.get_custom_fields_by_zone_exact(zone_name)

        text = f"⚙️ **Настройка полей для: {zone_name}**\n\n"
        if not fields:
            text += "Для этого корпуса пока нет кастомных полей."
        else:
            text += "Существующие дополнительные поля:\n"
            for i, f in enumerate(fields, 1):
                req_text = "Обязательное" if f["is_required"] else "Необязательное"
                text += f"{i}. **{f['field_name']}** ({req_text})\n"
                if f["description"]:
                    text += f"   _Подсказка:_ {f['description']}\n"

        buttons = []
        for f in fields:
            buttons.append([{"type": "callback", "text": f"🗑 Удалить '{f['field_name']}'", "payload": f"/cf_del_{f['field_id']}"}])

        buttons.append([{"type": "callback", "text": "➕ Добавить поле", "payload": "/cf_add"}])
        buttons.append([{"type": "callback", "text": "◀️ Назад к выбору зон", "payload": "/cf_back"}])

        await n.reply_with_keyboard(text, "markdown", buttons)

    async def execute(self, n):
        is_callback = n.type() == "message_callback"
        if is_callback:
            await n.answer_callback("")

        try:
            text = n.text()
        except ValueError:
            text = None

        if not text:
            await n.reply("Пожалуйста, используйте кнопки или введите текст.")
            return

        state_data = n.state_manager.get_state_data(n.state_id)
        if not state_data:
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        step = state_data.get("step")
        zone_name = state_data.get("zone_name")

        if text == "/cf_back":
            await self.show_choose_zone(n)
            return

        if text == "/menu":
            from scenes.main_menu import MainMenuScene
            menu_scene = MainMenuScene()
            n.activate_next_scene(menu_scene)
            await menu_scene.send_main_menu(n)
            return

        if step == "choose_zone":
            if text.startswith("/cf_zone_"):
                selected_zone = text.split("_", 2)[2]
                await self.show_zone_menu(n, selected_zone)
            else:
                await self.show_choose_zone(n)
            return

        elif step == "zone_menu":
            if text == "/cf_add":
                n.state_manager.update_state_data(n.state_id, {
                    "step": "add_field_name",
                    "zone_name": zone_name
                })
                buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/cf_cancel_add"}]]
                await n.reply_with_keyboard(
                    "✏️ **Добавление кастомного поля**\n\n"
                    "Введите **название поля** (например, `Гос. номер автомобиля`):",
                    "markdown",
                    buttons
                )
            elif text.startswith("/cf_del_"):
                field_id = int(text.split("_")[2])
                n.state_manager.update_state_data(n.state_id, {
                    "step": "confirm_delete",
                    "zone_name": zone_name,
                    "delete_field_id": field_id
                })
                buttons = [
                    [
                        {"type": "callback", "text": "💥 Да, удалить", "payload": "/cf_confirm_del"},
                        {"type": "callback", "text": "❌ Отмена", "payload": "/cf_cancel_del"}
                    ]
                ]
                await n.reply_with_keyboard(
                    "⚠️ **Подтвердите удаление**\n\nВы уверены, что хотите удалить это кастомное поле?",
                    "markdown",
                    buttons
                )
            else:
                await self.show_zone_menu(n, zone_name)
            return

        elif step == "add_field_name":
            if text == "/cf_cancel_add":
                await self.show_zone_menu(n, zone_name)
                return

            field_name = text.strip()
            if not field_name or len(field_name) < 2:
                await n.reply("❌ Название поля слишком короткое. Введите другое название:")
                return

            n.state_manager.update_state_data(n.state_id, {
                "step": "add_field_desc",
                "new_field_name": field_name,
                "zone_name": zone_name
            })
            buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/cf_cancel_add"}]]
            await n.reply_with_keyboard(
                f"✏️ **Добавление поля '{field_name}'**\n\n"
                "Введите **подсказку / вопрос** для пользователя при заполнении этого поля "
                "(например, `Пожалуйста, введите гос. номер автомобиля (например, А123АА777):`):",
                "markdown",
                buttons
            )

        elif step == "add_field_desc":
            if text == "/cf_cancel_add":
                await self.show_zone_menu(n, zone_name)
                return

            field_desc = text.strip()
            if not field_desc or len(field_desc) < 3:
                await n.reply("❌ Подсказка слишком короткая. Введите другую подсказку:")
                return

            n.state_manager.update_state_data(n.state_id, {
                "step": "add_field_req",
                "new_field_desc": field_desc,
                "new_field_name": state_data["new_field_name"],
                "zone_name": zone_name
            })
            buttons = [
                [
                    {"type": "callback", "text": "✅ Да", "payload": "/cf_req_1"},
                    {"type": "callback", "text": "❌ Нет", "payload": "/cf_req_0"}
                ],
                [
                    {"type": "callback", "text": "❌ Отмена", "payload": "/cf_cancel_add"}
                ]
            ]
            await n.reply_with_keyboard(
                f"✏️ **Добавление поля '{state_data['new_field_name']}'**\n\n"
                "Сделать это поле обязательным для заполнения?",
                "markdown",
                buttons
            )

        elif step == "add_field_req":
            if text == "/cf_cancel_add":
                await self.show_zone_menu(n, zone_name)
                return

            if text.startswith("/cf_req_"):
                is_req = int(text.split("_")[2])
                field_name = state_data["new_field_name"]
                field_desc = state_data["new_field_desc"]

                database.add_custom_field(zone_name, field_name, is_req, field_desc)
                await n.reply(f"✅ Поле **{field_name}** успешно добавлено для {zone_name}.")
                await self.show_zone_menu(n, zone_name)
            else:
                await n.reply("Пожалуйста, ответьте с помощью кнопок.")

        elif step == "confirm_delete":
            if text == "/cf_confirm_del":
                field_id = state_data["delete_field_id"]
                database.delete_custom_field(field_id)
                await n.reply("🗑 Поле успешно удалено.")
                await self.show_zone_menu(n, zone_name)
            elif text == "/cf_cancel_del":
                await self.show_zone_menu(n, zone_name)
            else:
                await self.show_zone_menu(n, zone_name)
