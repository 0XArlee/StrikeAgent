// POST /api/internal/copy: the Copy Arena's document from the agents' host (HMAC signed)
import { hostCopy } from "../../../server/copy";
import { safe } from "../../../server/util";
export const onRequestPost = safe(hostCopy);
