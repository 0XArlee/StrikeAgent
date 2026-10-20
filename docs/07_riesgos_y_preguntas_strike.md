# 07 · Riesgos, limitaciones y preguntas para el equipo de Strike

## Riesgos y limitaciones (por impacto)

| # | Riesgo | Impacto | Mitigación actual |
|---|---|---|---|
| R1 | **La ventaja en 1h no es estadísticamente significativa** con costes realistas (IC95 incluye 0) | Operar 1h es apostar | El agente se configura en 4h por defecto; 1h solo como experimento |
| R2 | **Builder fee alta destruye la expectativa** (1 % ⇒ −0,25 R/op en 4h, −1,54 R/op en 1h) | Pérdidas para el usuario, reputación | Recomendación ≤ 10 bps; el riesgo rechaza si coste > 0,35 R |
| R3 | Las cifras de los comentarios del indicador **no son reproducibles** | Expectativas infladas | Solo se comunican cifras medidas e IC; pregunta a EdgeCraft |
| R4 | Toda la historia 2022-2026 está "vista" por el autor al diseñar el indicador: no hay fuera de muestra temporal real | Sobreestimación | Activos fuera de muestra (E5), robustez de parámetros (E7), paper trading prospectivo |
| R5 | Strike tiene **poca liquidez fuera de BTC/ETH** y testnet casi ninguna | Slippage | Límites de spread/impacto; tamaño acotado; IOC con precio protector |
| R6 | Basis Strike (USD) vs Binance (USDT): mediana 7-12 bps, p95 ≈ 14-18 bps | Stops/entradas ligeramente desplazados | `max_basis_bps`; stop por mark de Strike |
| R7 | Formatos de API que difieren de la doc (verificado en 2 endpoints) | Errores en producción | Parseo tolerante; `strike-check` antes de arrancar |
| R8 | Motor de órdenes asíncrono (sin order_id en la respuesta) | Estado incierto tras timeouts | Reconciliación por `client_order_id`; mercado bloqueado si no cuadra |
| R9 | Custodia de API wallets de usuarios (modelo builder) | Si se filtran, un tercero puede **operar** (no retirar) | Secretos cifrados en reposo (pendiente: KMS/age), mínimo privilegio, sub-cuentas, rotación 90-180 días |
| R10 | El stop de 1,5 ATR no garantiza la pérdida máxima (gaps, liquidez, caída del servicio) | Pérdida > 1 R | Colchón de tamaño 1,25×, liquidación ≥ 2× la distancia del stop, stop en el exchange (no en el bot) |
| R11 | Dependencia de Binance como feed | Sin datos ⇒ sin señales | Feed no sano ⇒ no se abren operaciones (las salidas siguen: stop en Strike) |
| R12 | No hay marketplace de agentes documentado | No hay "publicación nativa" posible hoy | Vault / copy trading como distribución nativa; preguntas abajo |

## Preguntas para Strike (enviar al equipo)

**Builder Codes**
1. ¿La builder fee se calcula sobre el nocional ejecutado (precio × tamaño del fill)? ¿Aparece separada o incluida en
   `fee` de `/v2/history/fill`? ¿Qué tipo de transacción ve el builder al cobrarla?
2. ¿Qué pasa si una orden de una API wallet de builder **no** lleva `X-Builder-Fee-Bps`: se cobra 0 o el
   `fee_share_bps` aprobado? (el repo `strike-builder-reference` sugiere lo segundo; la guía, lo primero).
3. En `POST /v2/order/strategy`, ¿las patas TP/SL que crea Strike heredan la builder fee de la cabecera de la orden
   primaria?
4. ¿Cuál es el "deployment cap" actual de la builder fee? ¿Recibe el builder el 100 % de la fee?
5. ¿Se puede registrar un builder en **testnet**? ¿Hay faucet de testnet?
6. `max_fee_bps` vs `fee_share_bps` en `request-signature`: ¿cuál es el campo vigente?
7. ¿Caducidad de las API wallets del builder connect (`api_wallet_expired_at`) y cómo renovarlas sin que el usuario
   vuelva a firmar?

