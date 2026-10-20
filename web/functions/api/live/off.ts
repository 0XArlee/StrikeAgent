// POST /api/live/off (Bearer): stop real trading
import { liveOff } from "../../../server/live";
import { safe } from "../../../server/util";
export const onRequestPost = safe(liveOff);
