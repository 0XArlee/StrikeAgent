// POST /api/internal/alerts: the alerts bot's public Strike alerts from the agents' host (HMAC signed)
import { hostAlerts } from "../../../server/telegram";
import { safe } from "../../../server/util";
export const onRequestPost = safe(hostAlerts);
