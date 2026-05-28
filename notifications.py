"""Общие утилиты уведомлений для бота электронного бюро пропусков."""
import logging
import database
from maxbot_api_client_python.types import models

logger = logging.getLogger("max_visitor_bot")


async def send_notification(n, target_user_id, text: str):
    """Отправляет Markdown-уведомление заданному пользователю."""
    try:
        req = models.SendMessageReq(
            user_id=int(target_user_id),
            text=text,
            format="markdown"
        )
        await n.bot.api.messages.send_message_async(req)
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление пользователю {target_user_id}: {e}")


async def notify_admins(n, admin_ids: list[str], text: str):
    """Рассылает уведомление всем администраторам из списка."""
    for admin_id in admin_ids:
        await send_notification(n, admin_id, text)


async def send_expiry_notifications(n):
    """
    Находит просроченные заявки без уведомления и отправляет сообщение каждому инициатору.
    Вызывается при любом обновлении, которое может спровоцировать авто-просрочку
    (например, показ очереди, списка заявок пользователя, создание новой заявки).
    """
    expired_items = database.get_unnotified_expired()
    if not expired_items:
        return

    notified_ids = []
    for item in expired_items:
        notify_text = (
            f"⏳ **Ваша заявка №{item['request_id']} истекла.**\n\n"
            f"👤 Гость: {item['visitor_name']}\n"
            f"📅 Дата визита: {item['visit_date']}\n"
            f"🕒 Время визита: {item['visit_time']}\n"
            f"🚪 Корпус/Зона: {item['visit_zone']}\n\n"
            f"Заявка была автоматически закрыта — дата и время визита прошли."
        )
        await send_notification(n, item["initiator_id"], notify_text)
        notified_ids.append(item["request_id"])

    if notified_ids:
        database.mark_expire_notified(notified_ids)
        logger.info(f"Отправлены уведомления об истечении срока для заявок: {notified_ids}")
