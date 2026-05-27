"""Zone management scene for the technical administrator (Task 3)."""
import database
from database import zone_btn_label


class ZonesMgmtScene:
    async def start(self, app):
        pass

    async def show_zones_list(self, n):
        zones = database.get_zones_with_ids()

        n.state_manager.update_state_data(n.state_id, {
            "step": "zones_list"
        })

        text = "🗺️ **Управление зонами посещения**\n\n"
        if not zones:
            text += "Зон посещения пока нет.\n"
        else:
            text += "Список активных зон:\n"
            for i, z in enumerate(zones, 1):
                active_mark = "✅" if z["is_active"] else "❌"
                text += f"{i}. {active_mark} {z['zone_name']}\n"

        buttons = []
        # Action buttons per zone
        for z in zones:
            row = [
                {"type": "callback", "text": zone_btn_label(z['zone_name'], prefix="✏️ ", max_len=30), "payload": f"/zone_rename_{z['zone_id']}"},
                {"type": "callback", "text": "🗑", "payload": f"/zone_del_{z['zone_id']}"}
            ]
            buttons.append(row)

        buttons.append([{"type": "callback", "text": "➕ Добавить зону", "payload": "/zone_add"}])
        buttons.append([{"type": "callback", "text": "◀️ В меню", "payload": "/menu"}])

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

        step = state_data.get("step", "zones_list")

        # Return to main menu
        # Return to zones list
        if text == "/zones_back":
            await self.show_zones_list(n)
            return

        # ── Add zone ──────────────────────────────────────────────────────────

        if text == "/zone_add":
            n.state_manager.update_state_data(n.state_id, {"step": "add_zone_name"})
            buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/zones_back"}]]
            await n.reply_with_keyboard(
                "➕ **Добавление зоны посещения**\n\n"
                "Введите полное название новой зоны (например, `Улица Ленина, 10 (Корпус Б)`):",
                "markdown",
                buttons
            )
            return

        if step == "add_zone_name":
            if text == "/zones_back":
                await self.show_zones_list(n)
                return

            zone_name = text.strip()
            if not zone_name or len(zone_name) < 3:
                buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/zones_back"}]]
                await n.reply_with_keyboard(
                    "❌ Название зоны слишком короткое. Введите корректное название:",
                    "markdown",
                    buttons
                )
                return

            zone_id = database.add_zone(zone_name)
            if zone_id:
                await n.reply(f"✅ Зона **{zone_name}** успешно добавлена.")
            else:
                await n.reply(f"⚠️ Зона с таким названием уже существует.")

            await self.show_zones_list(n)
            return

        # ── Delete zone ───────────────────────────────────────────────────────

        if text.startswith("/zone_del_"):
            zone_id = int(text.split("_")[2])
            zone = database.get_zone(zone_id)
            if not zone:
                await n.reply("❌ Зона не найдена.")
                await self.show_zones_list(n)
                return

            n.state_manager.update_state_data(n.state_id, {
                "step": "confirm_del_zone",
                "target_zone_id": zone_id,
                "target_zone_name": zone["zone_name"]
            })
            buttons = [
                [
                    {"type": "callback", "text": "💥 Да, удалить", "payload": "/zone_confirm_del"},
                    {"type": "callback", "text": "❌ Отмена", "payload": "/zones_back"}
                ]
            ]
            await n.reply_with_keyboard(
                f"⚠️ **Подтвердите удаление зоны**\n\n"
                f"Вы уверены, что хотите удалить зону:\n**{zone['zone_name']}**?\n\n"
                f"Существующие заявки и настроенные поля для этой зоны сохранятся в базе данных.",
                "markdown",
                buttons
            )
            return

        if step == "confirm_del_zone":
            if text == "/zone_confirm_del":
                zone_id = state_data["target_zone_id"]
                zone_name = state_data.get("target_zone_name", "")
                database.delete_zone(zone_id)
                await n.reply(f"🗑 Зона **{zone_name}** удалена.")
            await self.show_zones_list(n)
            return

        # ── Rename zone ───────────────────────────────────────────────────────

        if text.startswith("/zone_rename_"):
            zone_id = int(text.split("_")[2])
            zone = database.get_zone(zone_id)
            if not zone:
                await n.reply("❌ Зона не найдена.")
                await self.show_zones_list(n)
                return

            n.state_manager.update_state_data(n.state_id, {
                "step": "rename_zone",
                "target_zone_id": zone_id,
                "target_zone_name": zone["zone_name"]
            })
            buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/zones_back"}]]
            await n.reply_with_keyboard(
                f"✏️ **Переименование зоны**\n\n"
                f"Текущее название: **{zone['zone_name']}**\n\n"
                f"Введите новое название зоны:",
                "markdown",
                buttons
            )
            return

        if step == "rename_zone":
            if text == "/zones_back":
                await self.show_zones_list(n)
                return

            new_name = text.strip()
            if not new_name or len(new_name) < 3:
                buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/zones_back"}]]
                await n.reply_with_keyboard(
                    "❌ Название зоны слишком короткое. Введите корректное название:",
                    "markdown",
                    buttons
                )
                return

            zone_id = state_data["target_zone_id"]
            old_name = state_data.get("target_zone_name", "")
            success = database.rename_zone(zone_id, new_name)
            if success:
                await n.reply(
                    f"✅ Зона переименована:\n"
                    f"_«{old_name}»_ → **{new_name}**\n\n"
                    f"Кастомные поля, привязанные к этой зоне, также обновлены."
                )
            else:
                await n.reply(f"⚠️ Не удалось переименовать: зона с названием **{new_name}** уже существует.")

            await self.show_zones_list(n)
            return

        # Default: return to zones list
        await self.show_zones_list(n)
