// GET /api/internal/copyplans: the owners' signed copy plans, for the agents' host (HMAC)
import { hostCopyPlans } from "../../../server/copyplan";
import { safe } from "../../../server/util";
export const onRequestGet = safe(hostCopyPlans);
