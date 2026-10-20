// GET /api/info
import { info } from "../../server/handlers";
import { safe } from "../../server/util";
export const onRequestGet = safe(info);
