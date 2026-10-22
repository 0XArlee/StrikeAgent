// GET /api/internal/feedback: new suggestions for the operator's phone; POST: sent (HMAC, the agents' host)
import { hostFeedback } from "../../../server/feedback";
import { safe } from "../../../server/util";
export const onRequestGet = safe(hostFeedback);
export const onRequestPost = safe(hostFeedback);
