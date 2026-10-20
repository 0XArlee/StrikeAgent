// GET /api/me (Authorization: Bearer <session token>)
import { me } from "../../server/handlers";
import { safe } from "../../server/util";
export const onRequestGet = safe(me);
