const API = "/api/v1";
const state = {
  account: null,
  products: [],
  suppliers: [],
  batches: [],
  sales: [],
  purchases: [],
  analytics: null,
  inventory: null,
  chatHistory: [],
  view: "overview",
};
let authGeneration = 0;

const currency = new Intl.NumberFormat("en-EG", {
  style: "currency",
  currency: "EGP",
  maximumFractionDigits: 2,
});
const integer = new Intl.NumberFormat("en-EG", { maximumFractionDigits: 0 });
const cairoDate = new Intl.DateTimeFormat("en-EG", {
  timeZone: "Africa/Cairo",
  day: "numeric",
  month: "short",
  year: "numeric",
});
const cairoDateTime = new Intl.DateTimeFormat("en-EG", {
  timeZone: "Africa/Cairo",
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
});

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (response.status === 204) return null;
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (response.status === 401 && path.startsWith("/")) setAccount(null);
  if (!response.ok) {
    const detail = body?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join("; ")
      : detail || "The request could not be completed.";
    throw new Error(message);
  }
  return body;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function money(value) { return currency.format(Number(value || 0)); }
function quantity(value) { return integer.format(Number(value || 0)); }
function dateOnly(value) {
  if (!value) return "—";
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? escapeHtml(value) : cairoDate.format(date);
}
function dateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : cairoDateTime.format(date);
}
function productName(productId) {
  return state.products.find((product) => product.id === productId)?.name || `Product #${productId}`;
}
function supplierName(supplierId) {
  return state.suppliers.find((supplier) => supplier.id === supplierId)?.name || `Supplier #${supplierId}`;
}

function toast(message, isError = false) {
  const region = document.querySelector("#toast-region");
  const item = document.createElement("div");
  item.className = `toast${isError ? " error" : ""}`;
  item.textContent = message;
  region.append(item);
  window.setTimeout(() => item.remove(), 4200);
}

function setAccount(account) {
  const nextUserId = account?.user_id ?? null;
  const accountChanged = (state.account?.user_id ?? null) !== nextUserId;
  if (accountChanged) {
    authGeneration += 1;
    state.products = [];
    state.suppliers = [];
    state.batches = [];
    state.sales = [];
    state.purchases = [];
    state.analytics = null;
    state.inventory = null;
    state.chatHistory = [];
    renderChat();
    setChatStatus("");
    document.querySelector("#chat-send").disabled = false;
    document.querySelector("#clear-chat").disabled = false;
    document.querySelectorAll(".chat-suggestion").forEach((button) => { button.disabled = false; });
    renderAll();
  }
  state.account = account;
  document.querySelector("#auth-screen").hidden = Boolean(account);
  document.querySelector("#app-shell").hidden = !account;
  if (!account) {
    return;
  }
  setText("#profile-name", account.full_name);
  setText("#profile-avatar", (account.full_name || "P").trim().charAt(0).toUpperCase());
  setText("#pharmacy-name", account.pharmacy_name);
}

function setAuthFeedback(message = "", isSuccess = false) {
  const feedback = document.querySelector("#auth-feedback");
  feedback.textContent = message;
  feedback.classList.toggle("success", isSuccess);
}

function showAuthMode(mode) {
  const isSignup = mode === "signup";
  document.querySelector("#login-panel").hidden = isSignup;
  document.querySelector("#signup-panel").hidden = !isSignup;
  document.querySelector("#auth-title").textContent = isSignup
    ? "Start with a private pharmacy workspace."
    : "Run your pharmacy with clarity.";
  setAuthFeedback();
}

async function submitAuth(path, form) {
  setAuthFeedback();
  const submitButton = form.querySelector("button[type=submit]");
  submitButton.disabled = true;
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formObject(form)),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body?.detail;
      const message = Array.isArray(detail)
        ? detail.map((item) => item.msg).join("; ")
        : detail || "We could not sign you in. Please try again.";
      throw new Error(message);
    }
    form.reset();
    setAccount(body);
    await loadData(true);
  } catch (error) {
    setAuthFeedback(error.message || "We could not connect. Please try again.");
  } finally {
    submitButton.disabled = false;
  }
}

