// GET /api/news: the News Tower's data (headlines, readings, calendar), pushed by the agents' host
import { news } from "../../server/news";
import { safe } from "../../server/util";
export const onRequestGet = safe(news);
