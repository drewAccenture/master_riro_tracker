// Joiner page: banner, tiles, deadline ladder, filters and the task table (US-05, US-11). Data from joiner(id, as_of).
// Filters only hide rows by fields Python sent; no status is computed here (US-04).
"use strict";

const BUCKET_LABELS = { overdue: "Overdue", today: "Today", soon: "1-3 days", week: "4-7 days", later: "Later" };

function joinerHead(data, actions) {
  const rollOn = dateChip("Onboarding date", data.roll_on_text, data.roll_on, (value) => actions.setRollOn(data.id, value));
  const asOf = dateChip("Status as of", data.as_of_text, state.asOf, actions.setAsOf);
  const menu = actionsMenu([
    { label: "Reset status date to today", run: actions.resetAsOf },
    { label: "Change roll-on date", run: () => (rollOn.input.showPicker ? rollOn.input.showPicker() : rollOn.input.focus()) },
  ]);
  return [
    el("div", { class: "backbar" }, [
      el("button", { class: "backlink", text: "← Back to all joiners", attrs: { type: "button" }, on: { click: () => actions.open(null) } }),
    ]),
    el("div", { class: "page-head" }, [
      el("div", {}, [el("h2", { text: data.name }), el("div", { class: "sub", text: "Deadlines count from the onboarding date" })]),
      el("div", { class: "head-right" }, [rollOn.chip, asOf.chip, menu]),
    ]),
  ];
}

function bannerBox(data) {
  const meter = el("span", { class: "meter" });
  for (const part of data.meter) {
    const css = part.track.replace(/[^A-Za-z]/g, "");
    const bar = el("i", { class: `m-${css}`, attrs: { title: `${part.track}: ${part.count}` } });
    bar.style.width = `${part.percent}%`;
    meter.append(bar);
  }
  return el("div", { class: `banner ${data.banner.kind}` }, [
    el("span", {}, [el("b", { text: data.banner.title }), document.createTextNode(` ${data.banner.text}`)]),
    meter,
  ]);
}

function tiles(data, redraw) {
  const box = el("div", { class: "tiles" });
  for (const tile of data.tiles) {
    const css = tile.track.replace(/[^A-Za-z]/g, "");
    box.append(
      el(
        "button",
        {
          class: `tile t-${css}`,
          attrs: { type: "button", "aria-pressed": String(state.filter.track === tile.track) },
          on: {
            click: () => {
              // US-05: a tile filters to that track; clicking it again clears the filter.
              state.filter.track = state.filter.track === tile.track ? null : tile.track;
              redraw();
            },
          },
        },
        [el("span", { class: "v", text: tile.count }), el("span", { class: "l", text: tile.label })],
      ),
    );
  }
  return box;
}

function ladderCard(data, redraw) {
  const row = el("div", { class: "ladder" });
  const marker = el("div", { class: "asof", attrs: { "aria-hidden": "true" } }, [el("span", { text: data.ladder.marker_label }), el("i")]);
  data.ladder.columns.forEach((column, index) => {
    if (index === data.ladder.marker_before) row.append(marker);
    const stack = el("span", { class: "stack" });
    for (const square of column.squares) {
      const title = `${data.task_rows[square.index].title} — ${square.track}`;
      stack.append(el("i", { class: `sq s-${square.css}`, attrs: { title } }));
    }
    row.append(
      el(
        "button",
        {
          class: "col",
          attrs: { type: "button", title: column.title, "aria-pressed": String(state.filter.ladder === column.key) },
          on: {
            click: () => {
              state.filter.ladder = state.filter.ladder === column.key ? null : column.key;
              redraw();
            },
          },
        },
        [stack, el("span", { class: "d", text: column.label }), el("span", { class: "dt", text: column.date })],
      ),
    );
  });
  // marker_before is a column index from Python; past the last column the line goes at the end.
  if (data.ladder.marker_before >= data.ladder.columns.length) row.append(marker);
  const legend = el("div", { class: "legend" });
  for (const [css, label] of [["Delayed", "Delayed"], ["OnTrack", "On Track"], ["Completed", "Completed"], ["CompletedLate", "Completed Late"], ["NA", "Not applicable"], ["Deadlineunclear", "Deadline unclear"]]) {
    legend.append(el("span", {}, [el("i", { class: `sq s-${css}` }), document.createTextNode(label)]));
  }
  return el("section", { class: "card" }, [
    el("h3", { text: "Deadline ladder" }),
    el("p", {
      class: "hint",
      text: "Each square is a task, grouped by the day it is due. Select a column to list only those tasks. The dashed line is the as-of date.",
    }),
    row,
    legend,
  ]);
}

function matches(data, index) {
  const task = data.tasks[index];
  const row = data.task_rows[index];
  const f = state.filter;
  if (f.track && task.track !== f.track) return false;
  if (f.ladder && row.ladder_key !== f.ladder) return false;
  if (f.bucket && row.bucket !== f.bucket) return false;
  if (f.role && task.role !== f.role) return false;
  if (f.q) {
    const text = `${row.title} ${row.who} ${task.role} ${task.deadline} ${row.full}`.toLowerCase();
    if (!text.includes(f.q.toLowerCase())) return false;
  }
  return true;
}

