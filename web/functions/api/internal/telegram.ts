// /api/internal/telegram (HMAC, the agents' host): GET whose link code it is or every linked owner; POST claim or unlink
import { hostTelegram } from "../../../server/telegram";
import { safe } from "../../../server/util";
export const onRequestGet = safe(hostTelegram);
export const onRequestPost = safe(hostTelegram);
