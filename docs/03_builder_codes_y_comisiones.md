# 03 · Builder Codes, comisión del desarrollador y alternativas nativas de monetización

Fuentes: `docs.strikefinance.org/api/builder-codes` (+ OpenAPI "Strike Builder API" v2.0.0), `api/getting-started`,
`perpetuals/trading-fees`, `perpetuals/copy-trading`, `perpetuals/vaults`, `api/vault-leader` — instantánea
2026-10-19 en `docs/sources/`. Repo `strike-builder-reference` @ c926f76 (2026-04-24).

Estados: **DOC** documentado oficialmente · **TEST** verificado con pruebas · **HIP** hipótesis pendiente ·
**BLOQ** bloqueado por acceso/aprobación/información de Strike.

## 1. Cómo funciona (resumen verificado en la documentación)

1. **Registro como builder** en `app.strikefinance.org/builder-codes` → código de builder único + `fee_share_bps`
   configurado (**máximo 100 bps = 1 %**). — DOC
2. **Onboarding de cada usuario** (*builder connect*), sin JWT ni cuenta previa (la crea si no existe):
   `POST /auth/builder/request-signature` {address, chain, code, `fee_share_bps` 0-100 que el usuario aprueba,
   public_key Ed25519 generada por el dApp, referral_code opcional} → el usuario firma `message_to_sign` con su wallet
   (EIP-191 / Ed25519 base58 / CIP-30) → `POST /auth/builder/verify-signature` {nonce, wallet_signature} → devuelve
   `account_id`, `api_wallet_public_key`, `api_wallet_expired_at`. Revoca las API wallets previas de esa cuenta+builder.
   El nonce caduca a los 5 min y es de un solo uso. — DOC
3. **Cobro**: cabecera `X-Builder-Fee-Bps: <n>` en cada orden. Reglas: n ≤ lo aprobado por el usuario, n ≤ el
   `fee_share_bps` del builder, n ≤ un "deployment cap" (valor no publicado); si no, **400 y la orden no se coloca**.
   Se cobra **al ejecutarse** (fill), no al colocar. Se abona **al instante** en el saldo de la cuenta de Strike del
   builder, retirable cuando se quiera. — DOC
