// GET /api/internal/live: links for the agents host (HMAC)
import { hostLive } from "../../../server/live";
import { safe } from "../../../server/util";
export const onRequestGet = safe(hostLive);
