(() => {
  let storefrontConfig = { ...(window.APP_CONFIG || {}) };
  const apiBaseUrl = String(storefrontConfig.apiBaseUrl || "").replace(/\/$/, "");

  const productNameEl = document.getElementById("product-name");
  const productEyebrowEl = document.getElementById("product-eyebrow");
  const productTaglineEl = document.getElementById("product-tagline");
  const productDescriptionEl = document.getElementById("product-description");
  const highlightsListEl = document.getElementById("highlights-list");
  const detailsListEl = document.getElementById("details-list");
  const coverImageEl = document.getElementById("cover-image");
  const coverFallbackEl = document.getElementById("cover-fallback");

  const priceAmountEl = document.getElementById("price-amount");
  const buyBtn = document.getElementById("buy-btn");
  const claimBtn = document.getElementById("claim-btn");
  const statusEl = document.getElementById("status");
  const paymentSection = document.getElementById("payment-section");
  const claimSection = document.getElementById("claim-section");
  const qrWrapper = document.getElementById("qr-wrapper");
  const solanaLink = document.getElementById("solana-link");
  const downloadHolder = document.getElementById("download-holder");

  applyStorefrontConfig(storefrontConfig);

  let order = null;
  let pollTimer = null;

  buyBtn.addEventListener("click", onBuyClick);
  claimBtn.addEventListener("click", onClaimClick);

  if (!apiBaseUrl || apiBaseUrl.includes("YOUR_API_ID")) {
    setStatus("Set docs/config.js -> apiBaseUrl first.", "warning");
    buyBtn.disabled = true;
    return;
  }

  void loadStorefrontConfigFromBackend();

  async function loadStorefrontConfigFromBackend() {
    const pathOrUrl = getText(storefrontConfig.storefrontConfigPath, "/storefront-config");
    const endpoint = buildStorefrontEndpoint(pathOrUrl);

    try {
      const response = await fetch(endpoint);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Could not load storefront config");
      }

      storefrontConfig = { ...storefrontConfig, ...data };
      applyStorefrontConfig(storefrontConfig);
    } catch (error) {
      console.warn(`Could not load storefront config: ${error.message}`);
    }
  }

  function buildStorefrontEndpoint(pathOrUrl) {
    if (/^https?:\/\//i.test(pathOrUrl)) {
      return pathOrUrl;
    }

    const normalizedPath = pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`;
    return `${apiBaseUrl}${normalizedPath}`;
  }

  async function onBuyClick() {
    setStatus("Creating order...");
    buyBtn.disabled = true;
    claimBtn.disabled = true;
    downloadHolder.textContent = "";
    clearPolling();

    try {
      const response = await fetch(`${apiBaseUrl}/create-order`, {
        method: "POST",
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Could not create order");
      }

      order = {
        orderId: data.order_id,
        claimToken: data.claim_token,
        paymentUri: data.payment_uri,
      };

      if (data.amount_usdc) {
        storefrontConfig = { ...storefrontConfig, priceUsdc: String(data.amount_usdc) };
      }
      if (data.product_name) {
        storefrontConfig = { ...storefrontConfig, productName: String(data.product_name) };
      }
      applyStorefrontConfig(storefrontConfig);

      renderQr(order.paymentUri);
      paymentSection.classList.remove("hidden");
      claimSection.classList.remove("hidden");
      setStatus("Order created. Waiting for payment...");
      startPolling();
    } catch (error) {
      buyBtn.disabled = false;
      setStatus(`Error: ${error.message}`, "error");
    }
  }

  async function onClaimClick() {
    if (!order) {
      return;
    }

    claimBtn.disabled = true;
    setStatus("Claiming link...");

    try {
      const url = new URL(`${apiBaseUrl}/claim-link`);
      url.searchParams.set("order_id", order.orderId);
      url.searchParams.set("claim_token", order.claimToken);

      const response = await fetch(url.toString());
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Could not claim link");
      }

      const anchor = document.createElement("a");
      anchor.href = data.download_url;
      anchor.target = "_blank";
      anchor.rel = "noreferrer";
      anchor.textContent = "Open your download link";

      downloadHolder.innerHTML = "";
      downloadHolder.appendChild(anchor);
      setStatus("Payment confirmed. Download unlocked.", "success");
    } catch (error) {
      claimBtn.disabled = false;
      setStatus(`Error: ${error.message}`, "error");
    }
  }

  function startPolling() {
    clearPolling();
    pollTimer = setInterval(checkPayment, 5000);
    checkPayment();
  }

  function clearPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function checkPayment() {
    if (!order) {
      return;
    }

    try {
      const url = new URL(`${apiBaseUrl}/check-payment`);
      url.searchParams.set("order_id", order.orderId);

      const response = await fetch(url.toString());
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Could not check payment");
      }

      if (data.status === "EXPIRED") {
        clearPolling();
        setStatus("Order expired. Click Buy to generate a new order.", "warning");
        buyBtn.disabled = false;
        claimBtn.disabled = true;
        return;
      }

      if (data.paid) {
        clearPolling();
        claimBtn.disabled = false;
        setStatus("Payment detected. Click Get Link.", "success");
      }
    } catch (error) {
      setStatus(`Check error: ${error.message}`, "error");
    }
  }

  function renderQr(value) {
    qrWrapper.innerHTML = "";
    // qrcode.js attaches a canvas or img element into the target container.
    new QRCode(qrWrapper, {
      text: value,
      width: 200,
      height: 200,
      correctLevel: QRCode.CorrectLevel.M,
    });

    solanaLink.href = value;
  }

  function applyStorefrontConfig(activeConfig) {
    const productName = getText(activeConfig.productName, "My Game");
    const productEyebrow = getText(activeConfig.productEyebrow, "Digital Download");
    const productTagline = getText(activeConfig.productTagline, "A premium game drop with instant unlock.");
    const productDescription = getText(
      activeConfig.productDescription,
      "Pay with USDC, verify on-chain, then claim your private link immediately."
    );
    const productPrice = String(activeConfig.priceUsdc ?? activeConfig.priceSol ?? "--");
    const buyButtonLabel = getText(activeConfig.buyButtonLabel, "Buy Now");
    const coverImageUrl = getText(activeConfig.coverImageUrl, "");
    const coverImageAlt = getText(activeConfig.coverImageAlt, `${productName} cover image`);

    const highlights = getTextList(activeConfig.highlights, [
      "Instant download unlock",
      "USDC checkout on Solana",
      "Simple wallet-friendly flow",
    ]);
    const productDetails = getTextList(activeConfig.productDetails, [
      "Private link delivered after payment confirmation",
      "Works on desktop and mobile browsers",
      "Version details and release notes controlled by your config",
    ]);

    productNameEl.textContent = productName;
    productEyebrowEl.textContent = productEyebrow;
    productTaglineEl.textContent = productTagline;
    productDescriptionEl.textContent = productDescription;
    priceAmountEl.textContent = productPrice;
    buyBtn.textContent = buyButtonLabel;
    document.title = `${productName} | Checkout`;

    renderList(highlightsListEl, highlights);
    renderList(detailsListEl, productDetails);
    renderCover(coverImageUrl, coverImageAlt);
  }

  function renderCover(imageUrl, imageAlt) {
    if (!imageUrl) {
      coverImageEl.removeAttribute("src");
      coverImageEl.classList.add("hidden");
      coverFallbackEl.classList.remove("hidden");
      return;
    }

    coverImageEl.src = imageUrl;
    coverImageEl.alt = imageAlt;
    coverImageEl.classList.remove("hidden");
    coverFallbackEl.classList.add("hidden");

    coverImageEl.addEventListener(
      "error",
      () => {
        coverImageEl.classList.add("hidden");
        coverFallbackEl.classList.remove("hidden");
      },
      { once: true }
    );
  }

  function renderList(target, items) {
    target.innerHTML = "";
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item;
      target.appendChild(li);
    }
  }

  function getText(value, fallback) {
    const parsed = String(value ?? "").trim();
    return parsed || fallback;
  }

  function getTextList(value, fallback) {
    if (!Array.isArray(value)) {
      return fallback;
    }

    const parsed = value.map((entry) => String(entry ?? "").trim()).filter(Boolean);
    return parsed.length > 0 ? parsed : fallback;
  }

  function setStatus(text, tone = "neutral") {
    statusEl.textContent = text;
    statusEl.dataset.tone = tone;
  }
})();
