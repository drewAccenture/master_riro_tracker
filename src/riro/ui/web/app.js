// Test page for slices 1 to 4. Shows what Python returns; no rules here (statuses come from Python).
"use strict";

const $ = (id) => document.getElementById(id);
let busy = false;

function show(state) {
  $("connection").textContent = state.connected ? "SharePoint: Connected" : "SharePoint: Not connected";
  $("connection").classList.toggle("is-connected", state.connected);
  $("folder").textContent = state.folder;
  $("message").textContent = state.running ? "Syncing..." : state.message;
  $("last-success").textContent = state.last_success;
  // ADR-004: tell her when the data was restored from the backup or started empty.
  if (state.data_note !== undefined) $("data-note").textContent = state.data_note || "";
  const details = [];
  if (state.files_listed) details.push(`${state.files_listed} files listed`);
  if (state.report) {
    details.push(`first file read: ${state.report.row_count} rows`);
    details.push(`headers found: ${state.report.headers_found.join(", ") || "none"}`);
    details.push(`headers missing: ${state.report.headers_missing.join(", ") || "none"}`);
  }
  $("details").textContent = details.join(" · ");
  // US-07: each skipped file with its reason. textContent only, so a file name is never read as HTML.
  const skipped = $("skipped");
  skipped.replaceChildren();
  for (const file of state.running ? [] : state.skipped || []) {
    const item = document.createElement("li");
    item.textContent = `${file.name}: ${file.reason}`;
    skipped.append(item);
  }
  $("sync").textContent = state.running ? "Syncing..." : "Sync now";
  $("sync").disabled = state.running || busy;
  // Connected: nothing to click. A later failed sign-in makes connected false, so the button comes back by itself.
  $("connect").disabled = state.running || busy || state.connected;
  // US-07: the expired-sign-in message says "Click Sign in again", so the button says it too.
  if (!busy) {
    $("connect").textContent = state.connected
      ? "Connected"
      : state.sign_in_expired ? "Sign in again" : "Connect to SharePoint";
  }
}

function list(id, texts) {
  // textContent only, so names and file names are never read as HTML.
  const box = $(id);
  box.replaceChildren();
  for (const text of texts) {
    const item = document.createElement("li");
    item.textContent = text;
    box.append(item);
  }
}

function today() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

let shownJoiners = "";

function showJoiners(result) {
  const text = JSON.stringify(result);
  if (text === shownJoiners) return; // keep a date she is typing
  shownJoiners = text;
  const joiners = result.joiners || [];
  const waiting = $("waiting");
  waiting.replaceChildren();
  for (const joiner of joiners.filter((j) => j.waiting)) {
    const item = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = `${joiner.name} `;
    const input = document.createElement("input");
    input.type = "date";
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Confirm";
    button.addEventListener("click", async () => {
      // US-03: typed once; Python checks the date and saves it.
      try {
        const answer = await window.pywebview.api.set_roll_on(joiner.id, input.value);
        notice(answer.ok ? "" : answer.message);
      } catch (e) {
        notice("The roll-on date could not be saved. Click Confirm again.");
      }
      shownJoiners = "";
      await refreshJoiners();
    });
    item.append(name, input, button);
    waiting.append(item);
  }
  list(
    "joiners",
    joiners
      .filter((j) => !j.waiting)
      .map((j) => `${j.name} · Roll-on ${j.roll_on} · ${j.percent}% done · ${j.delayed_count} delayed`),
  );
}

async function refreshJoiners() {
  showJoiners(await window.pywebview.api.joiners(today()));
}

function notice(text) {
  $("notice").textContent = text || "";
  $("notice").hidden = !text;
}

async function refresh() {
  const state = await window.pywebview.api.last_result();
  show(state);
  list("warnings", state.warnings || []);
  await refreshJoiners();
}

async function run(call, button) {
  busy = true;
  notice("");
  $(button).textContent = button === "sync" ? "Syncing..." : "Waiting for sign-in...";
  $("sync").disabled = true;
  $("connect").disabled = true;
  try {
    const result = await call();
    // Connect can fail without changing the last result (US-01), so its own message is shown as a notice.
    if (button === "connect" && result.state !== "ok" && result.state !== "not_connected") notice(result.message);
  } finally {
    busy = false;
    $("connect").textContent = "Connect to SharePoint";
    await refresh();
  }
}

async function copyReport() {
  const { text } = await window.pywebview.api.copy_report();
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    const buffer = $("report-buffer");
    buffer.value = text;
    buffer.select();
    document.execCommand("copy");
  }
  $("copied").hidden = false;
  setTimeout(() => { $("copied").hidden = true; }, 3000);
}

window.addEventListener("pywebviewready", () => {
  $("connect").addEventListener("click", () => run(() => window.pywebview.api.connect(), "connect"));
  $("sync").addEventListener("click", () => run(() => window.pywebview.api.sync_now(), "sync"));
  $("copy").addEventListener("click", copyReport);
  refresh();
  setInterval(() => { if (!busy) refresh(); }, 2000);
});
