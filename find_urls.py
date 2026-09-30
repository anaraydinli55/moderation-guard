import os
import re
import json

print("=== 1. SDK / Chains İçindeki Resmi URL'ler ===")
found_urls = set()
for root, _, files in os.walk("node_modules"):
    if "genlayer" in root:
        for file in files:
            if file.endswith((".js", ".mjs", ".json", ".d.ts")):
                try:
                    with open(os.path.join(root, file), "r", errors="ignore") as f:
                        c = f.read()
                        matches = re.findall(r"https?://[a-zA-Z0-9\.\-_/]+genlayer[a-zA-Z0-9\.\-_/]*", c)
                        found_urls.update(matches)
                except Exception:
                    pass

for u in sorted(found_urls):
    print(" ->", u)

print("\n=== 2. Kontrat Adresimiz İçin Geçerli URL Seçenekleri ===")
addr_mix = "0xA1b90B417c0b37611d9a49DE09906f5550704C09"
addr_lower = addr_mix.lower()

candidates = [
    f"https://studio.genlayer.com/contracts/{addr_mix}",
    f"https://studio.genlayer.com/contracts/{addr_lower}",
    f"https://studio.genlayer.com/contract/{addr_mix}",
    f"https://studio.genlayer.com/contract/{addr_lower}",
    f"https://studio.genlayer.com/explorer/contracts/{addr_mix}",
    f"https://studio.genlayer.com/explorer/contracts/{addr_lower}",
    f"https://studio-dev.genlayer.com/contracts/{addr_mix}",
    f"https://studio-dev.genlayer.com/contracts/{addr_lower}",
    f"https://explorer.genlayer.com/contract/{addr_mix}",
    f"https://explorer.genlayer.com/contract/{addr_lower}",
    f"https://explorer.genlayer.com/contracts/{addr_mix}",
    f"https://explorer.genlayer.com/contracts/{addr_lower}",
    f"https://explorer-studio.genlayer.com/contract/{addr_mix}",
    f"https://explorer-studio.genlayer.com/contract/{addr_lower}",
    f"https://explorer-bradbury.genlayer.com/contract/{addr_mix}",
    f"https://explorer-bradbury.genlayer.com/contract/{addr_lower}",
]

for url in candidates:
    print(url)
