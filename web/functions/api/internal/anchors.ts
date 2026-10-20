// POST /api/internal/anchors: heads of the agents host's audit logs, kept for good (HMAC)
import { hostAnchors } from "../../../server/audit";
import { safe } from "../../../server/util";
export const onRequestPost = safe(hostAnchors);
