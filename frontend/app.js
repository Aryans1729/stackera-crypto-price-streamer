(() => {
  const rowsEl = document.getElementById("rows");
  const statusTextEl = document.getElementById("statusText");
  const statusDotEl = document.getElementById("statusDot");

  const fmtPrice = (n) =>
    Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";

  const fmtPct = (n) => (Number.isFinite(n) ? `${n.toFixed(2)}%` : "—");

  const setStatus = (kind, text) => {
    statusTextEl.textContent = text;
    if (kind === "connected") {
      statusDotEl.style.background = "var(--good)";
      statusDotEl.style.boxShadow = "0 0 0 6px rgba(56, 217, 150, 0.14)";
      return;
    }
    if (kind === "connecting") {
      statusDotEl.style.background = "var(--warn)";
      statusDotEl.style.boxShadow = "0 0 0 6px rgba(255, 200, 97, 0.14)";
      return;
    }
    statusDotEl.style.background = "var(--bad)";
    statusDotEl.style.boxShadow = "0 0 0 6px rgba(255, 92, 122, 0.14)";
  };

  const defaultWsUrl = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const host = location.hostname || "localhost";
    const port = host === "localhost" || host === "127.0.0.1" ? "8000" : location.port;
    return `${proto}://${host}${port ? `:${port}` : ""}/ws`;
  };

  const getWsUrl = () => {
    const params = new URLSearchParams(location.search);
    let url = params.get("ws") || defaultWsUrl();
    const sym = params.get("symbol");
    if (sym) {
      url += (url.includes("?") ? "&" : "?") + "symbol=" + encodeURIComponent(sym);
    }
    return url;
  };

  const rowMap = new Map();

  const ensureRow = (symbol) => {
    if (rowMap.has(symbol)) return rowMap.get(symbol);
    const row = document.createElement("div");
    row.className = "table-row mono";
    row.innerHTML = `
      <span class="cell-symbol"></span>
      <span class="cell-price"></span>
      <span class="cell-change"></span>
      <span class="cell-time"></span>
    `;
    rowsEl.appendChild(row);
    rowMap.set(symbol, row);
    return row;
  };

  const updateRow = (data) => {
    const sym = data.symbol;
    if (!sym) return;
    const row = ensureRow(sym);
    row.querySelector(".cell-symbol").textContent = sym;
    row.querySelector(".cell-price").textContent = fmtPrice(Number(data.price));
    const pct = Number(data.change_percent);
    const ch = row.querySelector(".cell-change");
    ch.textContent = fmtPct(pct);
    ch.style.color = Number.isFinite(pct) && pct < 0 ? "var(--bad)" : "var(--good)";
    const ts = data.timestamp ? new Date(data.timestamp) : null;
    row.querySelector(".cell-time").textContent =
      ts && !Number.isNaN(ts.getTime()) ? ts.toLocaleTimeString() : "—";
  };

  let ws = null;
  let reconnectAttempt = 0;
  let reconnectTimer = null;

  const connect = () => {
    const wsUrl = getWsUrl();
    setStatus("connecting", `Connecting…`);

    try {
      ws = new WebSocket(wsUrl);
    } catch {
      scheduleReconnect();
      return;
    }

    ws.addEventListener("open", () => {
      reconnectAttempt = 0;
      setStatus("connected", "Connected");
    });

    ws.addEventListener("message", (evt) => {
      let data = null;
      try {
        data = JSON.parse(evt.data);
      } catch {
        return;
      }
      updateRow(data);
    });

    ws.addEventListener("close", () => {
      setStatus("disconnected", "Disconnected");
      scheduleReconnect();
    });

    ws.addEventListener("error", () => {
      setStatus("disconnected", "Disconnected");
      try {
        ws.close();
      } catch {}
    });
  };

  const scheduleReconnect = () => {
    if (reconnectTimer) return;
    reconnectAttempt += 1;
    const base = Math.min(15_000, 500 * 2 ** Math.min(6, reconnectAttempt));
    const jitter = Math.floor(Math.random() * 250);
    const waitMs = base + jitter;

    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, waitMs);
  };

  connect();
})();