async function startApp() {
  try {
    const response = await fetch("/auth/me");
    if (!response.ok) {
      setAccount(null);
      return;
    }
    setAccount(await response.json());
    await loadData(true);
  } catch {
    setAccount(null);
    setAuthFeedback("The pharmacy service could not be reached. Refresh the page and try again.");
  }
}

async function signOut() {
  try {
    await fetch("/auth/logout", { method: "POST" });
  } finally {
    setAccount(null);
    showAuthMode("login");
    setAuthFeedback("You have signed out.", true);
  }
}

function showView(name) {
  state.view = name;
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.querySelector(`#view-${name}`)?.classList.add("active");
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.classList.toggle("active", link.dataset.view === name);
  });
  const nav = document.querySelector(`.nav-link[data-view="${name}"]`);
  document.querySelector("#breadcrumb-current").textContent = nav?.textContent.trim() || "Overview";
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (name === "sales" && !document.querySelector("#sale-lines .dynamic-line")) addDynamicLine("sale");
  if (name === "purchases" && !document.querySelector("#purchase-lines .dynamic-line")) addDynamicLine("purchase");
  if (name === "chat") document.querySelector("#chat-message").focus({ preventScroll: true });
}

function setChatStatus(message, isError = false) {
  const status = document.querySelector("#chat-status");
  status.textContent = message;
  status.classList.toggle("error", isError);
}

function renderChat() {
  const transcript = document.querySelector("#chat-transcript");
  if (!transcript) return;
  transcript.replaceChildren();
  for (const message of state.chatHistory) {
    const bubble = document.createElement("article");
    bubble.className = `chat-message ${message.role}`;
    const label = document.createElement("p");
    label.className = "chat-message-label";
    label.textContent = message.role === "user" ? "You" : "AI assistant";
    const content = document.createElement("p");
    content.className = "chat-message-content";
    content.textContent = message.content;
    bubble.append(label, content);
    transcript.append(bubble);
  }
  transcript.scrollTop = transcript.scrollHeight;
}

function trimHistoryForRequest(message) {
  const history = state.chatHistory.slice(-12);
  const total = () => history.reduce((sum, item) => sum + item.content.length, message.length);
  while (history.length && total() > 15000) history.splice(0, 2);
  return history;
}

async function submitChatMessage(message) {
  if (!message || message.length > 4000 || !state.account) return;
  const textarea = document.querySelector("#chat-message");
  const sendButton = document.querySelector("#chat-send");
  const clearButton = document.querySelector("#clear-chat");
  const suggestions = document.querySelectorAll(".chat-suggestion");
  const userId = state.account.user_id;
  const generation = authGeneration;
  const history = trimHistoryForRequest(message);
  sendButton.disabled = true;
  clearButton.disabled = true;
  suggestions.forEach((button) => { button.disabled = true; });
  setChatStatus("Thinking…");
  try {
    const result = await api("/chat/messages", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    });
    if (generation !== authGeneration || userId !== state.account?.user_id) return;
    state.chatHistory = [...history, { role: "user", content: message }, { role: "assistant", content: result.answer }].slice(-12);
    renderChat();
    textarea.value = "";
    setChatStatus("");
  } catch (error) {
    if (generation === authGeneration && userId === state.account?.user_id) {
      setChatStatus(error.message || "The assistant could not answer. Please try again.", true);
    }
  } finally {
    if (generation === authGeneration && userId === state.account?.user_id) {
      sendButton.disabled = false;
      clearButton.disabled = false;
      suggestions.forEach((button) => { button.disabled = false; });
    }
  }
}

