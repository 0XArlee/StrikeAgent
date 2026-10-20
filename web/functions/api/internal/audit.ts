// GET /api/internal/audit: the audit trail for the agents host (HMAC)
import { hostAudit } from "../../../server/audit";
import { safe } from "../../../server/util";
export const onRequestGet = safe(hostAudit);