4. **Atribución**: la API wallet del builder connect queda ligada al código ("no separate builder code header is
   needed"); las órdenes muestran `Builder {Code, FeeBps}` en `/v2/order` y `/v2/openOrders`. — DOC
5. Depósitos y retiros del usuario pasan por el dApp pero **siempre los firma la wallet del usuario**; el destino del
   retiro está fijado en servidor a la wallet conectada (el builder no puede desviar fondos). — DOC

**Discrepancias detectadas:** el repo oficial `strike-builder-reference` usa `max_fee_bps` en `request-signature` y
**no envía** `X-Builder-Fee-Bps` (comenta "builder fees are handled server-side"); el OpenAPI vigente exige
`fee_share_bps` y la guía dice que la cabecera es "the only addition". Se implementa lo documentado en el OpenAPI y se
verifica en testnet qué ocurre sin cabecera. — HIP

## 2. Las 13 preguntas del prompt

| # | Pregunta | Respuesta | Estado |
|---|---|---|---|
| 1 | ¿El 1 % es permitido, configurable, vigente? | Sí: 0-100 bps en el registro y en la aprobación del usuario; por orden con la cabecera. Puede haber un "deployment cap" inferior no publicado. | DOC (cap: BLOQ) |
| 2 | ¿Sobre qué base? | "basis points on their order fills" → se asume nocional ejecutado (precio × tamaño), como la comisión de trading (`Fee = Fill Price × Fill Size × Rate`). No lo dice literalmente. | HIP → testnet |
| 3 | ¿Apertura, cierre, ambas? | Cada **fill** de una orden que lleve la cabecera: entradas y salidas si ambas la llevan. **Desconocido** si las patas TP/SL de un bracket (las crea Strike al llenarse la primaria) heredan la fee. | DOC / HIP |
| 4 | ¿Tamaño de orden, volumen ejecutado o comisiones? | Volumen ejecutado ("charged when the order fills, not when placed"). No es un % de la comisión de trading. | DOC |
| 5 | ¿Adicional a la tarifa estándar? ¿Cómo la ve el usuario? | Implícitamente adicional (Strike cobra su taker/maker aparte; sus comisiones van a holders de $STRIKE). No consta si `fee` en `/v2/history/fill` incluye la builder fee o va aparte. | HIP → testnet |
| 6 | ¿Máximo / mínimo? | Máx. 100 bps (1 %), mín. 0. | DOC |
| 7 | ¿Builder code / id de agente? | Hace falta el código de builder (registro). No existe "id de agente" en la documentación. | DOC |
| 8 | ¿Atribución heredada o por orden? | La **atribución** se hereda de la API wallet del builder connect; la **cuantía** va por orden en la cabecera. | DOC |
| 9 | ¿Comisión propia del agente? | Sí, el valor de la cabecera, dentro de los topes. Se configura en `config/agent.toml` (`builder_fee_bps`). | DOC |
| 10 | ¿Cómo consultar y verificar lo generado? | Por orden: `Builder.FeeBps` (el agente lo comprueba y alerta si no coincide). Ingresos: saldo/historial de la cuenta del builder y su dashboard; el tipo de transacción exacto no está documentado. | DOC / HIP |
| 11 | ¿Liquidación y pago? | Abono instantáneo al saldo de Strike del builder; retiro normal (mín. 5 $, comisión fija 1 $). | DOC |
| 12 | ¿Restricciones para agentes publicados? | No hay sistema de agentes/marketplace documentado. | BLOQ |
| 13 | ¿Diferencias builder general vs agentes? | No documentado. | BLOQ |

El dato "el creador recibe el 100 % de la builder fee" es coherente con la doc (se abona al builder, no se menciona
reparto), pero no está escrito literalmente → confirmar con Strike.

## 3. Economía: la builder fee frente a la ventaja medida (lo más importante de este documento)

Backtest realista (`docs/05_informe_cuantitativo.md`, BTC+ETH+SOL, 2022-01 → 2026-10, taker 5 bps/fill, slippage
2/5 bps, funding, una posición por mercado). La builder fee se cobra en **entrada y salida**.

| Builder fee por fill | 1h R/op neto | 4h R/op neto | 1D R/op neto |
|---|---|---|---|
| 0 bps | +0,121 (IC95 −0,01…+0,26) | **+0,539** (+0,17…+0,94) | +0,60 (−0,27…+2,06), n=48 |
| 5 bps | +0,038 | +0,499 | — |
| 10 bps | **−0,045** | **+0,460** (+0,10…+0,85) | +0,57 |
| 20 bps | −0,212 | +0,382 (+0,02…+0,78) | +0,54 |
| 50 bps | −0,712 | +0,147 (IC incluye 0) | +0,45 |
| 100 bps (1 %) | **−1,544** | **−0,245** | +0,30 |
| Punto de equilibrio | ≈ 7 bps | ≈ 70 bps | — (no significativo) |

Por qué: el coste de la fee en R es `2·fee / distancia del stop`. El stop medio es 1,5 % del precio en 1h, 3,1 % en
4h y 8,3 % en 1D, así que cada bps cuesta 0,017 R/op en 1h y 0,008 R/op en 4h.

**Reparto estimado del rendimiento** (por cada 10.000 $ de un usuario, riesgo 0,5 %/op con colchón 1,25, sin
interés compuesto; estimación de backtest, **no** una promesa):

| 4h | Usuario (aprox./año) | Builder (aprox./año) |
|---|---|---|
| 0 bps | +15,7 % | 0 $ |
| 5 bps | +14,6 % | ≈ 114 $ |
| **10 bps** | **+13,4 %** | **≈ 228 $** |
| 20 bps | +11,2 % | ≈ 456 $ |

En **1h** la fee se come al usuario: con 5 bps el builder se llevaría ≈ 1.087 $/año por cada 10.000 $ mientras el
usuario ganaría ≈ +5 %; con 10 bps el usuario pierde. **Ofrecer 1h con builder fee perjudica al usuario.**

### Recomendación

- **Timeframe 4h**, único con ventaja estadísticamente significativa.
- **`builder_fee_bps` entre 5 y 10** (máximo 20). Con 10 bps el usuario conserva ≈ 85 % de la ventaja.
- **No usar 100 bps.** Con el 1 % la estrategia tiene expectativa negativa para el usuario en todos los timeframes
  con significación; además contradice el requisito de transparencia y de no perjudicar al usuario.
- El motor de riesgo rechaza operaciones cuyos costes previstos (taker + builder + spread) superen 0,35 R
  (`RiskConfig.max_cost_r`): la fee nunca aumenta tamaño ni frecuencia, solo puede descartar operaciones.

## 4. Alternativas nativas de Strike (documentadas) que conviene valorar

| Vía | Cómo cobra el creador | Alineación con el usuario | Custodia/operativa | Estado |
|---|---|---|---|---|
| **Builder Codes** | bps por fill (≤ 1 %) | Cobra aunque el usuario pierda | El agente guarda una API wallet (solo trading) **por usuario**; app propia de conexión | DOC |
| **Vault de usuario** (líder) | 0-50 % del beneficio de los depositantes (10 % por defecto), solo al retirar con ganancia | Alta: sin beneficio no hay comisión | Una sola cuenta (la del vault), el líder opera vía API con `vault_id`; el líder debe tener ≥ 5 % de las participaciones; alta 100 USDC; 1 vault por usuario | DOC |
| **Copy trading** (líder Strike) | 10 % del beneficio del copiador al parar la suscripción | Alta | Ninguna: el agente opera su propia cuenta y los usuarios le copian desde la app de Strike (descubrimiento nativo) | DOC |

**Comprobado en el código de la app de Strike (2026-10-19):** la página `app.strikefinance.org/builder-codes` solo
sirve para que el builder se registre y vea su código, % de fee, volumen y *rewards*. **No existe una pantalla para que
un usuario se una a un builder**: el *builder connect* (firma con su wallet) solo existe por API, así que el modelo
builder necesita una **página de conexión propia** (pequeña) y que el agente guarde una API wallet de solo trading por
usuario. A cambio, **el dinero y las posiciones siguen en la cuenta de Strike del usuario**, que puede verlas, cerrarlas
y retirar desde la app de Strike cuando quiera (sin lock-up ni confiar fondos a un líder).

**Recomendación (revisada tras la objeción de Edgar):** las dos vías son válidas y no hay que hacer el vault "sí o sí".
- Si se acepta construir la página de conexión (estática en Cloudflare Pages + endpoint en el CT): **builder codes a
  10 bps como canal principal** — mejor para adopción (autocustodia en su propia cuenta) e ingresos más predecibles
  (≈ 228 $/año por cada 10.000 $ de usuario en 4h, según backtest).
- **Vault** como opción para quien quiera algo pasivo sin conectar nada, o si se prefiere cero infraestructura.

## 5. Lo que falta para declarar la monetización verificada (Fase 5)

1. Registrarte como builder (testnet si existe la página; si no, mainnet) → código + `fee_share_bps`.
2. Builder connect de una cuenta de prueba con `fee_share_bps` = 10.
3. Orden mínima con `X-Builder-Fee-Bps: 10` → comprobar `Builder.FeeBps = 10` en la orden, el desglose del fill, el
   abono en la cuenta del builder y su tipo de transacción.
4. Repetir **sin** la cabecera (¿cobra el valor aprobado o nada?) y con un bracket (¿las patas TP/SL cobran fee?).
5. Hasta entonces: **monetización NO verificada**.

## Confirmado por Strike (Shan, CEO, 2026-10-19)

Cierra las hipótesis de las secciones 1-2 (detalle en `docs/07`, "Respuestas de Strike"):
- Base: **precio × tamaño ejecutado × bps / 10 000 por fill**, redondeado hacia abajo a 0,01 $; aparte de la comisión
  de trading (`fee` de `/v2/history/fill` no la incluye). Se ve en `GET /v2/builder/fills` (`BuilderReward`).
- Sin cabecera → 0 (nunca `fee_share_bps` por defecto). Las patas TP/SL heredan los bps de su orden.
- Tope 100 bps; el builder cobra el **100 %**. `fee_share_bps` es el campo correcto (`max_fee_bps` da error).
- Registro de builder también en testnet, con 100 $ de saldo mínimo.
- API wallets sin caducidad.

## ¿Subir la fee a 30 bps? (análisis del 2026-10-19)

Con el backtest de E2 (4h, BTC/ETH/SOL, 2022-2026, ejecución realista, 0,5 % de riesgo por operación):

| Fee por fill | R/op neto del usuario | IC95 | ¿Ventaja estadística? | CAGR usuario | Fee al builder (% del capital/año) |
|---|---|---|---|---|---|
| 10 bps | +0,46 R | [+0,10, +0,85] | sí | 16,9 % | ≈ 2,9 % |
| 20 bps | +0,38 R | [+0,02, +0,78] | justo | 13,7 % | ≈ 5,7 % |
| 30 bps | +0,30 R | [−0,06, +0,70] | **no** | 10,5 % | ≈ 8,6 % |

(Fee al builder ≈ 2 fills × bps × nocional; nocional ≈ riesgo / distancia del stop ≈ 19 % del capital por operación;
≈ 73 operaciones/año en 3 mercados. Con 8 mercados ambas columnas crecen con el número de operaciones.)

Lectura: a 30 bps el builder se llevaría casi tanto como gana el usuario y la ventaja deja de ser estadísticamente
distinguible de cero; en 1h incluso 10 bps la anula. Tope razonable: **20 bps en 4h**; 30 bps no es recomendable con
esta estrategia. Decisión de Edgar.

**Decisión (Edgar, 2026-10-19): 20 bps por ejecución** (0,20 %; 0,40 % por operación de ida y vuelta). Aplicada en
los 5 agentes en papel, la web (costes, ficha de estrategia regenerada con `web/scripts/gen_strategy.py --builder-bps
20`: +0,38 R/op, IC95 [+0,02, +0,78], CAGR 13,7 %) y la API. Al registrar el builder code, `fee_share_bps` ≥ 20; en el
builder connect el usuario aprueba 20. Efecto en 1h: el coste esperado ≈ 0,33 R roza el tope del motor de riesgo
(`max_cost_r` = 0,35 R), así que el agente de 1h se retiró (Edgar, 2026-10-19).