function taskRows(data, body) {
  body.replaceChildren();
  let shown = 0;
  data.tasks.forEach((task, index) => {
    if (!matches(data, index)) return;
    shown += 1;
    const row = data.task_rows[index];
    const css = task.track ? task.track.replace(/[^A-Za-z]/g, "") : "";
    const open = state.open.has(index);
    const title = el("button", {
      class: "tt",
      text: row.title,
      attrs: { type: "button", "aria-expanded": String(open) },
      on: {
        click: () => {
          if (state.open.has(index)) state.open.delete(index);
          else state.open.add(index);
          taskRows(data, body);
        },
      },
    });
    body.append(
      el("tr", { class: "row" }, [
        el("td", { class: "num", text: task.number }),
        el("td", {}, [title]),
        el("td", { class: "owner" }, [el("b", { text: row.who }), el("span", { text: task.role })]),
        el("td", { class: "rule" }, [document.createTextNode(task.deadline), el("span", { text: row.due_text })]),
        el("td", { text: task.status }),
        el("td", { text: row.completion_text }),
        el("td", {}, [task.track ? el("span", { class: `badge b-${css}`, text: task.track }) : null]),
        el("td", { class: `days ${row.days_css}`, text: row.days_text }),
        el("td", { text: row.remarks }),
      ]),
    );
    if (open) {
      const detail = el("td", { attrs: { colspan: "9" } }, [el("h4", { text: "Full task" }), el("pre", { text: row.full })]);
      if (row.guidelines) detail.append(el("h4", { text: "Guidelines" }), el("pre", { text: row.guidelines }));
      body.append(el("tr", { class: "detail" }, [detail]));
    }
  });
  if (!shown) body.append(el("tr", {}, [el("td", { class: "empty", text: "No tasks match these filters.", attrs: { colspan: "9" } })]));
}

function activeChips(data) {
  const f = state.filter;
  const chips = [];
  if (f.track) chips.push(f.track);
  if (f.ladder && data.ladder) {
    const column = data.ladder.columns.find((c) => c.key === f.ladder);
    if (column) chips.push(column.key === "unclear" ? column.label : `Due ${column.label}`);
  }
  if (f.bucket) chips.push(`Open, ${BUCKET_LABELS[f.bucket]}`);
  return chips;
}

function toolbar(data, body, redraw, actions) {
  const search = el("input", { attrs: { type: "search", placeholder: "Search tasks, owners, deadlines", "aria-label": "Search tasks" } });
  search.value = state.filter.q;
  search.addEventListener("input", () => {
    state.filter.q = search.value;
    taskRows(data, body); // only the rows: the search box keeps its focus and cursor
  });
  const role = el("select", { attrs: { "aria-label": "Role" } }, [el("option", { text: "All roles", attrs: { value: "" } })]);
  for (const name of data.roles) role.append(el("option", { text: name, attrs: { value: name } }));
  role.value = state.filter.role;
  role.addEventListener("change", () => actions.setRole(role.value));
  const bar = el("div", { class: "toolbar" }, [search, role]);
  const chips = activeChips(data);
  if (chips.length || state.filter.role || state.filter.q) {
    bar.append(
      el("div", { class: "chips" }, chips.map((text) => el("span", { class: "chip", text }))),
      el("button", {
        class: "btn small",
        text: "Clear filters",
        attrs: { type: "button" },
        on: {
          click: () => {
            resetFilters();
            actions.setRole(""); // the counts follow the role, so Python is asked again
          },
        },
      }),
    );
  }
  return bar;
}

function renderJoiner(data, actions) {
  const redraw = () => renderJoiner(data, actions);
  const parts = joinerHead(data, actions);
  // US-13: a SharePoint file of the same owner replaces this import on the next sync.
  if (data.imported) parts.push(el("p", { class: "note imported", text: "Imported from this PC" }));
  if (data.problem_text) parts.push(el("p", { class: "note problem", text: data.problem_text }));
  if (data.skipped_text) parts.push(el("p", { class: "note", text: data.skipped_text }));
  if (data.role_note) parts.push(el("p", { class: "note role", text: data.role_note }));
  if (data.banner) parts.push(bannerBox(data), tiles(data, redraw), ladderCard(data, redraw));
  else parts.push(el("p", { class: "note problem", text: "Set the onboarding date to see deadlines and statuses." }));
  for (const warning of data.warnings) parts.push(el("p", { class: "note", text: warning }));
  const body = el("tbody");
  const head = el("tr", {}, ["#", "Task", "Owner", "Deadline", "Completion status", "Completed on", "Tracking", "Days to due", "Remarks"].map((text) => el("th", { text })));
  parts.push(toolbar(data, body, redraw, actions), el("div", { class: "tablewrap" }, [el("table", { class: "tasks" }, [el("thead", {}, [head]), body])]));
  taskRows(data, body);
  $("main").replaceChildren(...parts);
}
