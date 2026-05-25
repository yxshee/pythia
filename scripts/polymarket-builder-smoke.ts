/**
 * Polymarket builder-code format smoke test.
 *
 * Validates that the configured POLYMARKET_BUILDER_CODE env var is a
 * well-formed bytes32 hex string suitable for attaching to a Polymarket
 * CLOB V2 order. Does NOT place any orders, fetch matched fills, or
 * interact with the Polymarket API.
 *
 * Real production attribution requires:
 *   1. Registering a builder profile with Polymarket.
 *   2. Receiving a bytes32 builder code.
 *   3. Including that code in the order struct via the CLOB SDK v2.
 *   4. Confirming credited fills via getBuilderTrades().
 *
 * This script is intentionally bounded to step (1) format validation so
 * that nothing in CI / smoke runs can accidentally place a live order.
 * Order placement is gated by POLYMARKET_PLACE_ORDER, which must remain
 * "false" (default) for this submission's smoke path.
 */

const code = process.env.POLYMARKET_BUILDER_CODE;
if (!code || !/^0x[0-9a-fA-F]{64}$/.test(code)) {
  throw new Error("POLYMARKET_BUILDER_CODE must be a bytes32 hex string");
}
console.log("Builder code format valid.");
console.log(
  "Real attribution requires order-level builderCode and matched fills.",
);

const placeOrder = process.env.POLYMARKET_PLACE_ORDER === "true";
if (placeOrder) {
  throw new Error(
    "POLYMARKET_PLACE_ORDER=true is not supported in the submission smoke. " +
      "Set it to 'false' (default) and place orders manually via the CLOB SDK.",
  );
}
console.log("POLYMARKET_PLACE_ORDER=false — no orders will be placed.");
