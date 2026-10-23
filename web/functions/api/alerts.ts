// GET /api/alerts: Strike Finance's latest moments, as the alerts bot saw them (the city shows them)
import { alerts } from "../../server/telegram";
import { safe } from "../../server/util";
export const onRequestGet = safe(alerts);
