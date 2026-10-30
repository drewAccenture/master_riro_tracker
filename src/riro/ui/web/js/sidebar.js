// Sidebar: "All joiners", the "New joiners" list, the waiting list and the sync box (US-03, US-07, US-11).
"use strict";

function pill(count) {
  return el("span", {
    class: count > 0 ? "pill bad" : "pill ok",
    text: count,
    attrs: { title: `${count} delayed` },
  });
}

function renderNav(sidebar, open) {
  const nav = $("nav");
  nav.replaceChildren(
    el(
      "button",
      {
        class: "nav-item",
        attrs: { type: "button", "aria-current": String(state.view === "overview") },
        on: { click: () => open(null) },
      },
      [el("span", { class: "nm", text: "All joiners" }), pill(sidebar.delayed_total)],
    ),
    el("div", { class: "nav-label", text: "New joiners" }),
  );
  for (const joiner of sidebar.joiners) {
    nav.append(
      el(
        "button",
        {
          class: "nav-item",
          attrs: { type: "button", "aria-current": String(state.view === "joiner" && state.joinerId === joiner.id) },
          on: { click: () => open(joiner.id) },
        },
        [el("span", { class: "nm", text: joiner.name }, [el("small", { text: joiner.line })]), pill(joiner.delayed_count)],
      ),
    );
  }
}

let shownWaiting = "";

// US-03: the roll-on date is typed once. Redrawn only when the list changes, so a date being typed is kept.
function renderWaiting(waiting, afterSave) {
  const text = JSON.stringify(waiting);
  if (text === shownWaiting) return;
  shownWaiting = text;
  $("waiting-box").hidden = waiting.length === 0;
  const box = $("waiting");
  box.replaceChildren();
  for (const joiner of waiting) {
    const input = el("input", { attrs: { type: "date", "aria-label": `Roll-on date for ${joiner.name}` } });
    const confirm = el("button", {
      class: "btn small",
      text: "Confirm",
      attrs: { type: "button" },
      on: { click: () => saveRollOn(joiner.id, input.value, afterSave) },
    });
    box.append(
      el("div", { class: "wait-item" }, [el("span", { text: joiner.name }), el("div", { class: "row" }, [input, confirm])]),
    );
  }
}

async function saveRollOn(joinerId, value, afterSave) {
  try {
    const answer = await window.pywebview.api.set_roll_on(joinerId, value);
    notice(answer.ok ? "" : answer.message);
  } catch (e) {
    notice("The roll-on date could not be saved. Click Confirm again.");
  }
  shownWaiting = "";
  await afterSave();
}

function list(id, texts) {
  $(id).replaceChildren(...texts.map((text) => el("li", { text })));
}

function notice(text) {
  $("notice").textContent = text || "";
  $("notice").hidden = !text;
}

function renderSync(sync) {
  $("connection").textContent = sync.connected ? "SharePoint: Connected" : "SharePoint: Not connected";
  $("connection").classList.toggle("ok", sync.connected);
  const message = sync.running ? "Syncing..." : sync.message;
  // Before the first sync the message repeats the title ("SharePoint: Not connected"); show it once.
  $("message").textContent = message === $("connection").textContent ? "" : message;
  $("last-success").textContent = sync.last_success;
  list("skipped", sync.running ? [] : (sync.skipped || []).map((f) => `${f.name}: ${f.reason}`));
  list("warnings", sync.warnings || []);
  $("data-note").textContent = sync.data_note || "";
  $("sync").textContent = sync.running ? "Syncing..." : "Sync now";
  $("sync").disabled = sync.running || state.busy;
  // Connected: nothing to click. An expired sign-in makes connected false, so the button comes back (US-07).
  $("connect").disabled = sync.running || state.busy || sync.connected;
  if (!state.busy) {
    $("connect").textContent = sync.connected ? "Connected" : sync.sign_in_expired ? "Sign in again" : "Connect to SharePoint";
  }
}
