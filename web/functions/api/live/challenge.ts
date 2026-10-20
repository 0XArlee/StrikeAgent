// POST /api/live/challenge (Bearer): Strike builder-connect message to sign
import { liveChallenge } from "../../../server/live";
import { safe } from "../../../server/util";
export const onRequestPost = safe(liveChallenge);