async function loadData(showConnectionError = false) {
  const generation = authGeneration;
  const requests = [
    ["products", `${API}/products/?limit=500`],
    ["suppliers", `${API}/suppliers/?limit=500`],
    ["batches", `${API}/inventory/batches/?limit=500`],
    ["sales", `${API}/sales/?limit=100`],
    ["purchases", `${API}/purchases/?limit=100`],
    ["analytics", `${API}/analytics/sales/summary`],
    ["inventory", `${API}/analytics/inventory?expiry_window_days=30`],
    ["topProducts", `${API}/analytics/sales/top-products?limit=5`],
  ];
  const settled = await Promise.allSettled(requests.map(([, path]) => api(path)));
  if (generation !== authGeneration || !state.account) return false;
  let failed = false;
  settled.forEach((result, index) => {
    const key = requests[index][0];
    if (result.status === "fulfilled") state[key] = result.value;
    else failed = true;
  });
  renderAll();
  if (failed && showConnectionError) {
    toast("Some information could not load. Check that the pharmacy service is running.", true);
  }
  return !failed;
}

function renderAll() {
  renderDashboard();
  renderProducts();
  renderSuppliers();
  renderInventory();
  renderSales();
  renderPurchases();
  refreshProductOptions();
}

function renderDashboard() {
  const summary = state.analytics;
  const stock = state.inventory;
  setText("#metric-revenue", summary ? money(summary.revenue) : "—");
  setText("#metric-profit", summary ? money(summary.gross_profit) : "—");
  setText("#metric-margin", summary ? `${Number(summary.gross_margin_percent || 0).toFixed(1)}% gross margin` : "After batch cost");
  setText("#metric-stock", stock ? quantity(stock.sellable_units) : "—");
  setText("#metric-stock-value", stock ? `${money(stock.inventory_cost_value)} at cost` : "Across all products");
  setText("#metric-expiring", stock ? quantity(stock.near_expiry_units) : "—");

  const products = state.topProducts || [];
  const topRoot = document.querySelector("#top-products");
  if (!products.length) {
    topRoot.innerHTML = '<div class="empty-placeholder">No completed sales yet. Your best sellers will appear here.</div>';
  } else {
    const max = Math.max(...products.map((item) => Number(item.units_sold)), 1);
    topRoot.innerHTML = products.map((item) => `
      <div class="product-bar-row">
        <span class="product-bar-name" title="${escapeHtml(item.product_name)}">${escapeHtml(item.product_name)}</span>
        <span class="product-bar-track"><span class="product-bar-fill" style="width:${Math.max(4, (Number(item.units_sold) / max) * 100)}%"></span></span>
        <span class="product-bar-count">${quantity(item.units_sold)}</span>
      </div>`).join("");
  }

  const expiryRoot = document.querySelector("#expiry-list");
  const expiring = stock?.near_expiry_batches || [];
  if (!expiring.length) {
    expiryRoot.innerHTML = '<div class="empty-placeholder">Nothing expires in the next 30 days.</div>';
  } else {
    expiryRoot.innerHTML = expiring.slice(0, 5).map((batch) => `
      <div class="expiry-row">
        <div><div class="expiry-name">${escapeHtml(batch.product_name)}</div><div class="expiry-detail">Batch ${escapeHtml(batch.batch_number)} · ${quantity(batch.quantity)} units · ${dateOnly(batch.expiry_date)}</div></div>
        <span class="expiry-days">${batch.days_to_expiry === 0 ? "Today" : `${batch.days_to_expiry} days`}</span>
      </div>`).join("");
  }

  const recent = (state.sales || []).slice(0, 6);
  document.querySelector("#recent-sales").innerHTML = recent.length
    ? recent.map(saleRow).join("")
    : '<tr><td colspan="5" class="table-empty">No sales recorded yet. Create your first sale from the Sales page.</td></tr>';
}

function saleRow(sale, includeAllocation = false) {
  const units = (sale.items || []).reduce((total, item) => total + Number(item.quantity), 0);
  const allocationCount = (sale.items || []).reduce((total, item) => total + (item.batch_allocations || []).length, 0);
  return `<tr>
    <td><span class="sale-reference">#${String(sale.id).padStart(5, "0")}</span></td>
    <td>${quantity(units)} ${units === 1 ? "unit" : "units"}</td>
    <td>${dateTime(sale.sale_date)}</td>
    <td class="align-right table-primary">${money(sale.total_amount)}</td>
    <td>${includeAllocation ? `<span class="table-secondary">${quantity(allocationCount)} batch ${allocationCount === 1 ? "allocation" : "allocations"}</span>` : '<span class="status-pill">Completed</span>'}</td>
  </tr>`;
}

