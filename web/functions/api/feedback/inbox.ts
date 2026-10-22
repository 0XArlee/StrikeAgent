// GET /api/feedback/inbox: the latest suggestions, for an admin signed in with their wallet
import { feedbackInbox } from "../../../server/feedback";
import { safe } from "../../../server/util";
export const onRequestGet = safe(feedbackInbox);
