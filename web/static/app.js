const ROBINHOOD_CHAIN = {
  chainId: "0x1237",
  chainName: "Robinhood Chain",
  nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 },
  rpcUrls: ["https://rpc.mainnet.chain.robinhood.com"],
  blockExplorerUrls: ["https://robinhoodchain.blockscout.com"],
};

const params = new URLSearchParams(window.location.search);

function getSessionId() {
  const fromQuery = params.get("session");
  if (fromQuery) return fromQuery;
  const match = window.location.pathname.match(/^\/verify\/([A-Za-z0-9_-]+)$/);
  return match ? match[1] : null;
}

const sessionId = getSessionId();

const connectBtn = document.getElementById("connect-btn");
const verifyBtn = document.getElementById("verify-btn");
const statusEl = document.getElementById("status");
const walletDisplay = document.getElementById("wallet-display");
const walletBox = document.getElementById("wallet-box");
const actionsEl = document.getElementById("actions");
const stepConnect = document.getElementById("step-connect");
const stepSign = document.getElementById("step-sign");
const stepDone = document.getElementById("step-done");

let sessionData = null;
let connectedAddress = null;
let verifying = false;

function shortAddress(address) {
  if (!address || address.length < 12) return address || "";
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

function setStep(activeStep) {
  [stepConnect, stepSign, stepDone].forEach((el) => {
    el.classList.remove("active", "done");
  });
  if (activeStep === "connect") stepConnect.classList.add("active");
  if (activeStep === "sign") {
    stepConnect.classList.add("done");
    stepSign.classList.add("active");
  }
  if (activeStep === "done") {
    stepConnect.classList.add("done");
    stepSign.classList.add("done");
    stepDone.classList.add("done");
  }
}

function setStatus(message, type = "info", html = false) {
  statusEl.className = type;
  if (html) {
    statusEl.innerHTML = message;
  } else {
    statusEl.textContent = message;
  }
}

function friendlyError(status, detail) {
  if (status === 410) {
    return detail || "This link was already used. Run /verify in Discord for a fresh link.";
  }
  if (status === 403) {
    return detail || "This wallet does not hold qualifying Pixel Gardens NFTs.";
  }
  if (status === 409) {
    return detail || "This wallet is already linked to another Discord account.";
  }
  if (status === 400) {
    return detail || "Signature was rejected. Try again.";
  }
  if (status === 503) {
    return detail || "Discord bot is still starting. Wait a few seconds and try again.";
  }
  return detail || "Something went wrong. Try again from Discord.";
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
    setStatus("Missing verification session. Go back to Discord and run /verify again.", "error");
    connectBtn.disabled = true;
    return;
  }

  const res = await fetch(`/api/session/${sessionId}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    setStatus(friendlyError(res.status, body.detail), "error");
    connectBtn.disabled = true;
    return;
  }

  sessionData = await res.json();
  setStatus("Ready when you are — connect your wallet to start.", "info");
}

function showSuccess(body) {
  setStep("done");
  actionsEl.classList.add("hidden");
  walletBox.classList.add("visible");
  walletDisplay.textContent = shortAddress(body.wallet || connectedAddress);

  const roles = Array.isArray(body.roles) ? body.roles : [];
  const balance = body.balances?.PG;
  const roleHtml = roles.map((role) => `<span class="role-pill">${role}</span>`).join("");
  const balanceText =
    typeof balance === "number" ? `<div style="margin-top:10px;color:#b6c2cf;">PG balance: ${balance}</div>` : "";

  setStatus(
    `<div class="success-title">Verified successfully</div>` +
      `<div>Your Discord roles are updated. You can close this page.</div>` +
      (roleHtml ? `<div>${roleHtml}</div>` : "") +
      balanceText,
    "success",
    true
  );
}

async function submitVerification() {
  if (!sessionData || !connectedAddress || verifying) return;
  verifying = true;
  verifyBtn.disabled = true;
  setStep("sign");

  try {
    setStatus("Approve the signature in MetaMask — no gas fee required.", "info");
    const signature = await window.ethereum.request({
      method: "personal_sign",
      params: [sessionData.message, connectedAddress],
    });

    setStatus("Checking your Pixel Gardens holdings...", "info");
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
      throw new Error(friendlyError(res.status, body.detail));
    }

    showSuccess(body);
  } finally {
    verifying = false;
    if (!statusEl.classList.contains("success")) {
      verifyBtn.disabled = false;
    }
  }
}

connectBtn.addEventListener("click", async () => {
  if (!window.ethereum) {
    setStatus("MetaMask not found. Install MetaMask, then refresh this page.", "error");
    return;
  }

  try {
    connectBtn.disabled = true;
    setStatus("Connecting wallet and switching to Robinhood Chain...", "info");
    await ensureRobinhoodChain();

    const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
    connectedAddress = accounts[0];
    walletBox.classList.add("visible");
    walletDisplay.textContent = shortAddress(connectedAddress);
    verifyBtn.disabled = false;
    setStep("sign");
    setStatus("Wallet connected. Click Sign & Verify when you're ready.", "info");
  } catch (err) {
    connectBtn.disabled = false;
    if (err.code === 4001) {
      setStatus("Wallet connection was cancelled.", "error");
    } else {
      setStatus(err.message || "Failed to connect wallet.", "error");
    }
  }
});

verifyBtn.addEventListener("click", async () => {
  if (!sessionData || !connectedAddress) return;

  try {
    await submitVerification();
  } catch (err) {
    setStatus(err.message || "Verification failed.", "error");
  }
});

loadSession();
