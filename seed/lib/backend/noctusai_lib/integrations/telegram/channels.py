"""Channel binding check: is the bot an admin of this channel with the right to post?"""
from __future__ import annotations

from .types import ChannelAdminCheck, ChatId, ChatInfo, TelegramClient, TelegramForbiddenError, TelegramNotFoundError


async def verify_bot_channel_admin(client: TelegramClient, chat_id: ChatId) -> ChannelAdminCheck:
    """getChat + getChatMember(bot) -> a typed verdict. Never raises for the expected 'not admin / not found'
    cases (they are the answer); auth / rate-limit / transport errors propagate."""
    try:
        chat = await client.get_chat(chat_id)
    except TelegramNotFoundError:
        return ChannelAdminCheck(ChatInfo(0, "unknown"), False, False, "chat_not_found")
    except TelegramForbiddenError:
        return ChannelAdminCheck(ChatInfo(0, "unknown"), False, False, "bot_not_in_chat")
    if chat.type != "channel":
        return ChannelAdminCheck(chat, False, False, "not_a_channel")
    me = await client.get_me()
    try:
        member = await client.get_chat_member(chat.id, me.id)
    except TelegramForbiddenError:
        return ChannelAdminCheck(chat, False, False, "bot_not_in_chat")
    if not member.is_admin:
        return ChannelAdminCheck(chat, False, False, "bot_not_admin")
    if not member.can_post_messages:
        return ChannelAdminCheck(chat, True, False, "bot_cannot_post")
    return ChannelAdminCheck(chat, True, True, "")
