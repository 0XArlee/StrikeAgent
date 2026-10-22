// POST /api/feedback: a suggestion from the site's Feedback button (private: only the admins read it)
import { sendFeedback } from "../../server/feedback";
import { safe } from "../../server/util";
export const onRequestPost = safe(sendFeedback);
