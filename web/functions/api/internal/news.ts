// POST /api/internal/news: the News Tower's document from the agents' host (HMAC signed)
import { hostNews } from "../../../server/news";
import { safe } from "../../../server/util";
export const onRequestPost = safe(hostNews);
