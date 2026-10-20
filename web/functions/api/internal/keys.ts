// POST /api/internal/keys: fresh public keys from the agents host (HMAC)
import { hostKeys } from "../../../server/live";
import { safe } from "../../../server/util";
export const onRequestPost = safe(hostKeys);