function renderProducts(filter = "") {
  const query = filter.trim().toLowerCase();
  const list = (state.products || []).filter((product) => `${product.name} ${product.barcode || ""}`.toLowerCase().includes(query));
  setText("#product-count", `${list.length} active ${list.length === 1 ? "product" : "products"}`);
  document.querySelector("#products-table").innerHTML = list.length
    ? list.map((product) => `<tr>
        <td><span class="table-primary">${escapeHtml(product.name)}</span><div class="table-secondary">Product #${product.id}</div></td>
        <td>${escapeHtml(product.barcode || "—")}</td><td>${money(product.selling_price)}</td>
        <td><span class="status-pill">Active</span></td>
        <td class="align-right"><button class="action-link danger-link" data-archive-product="${product.id}">Archive</button></td>
      </tr>`).join("")
    : `<tr><td colspan="5" class="table-empty">${query ? "No products match that search." : "No products yet. Add your first product above."}</td></tr>`;
}

function renderSuppliers() {
  const list = state.suppliers || [];
  setText("#supplier-count", `${list.length} active ${list.length === 1 ? "supplier" : "suppliers"}`);
  document.querySelector("#suppliers-table").innerHTML = list.length
    ? list.map((supplier) => `<tr>
        <td><span class="table-primary">${escapeHtml(supplier.name)}</span><div class="table-secondary">Supplier #${supplier.id}</div></td>
        <td>${escapeHtml(supplier.contact_person || "—")}</td><td>${escapeHtml(supplier.phone || "—")}</td>
        <td>${escapeHtml(supplier.email || "—")}</td><td><span class="status-pill">Active</span></td>
      </tr>`).join("")
    : '<tr><td colspan="5" class="table-empty">No suppliers yet. Add a supplier to create purchase orders.</td></tr>';
}

function renderInventory() {
  const stock = state.inventory;
  setText("#inventory-on-hand", stock ? quantity(stock.on_hand_units) : "—");
  setText("#inventory-value", stock ? money(stock.inventory_cost_value) : "—");
  setText("#inventory-expired", stock ? quantity(stock.expired_units) : "—");
  const query = (document.querySelector("#batch-filter")?.value || "").trim().toLowerCase();
  const list = (state.batches || []).filter((batch) => `${productName(batch.product_id)} ${batch.batch_number}`.toLowerCase().includes(query));
  document.querySelector("#batches-table").innerHTML = list.length
    ? list.map((batch) => {
      const isExpired = batch.expiry_date < cairoTodayISO();
      const status = isExpired ? '<span class="status-pill cancelled">Expired</span>' : '<span class="status-pill">Sellable</span>';
      return `<tr><td><span class="table-primary">${escapeHtml(productName(batch.product_id))}</span><div class="table-secondary">Product #${batch.product_id}</div></td><td>${escapeHtml(batch.batch_number)}</td><td>${quantity(batch.quantity)}</td><td>${money(batch.unit_cost)}</td><td>${dateOnly(batch.expiry_date)}</td><td>${status}</td></tr>`;
    }).join("")
    : `<tr><td colspan="6" class="table-empty">${query ? "No batches match that search." : "No stock recorded yet."}</td></tr>`;
}

function renderSales() {
  const rows = state.sales || [];
  document.querySelector("#sales-table").innerHTML = rows.length
    ? rows.map((sale) => saleRow(sale, true)).join("")
    : '<tr><td colspan="5" class="table-empty">No sales recorded yet.</td></tr>';
}

