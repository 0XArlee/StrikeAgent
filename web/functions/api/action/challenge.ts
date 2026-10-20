// POST /api/action/challenge {accountId, action}
import { actionChallenge } from "../../../server/handlers";
import { safe } from "../../../server/util";
export const onRequestPost = safe(actionChallenge);
