// POST /api/internal/copystatus: how each copy plan goes, from the agents' host (HMAC)
import { hostCopyStatus } from "../../../server/copyplan";
import { safe } from "../../../server/util";
export const onRequestPost = safe(hostCopyStatus);
