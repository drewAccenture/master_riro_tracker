// Start-up, the refresh loop and the actions shared by the screens. Python is asked for every number (US-11).
// A screen is redrawn only when its data changed, so a filter, an open row or a half-typed search is kept.
"use strict";

const api = () => window.pywebview.api;
let shown = { overview: "", joiner: "" };
let cache = { overview: null, joiner: null };

const actions = {
  open(joinerId, bucket = null) {
    // US-05: switching joiner (or going back) resets every filter and the open rows.
    state.view = joinerId ? "joiner" : "overview";
    state.joinerId = joinerId;
    state.showAll = false;
    resetFilters(bucket);
    shown = { overview: "", joiner: "" };
    refresh();
  },
  setAsOf(value) {
    state.asOf = value; // Assumption 7: held by the page for this session only
    shown = { overview: "", joiner: "" };
    refresh();
  },
  resetAsOf() {
    actions.setAsOf(todayIso());
  },
  async setRollOn(joinerId, value) {
    await saveRollOn(joinerId, value, refresh);
    shown.joiner = "";
  },
  setRole(role) {
    state.filter.role = role;
    shown.joiner = "";
    refresh();
  },
  redraw() {
    if (state.view === "overview" && cache.overview) renderOverview(cache.overview, actions);
  },
};

// One refresh at a time. A click during a refresh asks for one more round, and an answer for a screen she has
// already left is dropped (the page never draws joiner X after she went back to the overview).
let refreshing = false;
let again = false;

async function refresh() {
  if (refreshing) {
    again = true;
    return;
  }
  refreshing = true;
  try {
    do {
      again = false;
      await refreshOnce();
    } while (again);
  } catch (e) {
    notice("The tracker could not load its data. Click Copy diagnostic report and send it to the maintainer.");
  } finally {
    refreshing = false;
  }
}

async function refreshOnce() {
  const key = () => `${state.view}|${state.joinerId}|${state.asOf}|${state.filter.role}`;
  const asked = key();
  const stale = () => key() !== asked;
  const sync = await api().last_result();
  renderSync(sync);
  const overview = await api().overview(state.asOf);
  if (stale()) return;
  if (overview.error) {
    notice(overview.error);
    return;
  }
  renderNav(overview.sidebar, actions.open);
  renderWaiting(overview.sidebar.waiting, refresh);
  if (state.view === "joiner") {
    // Decision B: the counts on the joiner page follow the role filter; Python counts them.
    const joiner = await api().joiner(state.joinerId, state.asOf, state.filter.role);
    if (stale()) return;
    // US-10: a joiner the last sync hid (or one no longer known) sends the page back to the overview.
    if (!joiner.found || joiner.hidden) {
      actions.open(null);
      return;
    }
    const text = JSON.stringify(joiner);
    if (text !== shown.joiner) {
      shown.joiner = text;
      cache.joiner = joiner;
      renderJoiner(joiner, actions);
    }
    return;
  }
  const text = JSON.stringify(overview);
  if (text !== shown.overview) {
    shown.overview = text;
    cache.overview = overview;
    renderOverview(overview, actions);
  }
}

async function run(call, button) {
  state.busy = true;
  notice("");
  $(button).textContent = button === "sync" ? "Syncing..." : "Waiting for sign-in...";
  $("sync").disabled = true;
  $("connect").disabled = true;
  try {
    const result = await call();
    // Connect can fail without changing the last result (US-01), so its own message is shown as a notice.
    if (button === "connect" && result.state !== "ok" && result.state !== "not_connected") notice(result.message);
  } finally {
    state.busy = false;
    $("connect").textContent = "Connect to SharePoint";
    await refresh();
  }
}

async function copyReport() {
  const { text } = await api().copy_report();
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    const buffer = $("report-buffer");
    buffer.value = text;
    buffer.select();
    document.execCommand("copy");
  }
  $("copied").hidden = false;
  setTimeout(() => {
    $("copied").hidden = true;
  }, 3000);
}

window.addEventListener("pywebviewready", () => {
  $("connect").addEventListener("click", () => run(() => api().connect(), "connect"));
  $("sync").addEventListener("click", () => run(() => api().sync_now(), "sync"));
  $("copy").addEventListener("click", copyReport);
  refresh();
  setInterval(() => {
    if (!state.busy) refresh();
  }, 2000);
});
