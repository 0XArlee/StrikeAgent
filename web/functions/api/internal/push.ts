// POST /api/internal/push: snapshot from the agents' host (HMAC signed)
import { push } from "../../../server/handlers";
import { safe } from "../../../server/util";
export const onRequestPost = safe(push);
