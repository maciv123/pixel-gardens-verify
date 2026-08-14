const ROBINHOOD_CHAIN = {
  chainId: "0x1237",
  chainName: "Robinhood Chain",
  nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 },
  rpcUrls: ["https://rpc.mainnet.chain.robinhood.com"],
  blockExplorerUrls: ["https://robinhoodchain.blockscout.com"],
};

const params = new URLSearchParams(window.location.search);
const sessionId = params.get("session");

const connectBtn = document.getElementById("connect-btn");
const verifyBtn = document.getElementById("verify-btn");
const statusEl = document.getElementById("status");
const walletDisplay = document.getElementById("wallet-display");

let sessionData = null;
let connectedAddress = null;

function setStatus(message, type = "info") {
  statusEl.textContent = message;
  statusEl.className = type;
}

async function ensureRobinhoodChain() {
  const chainId = await window.ethereum.request({ method: "eth_chainId" });
  if (chainId.toLowerCase() === ROBINHOOD_CHAIN.chainId.toLowerCase()) {
    return;
  }
  try {
    await window.ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: ROBINHOOD_CHAIN.chainId }],
    });
  } catch (err) {
    if (err.code === 4902) {
      await window.ethereum.request({
        method: "wallet_addEthereumChain",
        params: [ROBINHOOD_CHAIN],
      });
    } else {
      throw err;
    }
  }
}

async function loadSession() {
  if (!sessionId) {
    setStatus("Missing verification session. Go back to Discord and click Verify again.", "error");
    connectBtn.disabled = true;
    return;
  }

  const res = await fetch(`/api/session/${sessionId}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    setStatus(body.detail || "Session expired or invalid. Request a new link from Discord.", "error");
    connectBtn.disabled = true;
    return;
  }

  sessionData = await res.json();
  setStatus("Session loaded. Connect your wallet to continue.", "info");
}

async function submitVerification() {
  if (!sessionData || !connectedAddress) return;

  setStatus("Please sign the message in MetaMask...", "info");
  const signature = await window.ethereum.request({
    method: "personal_sign",
    params: [sessionData.message, connectedAddress],
  });

  setStatus("Checking your NFTs on Robinhood Chain...", "info");
  const res = await fetch("/api/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      address: connectedAddress,
      signature,
    }),
  });

  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || "Verification failed.");
  }

  setStatus(
    body.roles?.length
      ? `Verified! Roles assigned: ${body.roles.join(", ")}. Return to Discord.`
      : "Verified! You can close this page and return to Discord.",
    "success"
  );
}

connectBtn.addEventListener("click", async () => {
  if (!window.ethereum) {
    setStatus("MetaMask not found. Install MetaMask to continue.", "error");
    return;
  }

  try {
    connectBtn.disabled = true;
    verifyBtn.disabled = true;
    setStatus("Connecting wallet...", "info");
    await ensureRobinhoodChain();

    const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
    connectedAddress = accounts[0];
    walletDisplay.textContent = connectedAddress;
    await submitVerification();
  } catch (err) {
    connectBtn.disabled = false;
    verifyBtn.disabled = false;
    setStatus(err.message || "Failed to connect wallet.", "error");
  }
});

verifyBtn.addEventListener("click", async () => {
  if (!sessionData || !connectedAddress) return;

  try {
    verifyBtn.disabled = true;
    await submitVerification();
  } catch (err) {
    verifyBtn.disabled = false;
    setStatus(err.message || "Verification failed.", "error");
  }
});

loadSession();
