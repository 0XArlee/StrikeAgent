# Conectar tu wallet a Smart Flow Agent (Strike Finance)

> **Nunca** compartas tu frase semilla ni la clave privada de tu wallet (ni conmigo, ni en un chat, ni en un archivo
> del proyecto). Este proyecto no las necesita en ningún momento.

## Cómo funciona

Tu wallet (Phantom, MetaMask/Rabby, Nami/Eternl…) **no opera directamente**. Solo autoriza una **API wallet**: un par
de claves Ed25519 independiente que puede **consultar y operar, pero no puede retirar fondos** (doc oficial:
*API Wallet Authentication → Permissions*). Los retiros siempre exigen la firma de tu wallet real.

## Pasos (empezar en TESTNET, sin dinero real)

1. **Abre la app de testnet**: https://testnet.strikefinance.org y conecta tu wallet (solo firmas un mensaje).
2. **Saldo de prueba**: consíguelo dentro de la app de testnet (no he podido confirmar si hay faucet; si no lo hay,
   dímelo y lo preguntamos a Strike).
3. *(Recomendado)* **Crea una sub-cuenta** "SmartFlow Agent" (menú Sub-accounts) para aislar el riesgo del agente.
4. **Genera la API wallet en tu PC** — PowerShell, dentro de la carpeta `StrikeAgent`:
   ```powershell
   .venv\Scripts\python -m smartflow.strike.keys testnet
   ```
   - Guarda la clave **privada** en `secrets\strike_testnet.env` (está en `.gitignore`, no se sube a ningún sitio).
   - Te muestra **solo la clave pública** (64 caracteres hexadecimales).
5. **Registra la clave pública** en la app: **API Wallets** → https://testnet.strikefinance.org/api-keys → añadir la
   clave pública (si deja vincularla a la sub-cuenta del paso 3, mejor).
6. **Avísame ("registrada")**. Haré **solo lecturas** (cuenta, saldo, posiciones, órdenes abiertas) para verificar la
   autenticación de punta a punta. **No se envía ninguna orden sin tu permiso explícito.**

## Después (mainnet)

Mismo proceso en https://app.strikefinance.org con `python -m smartflow.strike.keys mainnet`, una sub-cuenta con un
importe pequeño y solo cuando el paper trading y las pruebas en testnet estén superados.

## Monetización: Builder Code (paso aparte)

Para cobrar comisión de desarrollador hay que **registrarse como builder** en https://app.strikefinance.org/builder-codes
(código de builder + `fee_share_bps`, máximo 100 = 1 %). Los usuarios conectan su wallet a tu builder mediante el
flujo *builder connect* (firman un mensaje que fija la comisión máxima que aceptan).

**Recomendación medida** (ver `docs/05_informe_cuantitativo.md`): **≤ 10 bps**, no 100. Con 100 bps por fill la
estrategia pierde dinero para el usuario en 1h y en 4h.

Dime qué wallet/cadena usas (Solana, Ethereum o Cardano): el flujo *builder connect* firma distinto en cada una.
