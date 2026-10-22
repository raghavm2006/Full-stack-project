const initial = new URLSearchParams(window.location.search);
const state = { page: 1, perPage: 20, spamLabel: initial.get("spam_label") || "", isRead: initial.get("is_read") || "", needsFollowUp: initial.get("needs_follow_up") || "", priority: initial.get("priority") || "", search: "", sort: "newest" };
let requestNumber = 0;
let selectedId = null;

function priorityBadge(priority) {
  if (!["HIGH", "MEDIUM", "LOW"].includes(priority)) return "";
  return `<span class="badge badge-priority-${priority}">${priority.toLowerCase()}</span>`;
}
function categoryBadge(category) {
  return `<span class="badge category-badge">${escapeHtml(category || "Uncategorized")}</span>`;
}
function renderEmails(emails) {
  const list = document.getElementById("inboxList");
  list.innerHTML = "";
  document.getElementById("inboxEmpty").classList.toggle("d-none", emails.length > 0);
  emails.forEach(email => {
    const item = document.createElement("a");
    item.href = `/inbox/${email.id}`;
    item.className = `list-group-item list-group-item-action email-row ${email.is_read ? "" : "unread"} ${selectedId === email.id ? "selected" : ""}`;
    const sender = email.sender || "Unknown sender";
    const name = sender.replace(/<[^>]*>/g, "").replace(/"/g, "").trim() || sender;
    const initials = name.split(/\s+/).slice(0, 2).map(part => part[0]).join("").toUpperCase();
    item.innerHTML = `<span class="sender-avatar" aria-hidden="true">${escapeHtml(initials)}</span>
      <div class="email-row-content"><div class="email-row-top"><strong class="sender-name">${escapeHtml(name)}</strong><time>${escapeHtml(formatTimestamp(email.timestamp))}</time></div>
      <div class="email-subject">${escapeHtml(email.subject || "(no subject)")}</div>
      <div class="email-snippet">${escapeHtml(email.snippet || "No preview available")}</div>
      <div class="email-badges">${categoryBadge(email.category)} ${priorityBadge(email.priority)} ${email.spam_label === true ? '<span class="badge bg-danger">Predicted spam</span>' : ""} ${email.needs_follow_up ? '<span class="badge followup-badge">Follow-up</span>' : ""} ${email.is_duplicate ? '<span class="badge category-badge">Duplicate</span>' : ""} ${email.is_read ? "" : '<span class="unread-dot" aria-label="Unread"></span>'}</div></div>`;
    item.addEventListener("click", event => {
      if (!window.matchMedia("(min-width: 1100px)").matches || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      selectedId = email.id;
      list.querySelectorAll(".email-row").forEach(row => row.classList.remove("selected"));
      item.classList.add("selected");
      document.getElementById("previewEmpty").classList.add("d-none");
      const frame = document.getElementById("previewFrame");
      frame.classList.remove("d-none");
      frame.src = `${item.getAttribute("href")}?preview=1`;
    });
    list.appendChild(item);
  });
}
function renderPagination(totalPages, currentPage) {
  const pagination = document.getElementById("inboxPagination");
  pagination.innerHTML = "";
  if (totalPages <= 1) return;
  const pages = [...new Set([1, ...Array.from({length: 5}, (_, i) => currentPage - 2 + i).filter(p => p > 1 && p < totalPages), totalPages])];
  let previous = 0;
  pages.forEach(page => {
    if (previous && page - previous > 1) {
      const gap = document.createElement("li");
      gap.className = "page-item disabled";
      gap.innerHTML = '<span class="page-link">?</span>';
      pagination.appendChild(gap);
    }
    const li = document.createElement("li");
    li.className = `page-item ${page === currentPage ? "active" : ""}`;
    const button = document.createElement("button");
    button.className = "page-link";
    button.textContent = page;
    button.setAttribute("aria-label", `Page ${page}`);
    if (page === currentPage) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => { state.page = page; loadInbox(); });
    li.appendChild(button);
    pagination.appendChild(li);
    previous = page;
  });
}
async function loadInbox() {
  const number = ++requestNumber;
  const loading = document.getElementById("inboxLoading");
  loading.classList.remove("d-none");
  document.getElementById("inboxList").setAttribute("aria-busy", "true");
  const params = new URLSearchParams({page: state.page, per_page: state.perPage, sort: state.sort});
  if (state.isRead) params.set("is_read", state.isRead);
  if (state.spamLabel) params.set("spam_label", state.spamLabel);
  if (state.needsFollowUp) params.set("needs_follow_up", state.needsFollowUp);
  if (state.priority) params.set("priority", state.priority);
  if (state.search) params.set("q", state.search);
  try {
    const response = await apiFetch(`/emails?${params}`);
    if (!response || number !== requestNumber) return;
    if (!response.ok) throw new Error("Inbox unavailable");
    const data = await response.json();
    if (number !== requestNumber) return;
    renderEmails(data.emails);
    renderPagination(data.total_pages, data.page);
    document.getElementById("inboxCount").textContent = `${data.total} message${data.total === 1 ? "" : "s"}${state.search ? " matching your search" : " in this view"}`;
  } catch (_) {
    if (number === requestNumber) {
      document.getElementById("inboxEmpty").classList.add("d-none");
      document.getElementById("inboxList").innerHTML = '<div class="alert alert-danger" role="alert">Could not load your inbox. Refresh to try again.</div>';
    }
  } finally {
    if (number === requestNumber) {
      loading.classList.add("d-none");
      document.getElementById("inboxList").removeAttribute("aria-busy");
    }
  }
}
document.addEventListener("DOMContentLoaded", () => {
  [["spamFilter", "spamLabel"], ["readFilter", "isRead"], ["followUpFilter", "needsFollowUp"], ["priorityFilter", "priority"], ["sortFilter", "sort"]].forEach(([id, key]) => {
    const select = document.getElementById(id);
    select.value = state[key];
    select.addEventListener("change", () => { state[key] = select.value; state.page = 1; loadInbox(); });
  });
  let debounce;
  document.getElementById("inboxSearch").addEventListener("input", event => {
    clearTimeout(debounce);
    state.search = event.target.value;
    debounce = setTimeout(() => { state.page = 1; loadInbox(); }, 250);
  });
  window.addEventListener("message", event => {
    const frame = document.getElementById("previewFrame");
    if (event.origin === window.location.origin && event.source === frame.contentWindow && event.data?.type === "emailorbit-updated") loadInbox();
  });
  loadInbox();
});
