// POST /api/connect/verify {sessionId, walletSignature}
import { connectVerify } from "../../../server/handlers";
import { safe } from "../../../server/util";
export const onRequestPost = safe(connectVerify);