**Órdenes**
8. ¿`client_order_id` es único por cuenta (rechaza duplicados)? ¿Durante cuánto tiempo?
9. Formato vigente del bracket: `tp_order`/`sl_order` (OpenAPI) o `take_profit_orders[]`/`stop_loss_orders[]` (repo).
10. Al cerrar la posición con una orden reduce-only aparte, ¿se cancelan automáticamente las patas pendientes del
    bracket?

**Agentes**
11. ¿Existe o existirá un sistema de agentes/marketplace? Formato, registro, revisión, alojamiento, permisos,
    versionado, requisitos de seguridad, cómo se configura la comisión del creador y cómo se verifica la atribución.
12. Para un agente distribuido como **vault** o **lead de copy trading**: ¿hay programa de "verified vault"/destacado y
    requisitos?

## Respuestas de Strike (Shan, CEO, 2026-10-19)

Respuestas a las preguntas 1-10 (las 11-12, marketplace y vault destacado, siguen abiertas):

| # | Respuesta | Qué cambia en el agente |
|---|---|---|
| 1 | Builder fee = precio del fill × tamaño ejecutado × bps / 10 000, **por fill**, redondeada hacia abajo a 0,01 $. **No** va incluida en `fee` de `/v2/history/fill`. El builder la ve como `BuilderReward` en `GET /v2/builder/fills`; el trader como `builder_fee` en los eventos de trade del WebSocket. No hay transacción: pasa del saldo de Strike del trader al del builder durante el fill. | Verificar ingresos con `GET /v2/builder/fills` (cuenta del builder), no con `fee` de los fills. |
| 2 | Sin `X-Builder-Fee-Bps` la builder fee es **0**; nunca toma `fee_share_bps` por defecto. El fill cuenta igualmente como volumen del builder. | La cabecera debe ir en **todas** las órdenes: ya va en cada POST de `ORDER_PATHS` (entradas, salidas reduce-only, stops de respaldo, brackets). |
| 3 | Las patas TP/SL de `POST /v2/order/strategy` **heredan** el builder code y los bps de la orden original. Se recomprueba al ejecutarse: si entretanto el usuario o el builder bajó su tope por debajo, la pata se ejecuta sin builder fee. | Nada que cambiar; el stop del bracket cobra. |
| 4 | Tope de despliegue **100 bps (1 %)**. El builder recibe el **100 %** de la fee. | Confirmado. |
| 5 | Los builder codes **funcionan en testnet**. Registrarse exige **100 $ de saldo** en la cuenta. No hay faucet público: el equipo de Strike financia cuentas de prueba. | La cuenta testnet de Edgar (≈1 400 $ ficticios) permite registrar el builder en testnet y probar el builder connect completo. |
| 6 | Usar **`fee_share_bps`** en `request-signature`; `max_fee_bps` se rechaza (`json: unknown field "max_fee_bps"`). | Es lo que implementamos (OpenAPI). |
| 7 | Las API wallets del builder connect **no caducan** (9999-12-31T23:59:59Z). Solo dejan de funcionar si el usuario reconecta con el mismo builder o la revoca. | Sin renovaciones; detectar 401 → pedir reconexión. |
| 8 | `client_order_id` **no es único** y los duplicados no se rechazan: cada uno crea otra orden; buscar o cancelar por `client_order_id` coge la abierta más reciente. | Ya lo tratamos: idempotencia en el cliente y reconciliación, nunca reenviar. |
| 9 | La API viva usa `tp_order` / `sl_order` (un objeto cada uno), como el OpenAPI. `take_profit_orders[]` / `stop_loss_orders[]` no existen. | Es lo que implementamos. |
| 10 | Cerrar con una reduce-only aparte **cancela solas** las TP/SL pendientes cuando la posición queda plana o cambia de lado. No afecta a TP/SL de una entrada aún sin ejecutar. | Nuestra cancelación de patas sobrantes queda como red de seguridad (inofensiva si ya no existen). |
