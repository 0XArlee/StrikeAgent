// POST /api/feedback/read: an admin marks suggestions read
import { feedbackRead } from "../../../server/feedback";
import { safe } from "../../../server/util";
export const onRequestPost = safe(feedbackRead);