function renderPurchases() {
  const statusFilter = document.querySelector("#purchase-status-filter")?.value || "";
  const purchases = (state.purchases || []).filter((purchase) => !statusFilter || purchase.status === statusFilter);
  const root = document.querySelector("#purchases-list");
  if (!purchases.length) {
    root.innerHTML = '<div class="table-empty">No purchase orders to show.</div>';
    return;
  }
  root.innerHTML = purchases.map((purchase) => {
    const status = purchase.status.replaceAll("_", " ");
    const lines = (purchase.items || []).map((item) => {
      const remaining = Number(item.ordered_quantity) - Number(item.received_quantity);
      const action = remaining > 0 && ["ordered", "partially_received"].includes(purchase.status)
        ? `<button class="action-link" data-receive-purchase="${purchase.id}" data-item-id="${item.id}" data-product="${escapeHtml(productName(item.product_id))}" data-remaining="${remaining}">Receive batch →</button>`
        : `<span class="table-secondary">${remaining === 0 ? "Fully received" : ""}</span>`;
      return `<div class="purchase-card-line"><div><div class="purchase-line-title">${escapeHtml(productName(item.product_id))}</div><div class="purchase-line-meta">${quantity(item.received_quantity)} of ${quantity(item.ordered_quantity)} received · ${money(item.unit_cost)} / unit</div></div><div>${action}</div></div>`;
    }).join("");
    const cancel = purchase.status === "ordered" ? `<button class="action-link danger-link" data-cancel-purchase="${purchase.id}">Cancel</button>` : "";
    return `<article class="purchase-card"><div class="purchase-card-head"><div><div class="purchase-card-title">${escapeHtml(supplierName(purchase.supplier_id))} <span class="table-secondary">· Order #${purchase.id}</span></div><div class="purchase-card-meta">${dateTime(purchase.order_date)} · ${money(purchase.total_cost)}</div></div><div class="heading-actions"><span class="status-pill ${purchase.status}">${escapeHtml(status)}</span>${cancel}</div></div><div class="purchase-card-items">${lines}</div></article>`;
  }).join("");
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value;
}

function refreshProductOptions() {
  const html = `<option value="">Choose a product</option>${(state.products || []).map((product) => `<option value="${product.id}">${escapeHtml(product.name)} · ${money(product.selling_price)}</option>`).join("")}`;
  document.querySelectorAll("select.product-options, select.line-product").forEach((select) => {
    const selected = select.value;
    select.innerHTML = html;
    if (selected) select.value = selected;
  });
  const supplierSelect = document.querySelector("#purchase-supplier");
  if (supplierSelect) {
    const selected = supplierSelect.value;
    supplierSelect.innerHTML = `<option value="">Choose a supplier</option>${(state.suppliers || []).map((supplier) => `<option value="${supplier.id}">${escapeHtml(supplier.name)}</option>`).join("")}`;
    if (selected) supplierSelect.value = selected;
  }
}

function addDynamicLine(kind) {
  const root = document.querySelector(kind === "sale" ? "#sale-lines" : "#purchase-lines");
  if (!root) return;
  const row = document.createElement("div");
  row.className = `dynamic-line ${kind === "purchase" ? "purchase-line" : ""}`;
  const options = `<option value="">Choose a product</option>${(state.products || []).map((product) => `<option value="${product.id}">${escapeHtml(product.name)} · ${money(product.selling_price)}</option>`).join("")}`;
  if (kind === "sale") {
    row.innerHTML = `<label>Product<select class="line-product" required>${options}</select></label><label>Quantity<input class="line-quantity" type="number" min="1" max="100000" step="1" value="1" required /></label><button type="button" class="remove-line" aria-label="Remove product">×</button>`;
  } else {
    row.innerHTML = `<label>Product<select class="line-product" required>${options}</select></label><label>Order quantity<input class="line-quantity" type="number" min="1" max="100000" step="1" value="1" required /></label><label>Unit cost (EGP)<input class="line-cost" type="number" min="0" step="0.01" placeholder="0.00" required /></label><button type="button" class="remove-line" aria-label="Remove product">×</button>`;
  }
  root.append(row);
}

function cairoTodayISO() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Cairo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

