"""Сцена управления администраторами для технического администратора."""
import os
import database

ROLE_LABELS = {
    "admin":      "🛡 Администратор ИБ",
    "tech_admin": "⚙️ Тех. Администратор",
    "initiator":  "👤 Обычный пользователь",
}


class AdminMgmtScene:
    async def start(self, app):
        pass

    async def show_admins_list(self, n):
        db_admins = database.get_admins()

        # IDs, зафиксированные в .env (они всегда имеют роль, даже без записи в БД)
        env_admin_ids    = {x.strip() for x in os.getenv("ADMIN_USER_IDS",      "").split(",") if x.strip()}
        env_tech_ids     = {x.strip() for x in os.getenv("TECH_ADMIN_USER_IDS", "").split(",") if x.strip()}
        env_ids          = env_admin_ids | env_tech_ids

        n.state_manager.update_state_data(n.state_id, {"step": "admins_list"})

        text = "👥 **Управление администраторами**\n\n"

        if env_ids:
            text += "🔒 **Закреплены через .env (неизменяемы):**\n"
            for uid in sorted(env_ids):
                role = "tech_admin" if uid in env_tech_ids else "admin"
                text += f"  • `{uid}` — {ROLE_LABELS[role]}\n"
            text += "\n"

        if db_admins:
            # Не дублировать тех, кто уже в .env
            extra = [u for u in db_admins if u["user_id"] not in env_ids]
            if extra:
                text += "📋 **Назначены через бот:**\n"
                for u in extra:
                    name = u["display_name"] or u["user_id"]
                    text += f"  • `{u['user_id']}` — {name} → {ROLE_LABELS.get(u['role'], u['role'])}\n"
            else:
                text += "📋 Дополнительных администраторов нет.\n"
        else:
            text += "📋 Дополнительных администраторов нет.\n"

        buttons = []

        # Кнопки «Снять роль» для каждого DB-администратора (не из .env)
        extra_admins = [u for u in db_admins if u["user_id"] not in env_ids]
        for u in extra_admins:
            name_short = (u["display_name"] or u["user_id"])[:20]
            buttons.append([{
                "type": "callback",
                "text": f"❌ Снять роль: {name_short}",
                "payload": f"/adm_revoke_{u['user_id']}"
            }])

        buttons.append([{"type": "callback", "text": "➕ Назначить администратора", "payload": "/adm_add"}])
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

        step = state_data.get("step", "admins_list")

        if text == "/adm_back":
            await self.show_admins_list(n)
            return

        # ── Добавление администратора ────────────────────────────────────────

        if text == "/adm_add":
            n.state_manager.update_state_data(n.state_id, {"step": "adm_enter_id"})
            buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/adm_back"}]]
            await n.reply_with_keyboard(
                "➕ **Назначить администратора**\n\n"
                "Введите **числовой ID пользователя** в мессенджере MAX.\n\n"
                "💡 Пользователь может узнать свой ID, написав боту `/start` — "
                "ID отображается в адресной строке профиля или его можно получить из ссылки на чат.",
                "markdown",
                buttons
            )
            return

        if step == "adm_enter_id":
            if text == "/adm_back":
                await self.show_admins_list(n)
                return

            uid = text.strip()
            if not uid.lstrip("-").isdigit():
                buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/adm_back"}]]
                await n.reply_with_keyboard(
                    "❌ ID должен быть числом. Попробуйте ещё раз:",
                    "markdown",
                    buttons
                )
                return

            # Проверяем, не является ли этот ID уже администратором из .env
            env_admin_ids = {x.strip() for x in os.getenv("ADMIN_USER_IDS",      "").split(",") if x.strip()}
            env_tech_ids  = {x.strip() for x in os.getenv("TECH_ADMIN_USER_IDS", "").split(",") if x.strip()}
            if uid in env_admin_ids | env_tech_ids:
                await n.reply(f"ℹ️ Пользователь `{uid}` уже является администратором (закреплён в .env).")
                await self.show_admins_list(n)
                return

            n.state_manager.update_state_data(n.state_id, {
                "step": "adm_choose_role",
                "target_uid": uid
            })
            buttons = [
                [{"type": "callback", "text": "🛡 Администратор ИБ",      "payload": "/adm_role_admin"}],
                [{"type": "callback", "text": "⚙️ Тех. Администратор",    "payload": "/adm_role_tech_admin"}],
                [{"type": "callback", "text": "❌ Отмена",                  "payload": "/adm_back"}],
            ]
            await n.reply_with_keyboard(
                f"👤 Пользователь: `{uid}`\n\nВыберите роль:",
                "markdown",
                buttons
            )
            return

        if step == "adm_choose_role":
            uid = state_data.get("target_uid", "")

            role_map = {
                "/adm_role_admin":      "admin",
                "/adm_role_tech_admin": "tech_admin",
            }
            if text not in role_map:
                await self.show_admins_list(n)
                return

            role = role_map[text]
            database.set_user_role(uid, role)
            await n.reply(
                f"✅ Пользователю `{uid}` назначена роль: **{ROLE_LABELS[role]}**.\n\n"
                f"При следующем входе в бот у него появится соответствующее меню."
            )
            await self.show_admins_list(n)
            return

        # ── Снятие роли ──────────────────────────────────────────────────────

        if text.startswith("/adm_revoke_"):
            uid = text.split("_", 2)[2]
            user = database.get_user(uid)

            env_admin_ids = {x.strip() for x in os.getenv("ADMIN_USER_IDS",      "").split(",") if x.strip()}
            env_tech_ids  = {x.strip() for x in os.getenv("TECH_ADMIN_USER_IDS", "").split(",") if x.strip()}
            if uid in env_admin_ids | env_tech_ids:
                await n.reply("⛔ Этот администратор закреплён в .env и не может быть изменён через бот.")
                await self.show_admins_list(n)
                return

            n.state_manager.update_state_data(n.state_id, {
                "step": "adm_confirm_revoke",
                "target_uid": uid,
                "target_name": (user["display_name"] if user else uid)
            })
            name = (user["display_name"] if user else uid)
            buttons = [
                [
                    {"type": "callback", "text": "✅ Да, снять роль", "payload": "/adm_confirm_revoke"},
                    {"type": "callback", "text": "❌ Отмена",          "payload": "/adm_back"},
                ]
            ]
            await n.reply_with_keyboard(
                f"⚠️ Снять роль администратора у пользователя **{name}** (`{uid}`)?\n\n"
                f"Он станет обычным пользователем.",
                "markdown",
                buttons
            )
            return

        if step == "adm_confirm_revoke" and text == "/adm_confirm_revoke":
            uid  = state_data.get("target_uid", "")
            name = state_data.get("target_name", uid)
            database.set_user_role(uid, "initiator")
            await n.reply(f"✅ Роль у **{name}** (`{uid}`) снята — теперь обычный пользователь.")
            await self.show_admins_list(n)
            return

        # По умолчанию: возврат к списку администраторов
        await self.show_admins_list(n)
