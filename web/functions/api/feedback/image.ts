// GET /api/feedback/image?id=&sig=: a suggestion's picture, behind a signed link
import { feedbackImage } from "../../../server/feedback";
import { safe } from "../../../server/util";
export const onRequestGet = safe(feedbackImage);
