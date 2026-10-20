// POST /api/connect/challenge {address, chain, risk, markets, name, public}
import { connectChallenge } from "../../../server/handlers";
import { safe } from "../../../server/util";
export const onRequestPost = safe(connectChallenge);
