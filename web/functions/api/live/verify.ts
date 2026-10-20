// POST /api/live/verify (Bearer) {sessionId, walletSignature}
import { liveVerify } from "../../../server/live";
import { safe } from "../../../server/util";
export const onRequestPost = safe(liveVerify);
