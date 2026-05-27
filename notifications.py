"""Shared notification utilities for the visitor pass bot."""
import logging
import database
from maxbot_api_client_python.types import models

logger = logging.getLogger("max_visitor_bot")


async def send_notification(n, target_user_id, text: str):
    """Send a Markdown notification message to a given user ID."""
    try:
        req = models.SendMessageReq(
            user_id=int(target_user_id),
            text=text,
            format="markdown"
        )
        await n.bot.api.messages.send_message_async(req)
    except Exception as e:
        logger.warning(f"Failed to send notification to {target_user_id}: {e}")


async def notify_admins(n, admin_ids: list[str], text: str):
    """Broadcast a notification to all admin IDs."""
    for admin_id in admin_ids:
        await send_notification(n, admin_id, text)


async def send_expiry_notifications(n):
    """
    Find expired requests that haven't been notified yet and send a message
    to each initiator. Should be called on any update that triggers auto-expire
    (e.g. showing the queue, showing a user's requests, creating a new request).
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
        logger.info(f"Sent expiry notifications for requests: {notified_ids}")
