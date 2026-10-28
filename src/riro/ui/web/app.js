// One page for slice 1. Shows what Python returns; no rules here.
"use strict";

const $ = (id) => document.getElementById(id);
let busy = false;

function show(state) {
  $("connection").textContent = state.connected ? "SharePoint: Connected" : "SharePoint: Not connected";
  $("connection").classList.toggle("is-connected", state.connected);
  $("folder").textContent = state.folder;
  $("message").textContent = state.running ? "Syncing..." : state.message;
  $("last-success").textContent = state.last_success;
  const details = [];
  if (state.files_listed) details.push(`${state.files_listed} files listed`);
  if (state.report) {
    details.push(`file 1: ${state.report.row_count} rows`);
    details.push(`headers found: ${state.report.headers_found.join(", ") || "none"}`);
    details.push(`headers missing: ${state.report.headers_missing.join(", ") || "none"}`);
  }
  $("details").textContent = details.join(" · ");
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

function notice(text) {
  $("notice").textContent = text || "";
  $("notice").hidden = !text;
}

async function refresh() {
  show(await window.pywebview.api.last_result());
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