function openReceiveDialog(button) {
  const dialog = document.querySelector("#receive-dialog");
  const form = document.querySelector("#receive-form");
  form.elements.purchase_id.value = button.dataset.receivePurchase;
  form.elements.purchase_item_id.value = button.dataset.itemId;
  form.elements.quantity.max = button.dataset.remaining;
  form.elements.quantity.value = button.dataset.remaining;
  form.elements.expiry_date.min = cairoTodayISO();
  document.querySelector("#receive-line-description").textContent = `${button.dataset.product} · ${button.dataset.remaining} units remaining on this order`;
  dialog.showModal();
}

function formObject(form) { return Object.fromEntries(new FormData(form).entries()); }

document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
document.querySelectorAll("[data-open-view]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.openView)));
document.querySelectorAll("[data-scroll-to]").forEach((button) => button.addEventListener("click", () => {
  document.querySelector(`#${button.dataset.scrollTo}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  document.querySelector(`#${button.dataset.scrollTo} input`)?.focus({ preventScroll: true });
}));

document.querySelector("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const textarea = document.querySelector("#chat-message");
  const message = textarea.value.trim();
  if (!message) return;
  await submitChatMessage(message);
});
document.querySelector("#chat-message").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    document.querySelector("#chat-form").requestSubmit();
  }
});
document.querySelectorAll(".chat-suggestion").forEach((button) => button.addEventListener("click", () => {
  const textarea = document.querySelector("#chat-message");
  textarea.value = button.textContent.trim();
  textarea.focus();
}));
document.querySelector("#clear-chat").addEventListener("click", () => {
  state.chatHistory = [];
  renderChat();
  setChatStatus("Conversation cleared.");
  document.querySelector("#chat-message").focus();
});

document.querySelector("#create-product-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formObject(form);
  data.selling_price = Number(data.selling_price);
  if (!data.barcode) delete data.barcode;
  try {
    await api("/products/", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    await loadData();
    toast("Product added to the catalog.");
  } catch (error) { toast(error.message, true); }
});

document.querySelector("#create-supplier-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formObject(form);
  ["contact_person", "phone", "email"].forEach((key) => { if (!data[key]) delete data[key]; });
  try {
    await api("/suppliers/", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    await loadData();
    toast("Supplier saved.");
  } catch (error) { toast(error.message, true); }
});

document.querySelector("#create-batch-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formObject(form);
  data.product_id = Number(data.product_id);
  data.quantity = Number(data.quantity);
  data.unit_cost = Number(data.unit_cost);
  try {
    await api("/inventory/batches/", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    await loadData();
    toast("Opening stock batch recorded.");
  } catch (error) { toast(error.message, true); }
});

document.querySelector("#add-sale-line").addEventListener("click", () => addDynamicLine("sale"));
document.querySelector("#add-purchase-line").addEventListener("click", () => addDynamicLine("purchase"));

document.querySelector("#create-sale-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const items = [...document.querySelectorAll("#sale-lines .dynamic-line")].map((row) => ({
    product_id: Number(row.querySelector(".line-product").value),
    quantity: Number(row.querySelector(".line-quantity").value),
  }));
  if (items.some((item) => !item.product_id)) return toast("Choose a product for each sale line.", true);
  try {
    const sale = await api("/sales/", { method: "POST", body: JSON.stringify({ items }) });
    document.querySelector("#sale-lines").innerHTML = "";
    await loadData();
    toast(`Sale #${sale.id} completed · ${money(sale.total_amount)}`);
  } catch (error) { toast(error.message, true); }
});

document.querySelector("#create-purchase-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const supplierId = Number(form.elements.supplier_id.value);
  const items = [...document.querySelectorAll("#purchase-lines .dynamic-line")].map((row) => ({
    product_id: Number(row.querySelector(".line-product").value),
    ordered_quantity: Number(row.querySelector(".line-quantity").value),
    unit_cost: Number(row.querySelector(".line-cost").value),
  }));
  if (!supplierId) return toast("Choose a supplier for this purchase.", true);
  if (items.some((item) => !item.product_id)) return toast("Choose a product for each purchase line.", true);
  try {
    const purchase = await api("/purchases/", { method: "POST", body: JSON.stringify({ supplier_id: supplierId, items }) });
    form.reset();
    document.querySelector("#purchase-lines").innerHTML = "";
    await loadData();
    toast(`Purchase order #${purchase.id} created.`);
  } catch (error) { toast(error.message, true); }
});

