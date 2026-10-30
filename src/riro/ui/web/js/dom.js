// Small DOM helpers and the page state. No rules here: every number and text comes from Python (US-11).
// Data is always placed with textContent, never innerHTML, so names and task text are never read as HTML.
"use strict";

const $ = (id) => document.getElementById(id);

// el("button", {class: "btn", text: "Sync now", attrs: {type: "button"}, on: {click: fn}}, [children])
function el(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.class) node.className = options.class;
  if (options.text !== undefined && options.text !== null) node.textContent = String(options.text);
  for (const [name, value] of Object.entries(options.attrs || {})) {
    if (value !== undefined && value !== null && value !== false) node.setAttribute(name, String(value));
  }
  for (const [name, handler] of Object.entries(options.on || {})) node.addEventListener(name, handler);
  for (const child of children) if (child) node.append(child);
  return node;
}

function todayIso() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

// UI state only (workflows US-05, Assumption 7): what is selected and filtered, never a computed status.
const state = {
  view: "overview", // "overview" or "joiner"
  joinerId: null,
  asOf: todayIso(),
  filter: { track: null, ladder: null, bucket: null, role: "", q: "" },
  open: new Set(), // expanded task rows (task index)
  showAll: false, // "Needs attention": all items, not only 8
  busy: false,
};

function resetFilters(bucket = null) {
  state.filter = { track: null, ladder: null, bucket, role: "", q: "" };
  state.open = new Set();
}

function dateChip(label, value, iso, onChange) {
  const input = el("input", { attrs: { type: "date", value: iso || "", "aria-label": label } });
  // A date box fires "change" on every key while she types a year, so a value is used only on Enter, when the box
  // loses focus, or after a pause; Python also refuses years outside 2000-2099 (US-03: a date is typed once).
  let last = iso || "";
  let timer = null;
  const commit = () => {
    clearTimeout(timer);
    if (input.value && input.value !== last) {
      last = input.value;
      onChange(input.value);
    }
  };
  input.addEventListener("change", () => {
    clearTimeout(timer);
    timer = setTimeout(commit, 1200);
  });
  input.addEventListener("blur", commit);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") commit();
  });
  input.addEventListener("click", () => {
    if (input.showPicker) input.showPicker();
  });
  const chip = el("label", { class: "datechip", attrs: { title: "Click to change" } }, [
    el("span", { class: "dc-l", text: label }),
    el("span", { class: "dc-v", text: value || "Not set" }),
    input,
  ]);
  return { chip, input };
}

function actionsMenu(items) {
  const menu = el("div", { class: "menu", attrs: { role: "menu", hidden: true } });
  const button = el("button", {
    class: "iconbtn",
    text: "⋯",
    attrs: { type: "button", "aria-label": "Actions", title: "Actions", "aria-haspopup": "menu", "aria-expanded": "false" },
  });
  const close = () => {
    menu.hidden = true;
    button.setAttribute("aria-expanded", "false");
  };
  for (const item of items) {
    menu.append(
      el("button", {
        class: "mi",
        text: item.label,
        attrs: { type: "button", role: "menuitem" },
        on: {
          click: () => {
            close();
            item.run();
          },
        },
      }),
    );
  }
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const opening = menu.hidden;
    menu.hidden = !opening;
    button.setAttribute("aria-expanded", String(opening));
    if (opening && menu.firstChild) menu.firstChild.focus();
  });
  return el("div", { class: "menuwrap" }, [button, menu]);
}

// One listener for the whole page (not one per menu, so redraws never pile listeners up).
function closeMenus(except) {
  for (const wrap of document.querySelectorAll(".menuwrap")) {
    if (wrap.contains(except)) continue;
    wrap.querySelector(".menu").hidden = true;
    wrap.querySelector(".iconbtn").setAttribute("aria-expanded", "false");
  }
}
document.addEventListener("click", (event) => closeMenus(event.target));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeMenus(null);
});

function emptyCard(text) {
  return el("section", { class: "card empty", text });
}
