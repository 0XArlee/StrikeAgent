// GET /api/copy: Strike's copy trading for the Copy Arena (leads, copiers, Strike's totals), pushed by the agents' host
import { copy } from "../../server/copy";
import { safe } from "../../server/util";
export const onRequestGet = safe(copy);
