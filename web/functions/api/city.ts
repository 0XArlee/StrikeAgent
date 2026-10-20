// GET /api/city: the real agents plus the users' agents shown in the city by their owners
import { city } from "../../server/handlers";
import { safe } from "../../server/util";
export const onRequestGet = safe(city);
