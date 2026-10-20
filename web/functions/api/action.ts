// POST /api/action {sessionId, walletSignature}
import { action } from "../../server/handlers";
import { safe } from "../../server/util";
export const onRequestPost = safe(action);
