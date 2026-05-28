"""Сцена списка пользователей для технического администратора."""
import database

PAGE_SIZE = 8

ROLE_LABELS = {
    "initiator":  "👤 Инициатор",
    "admin":      "🛡 Администратор ИБ",
    "tech_admin": "⚙️ Тех. Администратор",
}


class UserListScene:
    async def start(self, app):
        pass

    async def show_user_list(self, n, page: int = 0, search: str = None):
        total = database.get_users_count(search)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1

        offset = page * PAGE_SIZE
        users = database.get_users_page(PAGE_SIZE, offset, search)

        n.state_manager.update_state_data(n.state_id, {
            "step": "browsing",
            "page": page,
            "search": search
        })

        # Header
        if search:
            header = (
                f"🔍 **Поиск: «{search}»** — найдено {total}\n\n"
            )
        else:
            header = (
                f"👥 **Все пользователи** — {total} чел., стр. {page + 1}/{total_pages}\n\n"
            )

        # User lines
        lines = []
        for u in users:
            name = u["display_name"] or "—"
            role_label = ROLE_LABELS.get(u["role"], u["role"])
            consent_mark = "✅" if u["consent_given"] else "❓"
            lines.append(
                f"{consent_mark} **{name}**\n"
                f"   ID: `{u['user_id']}` | {role_label}"
            )

        if not lines:
            body = "_Ничего не найдено._"
        else:
            body = "\n\n".join(lines)

        text = header + body

        buttons = []

        # Navigation row
        nav_row = []
        if page > 0:
            nav_row.append({"type": "callback", "text": "◀️", "payload": f"/ulist_page_{page - 1}"})
        nav_row.append({"type": "callback", "text": f"{page + 1}/{total_pages}", "payload": "/ulist_noop"})
        if page < total_pages - 1:
            nav_row.append({"type": "callback", "text": "▶️", "payload": f"/ulist_page_{page + 1}"})
        if len(nav_row) > 1:
            buttons.append(nav_row)

        # Search / clear row
        if search:
            buttons.append([
                {"type": "callback", "text": "🔍 Новый поиск", "payload": "/ulist_search"},
                {"type": "callback", "text": "✖️ Сбросить", "payload": "/ulist_clear"}
            ])
        else:
            buttons.append([
                {"type": "callback", "text": "🔍 Поиск по имени / ID", "payload": "/ulist_search"}
            ])

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
            await n.reply("Пожалуйста, используйте кнопки или введите поисковый запрос.")
            return

        state_data = n.state_manager.get_state_data(n.state_id)
        if not state_data:
            from scenes.main_menu import MainMenuScene
            menu = MainMenuScene()
            n.activate_next_scene(menu)
            await menu.send_main_menu(n)
            return

        step   = state_data.get("step", "browsing")
        page   = state_data.get("page", 0)
        search = state_data.get("search")

        # No-op button (page indicator)
        if text == "/ulist_noop":
            return

        # Page navigation
        if text.startswith("/ulist_page_"):
            new_page = int(text.split("_")[2])
            await self.show_user_list(n, new_page, search)
            return

        # Start search input
        if text == "/ulist_search":
            n.state_manager.update_state_data(n.state_id, {
                "step": "search_input",
                "page": page,
                "search": search
            })
            buttons = [[{"type": "callback", "text": "❌ Отмена", "payload": "/ulist_cancel_search"}]]
            await n.reply_with_keyboard(
                "🔍 **Поиск пользователя**\n\n"
                "Введите имя или часть ID пользователя:",
                "markdown",
                buttons
            )
            return

        # Cancel search input
        if text == "/ulist_cancel_search":
            await self.show_user_list(n, page, search)
            return

        # Clear search
        if text == "/ulist_clear":
            await self.show_user_list(n, 0, None)
            return

        # Process search query
        if step == "search_input":
            query = text.strip()
            if len(query) < 1:
                await n.reply("Запрос слишком короткий, попробуйте ещё раз:")
                return
            await self.show_user_list(n, 0, query)
            return

        # Unknown — refresh
        await self.show_user_list(n, page, search)
