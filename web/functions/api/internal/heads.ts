// POST /api/internal/heads: the heads the site kept, to check the host's logs (HMAC)
import { hostHeads } from "../../../server/audit";
import { safe } from "../../../server/util";
export const onRequestPost = safe(hostHeads);
