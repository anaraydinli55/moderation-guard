import { createClient } from "genlayer-js";
import { studioDevnet } from "genlayer-js/chains";
import { privateKeyToAccount } from "viem/accounts";

const rawKey = process.env.PRIVATE_KEY;
if (!rawKey) {
  console.error("❌ PRIVATE_KEY eksik!");
  process.exit(1);
}

const privateKey = rawKey.startsWith("0x") ? rawKey : "0x" + rawKey;
const account = privateKeyToAccount(privateKey);

const client = createClient({
  chain: studioDevnet,
  account: account,
});

const CONTRACT_ADDR = process.env.CONTRACT_ADDRESS || "0x28ED9e09991896D1399Ae71F1c90Bb02863dd67B";

async function test() {
  console.log("🔬 ModerationGuard eq_principle testi başlatılıyor...");
  console.log("   Contract:", CONTRACT_ADDR);

  const estimate = await client.estimateTransactionFees({
    leaderTimeunitsAllocation: 100n,
    validatorTimeunitsAllocation: 200n,
    rotations: [0n],
  });

  console.log("💰 Fee:", estimate.feeValue.toString());

  // ✅ moderateContent write çağrısı (konsensüs ile değerlendirme)
  const txHash = await client.writeContract({
    address: CONTRACT_ADDR,
    functionName: "moderateContent",
    args: ["https://example.com", "text"],
    fees: {
      distribution: estimate.distribution,
      feeValue: estimate.feeValue,
    },
  });

  console.log("✅ Tx gönderildi:", txHash);
  console.log("\n⏳ Receipt:");
  console.log("   genlayer receipt", txHash);
}

test().catch(err => {
  console.error("❌ Hata:", err);
  process.exit(1);
});