document.querySelector("#receive-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formObject(form);
  const purchaseId = Number(data.purchase_id);
  delete data.purchase_id;
  data.purchase_item_id = Number(data.purchase_item_id);
  data.quantity = Number(data.quantity);
  try {
    await api(`/purchases/${purchaseId}/receipts`, { method: "POST", body: JSON.stringify({ items: [data] }) });
    form.reset();
    document.querySelector("#receive-dialog").close();
    await loadData();
    toast("Delivery received and inventory batch created.");
  } catch (error) { toast(error.message, true); }
});

document.querySelector("#close-receive").addEventListener("click", () => document.querySelector("#receive-dialog").close());
document.querySelector("#cancel-receive").addEventListener("click", () => document.querySelector("#receive-dialog").close());
document.querySelector("#refresh-button").addEventListener("click", async () => {
  await loadData(true);
  toast("Workspace refreshed.");
});
document.querySelector("#product-filter").addEventListener("input", (event) => renderProducts(event.currentTarget.value));
document.querySelector("#batch-filter").addEventListener("input", renderInventory);
document.querySelector("#purchase-status-filter").addEventListener("change", renderPurchases);
document.querySelector("#global-search").addEventListener("input", (event) => {
  if (state.view !== "products") showView("products");
  document.querySelector("#product-filter").value = event.currentTarget.value;
  renderProducts(event.currentTarget.value);
});

document.addEventListener("click", async (event) => {
  const archive = event.target.closest("[data-archive-product]");
  if (archive) {
    const productId = archive.dataset.archiveProduct;
    if (!window.confirm("Archive this product? It will remain in transaction history.")) return;
    try {
      await api(`/products/${productId}`, { method: "DELETE" });
      await loadData();
      toast("Product archived.");
    } catch (error) { toast(error.message, true); }
  }
  const receive = event.target.closest("[data-receive-purchase]");
  if (receive) openReceiveDialog(receive);
  const cancel = event.target.closest("[data-cancel-purchase]");
  if (cancel) {
    try {
      await api(`/purchases/${cancel.dataset.cancelPurchase}/cancel`, { method: "POST" });
      await loadData();
      toast("Purchase order cancelled.");
    } catch (error) { toast(error.message, true); }
  }
  const remove = event.target.closest(".remove-line");
  if (remove) {
    const parent = remove.closest(".dynamic-lines");
    const lines = parent.querySelectorAll(".dynamic-line");
    if (lines.length > 1) remove.closest(".dynamic-line").remove();
    else {
      const row = remove.closest(".dynamic-line");
      row.querySelector("select").value = "";
      row.querySelectorAll("input").forEach((input) => { input.value = ""; });
    }
  }
});

document.querySelector("#login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  submitAuth("/auth/login", event.currentTarget);
});
document.querySelector("#signup-form").addEventListener("submit", (event) => {
  event.preventDefault();
  submitAuth("/auth/signup", event.currentTarget);
});
document.querySelector("#show-signup").addEventListener("click", () => showAuthMode("signup"));
document.querySelector("#show-login").addEventListener("click", () => showAuthMode("login"));
document.querySelector("#logout-button").addEventListener("click", signOut);
document.querySelector("#top-logout-button").addEventListener("click", signOut);

document.querySelector("#today-label").textContent = new Intl.DateTimeFormat("en-EG", {
  timeZone: "Africa/Cairo", weekday: "short", day: "numeric", month: "short",
}).format(new Date());
document.querySelector("#welcome-label").textContent = `PHARMACY OVERVIEW · ${new Intl.DateTimeFormat("en-EG", {
  timeZone: "Africa/Cairo", weekday: "long", month: "long", day: "numeric",
}).format(new Date()).toUpperCase()}`;

addDynamicLine("sale");
addDynamicLine("purchase");
startApp();
