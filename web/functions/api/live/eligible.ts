// GET /api/live/eligible?address=: right after a wallet connects, whether it already has an agent (it only signs in)
// and whether it may connect its Strike account now (invite-only phase)
import { walletStatus } from "../../../server/handlers";
import { safe } from "../../../server/util";
export const onRequestGet = safe(walletStatus);
