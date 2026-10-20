// any other /api path
import { fail } from "../../server/util";
export const onRequest = () => fail(404, "not found");
