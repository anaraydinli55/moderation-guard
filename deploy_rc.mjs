import { createClient } from "genlayer-js";
import { studioDevnet } from "genlayer-js/chains";
import { privateKeyToAccount } from "viem/accounts";
import fs from "fs";

const rawKey = process.env.PRIVATE_KEY;
if (!rawKey || rawKey.length < 66) {
  console.error("❌ PRIVATE_KEY eksik veya geçersiz!");
  process.exit(1);
}

const privateKey = rawKey.startsWith("0x") ? rawKey : "0x" + rawKey;
const account = privateKeyToAccount(privateKey);

const client = createClient({
  chain: studioDevnet,
  account: account,
});

console.log("🔑 Deployer:", account.address);
console.log("⛓️  Chain:   ", studioDevnet.name, "(ID:", studioDevnet.id, ")");

const contractPath = process.argv[2] || "./ModerationGuard_RC.py";
if (!fs.existsSync(contractPath)) {
  console.error("❌ Contract bulunamadı:", contractPath);
  process.exit(1);
}

const contractCode = fs.readFileSync(contractPath, "utf8");
console.log("📄 Contract:", contractPath, "(", contractCode.length, "chars )");

async function deploy() {
  console.log("\n🚀 Fee estimate alınıyor...");

  const estimate = await client.estimateTransactionFees({
    leaderTimeunitsAllocation: 100n,
    validatorTimeunitsAllocation: 200n,
    rotations: [0n],
  });

  // ✅ BigInt'leri string'e çevirerek logla
  console.log("💰 Fee estimate:");
  console.log("   feeValue:", estimate.feeValue.toString());
  console.log("   distribution:", JSON.stringify(estimate.distribution, (_, v) => typeof v === "bigint" ? v.toString() : v));

  console.log("\n🚀 Deploy başlatılıyor...");
  const txHash = await client.deployContract({
    code: contractCode,
    args: [],
    fees: {
      distribution: estimate.distribution,
      feeValue: estimate.feeValue,
    },
  });

  console.log("✅ Tx gönderildi:", txHash);
  console.log("\n⏳ Receipt için:");
  console.log("   genlayer receipt", txHash, "--status FINALIZED");
  fs.writeFileSync("pending_tx.txt", txHash + "\n");
}

deploy().catch(err => {
  console.error("❌ Hata:", err);
  process.exit(1);
});
