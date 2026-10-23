// /api/me/telegram (Authorization: Bearer <session token>): GET the chats linked to my agent, POST a one-time link to
// the alerts bot, DELETE unlink them
import { meTelegram } from "../../../server/telegram";
import { safe } from "../../../server/util";
export const onRequestGet = safe(meTelegram);
export const onRequestPost = safe(meTelegram);
export const onRequestDelete = safe(meTelegram);
