// "All joiners": KPI tiles, the heatmap and "Needs attention" (US-11). Numbers and text come from overview(as_of).
"use strict";

const ATTENTION_LIMIT = 8;

function kpi(value, label, css) {
  return el("div", { class: `kpi ${css}` }, [el("span", { class: "v", text: value }), el("span", { class: "l", text: label })]);
}

function overviewHead(data, actions) {
  const asOf = dateChip("Status as of", data.as_of_text, state.asOf, actions.setAsOf);
  return el("div", { class: "page-head" }, [
    el("div", {}, [
      el("h2", { text: "All joiners" }),
      el("div", { class: "sub", text: `Open tasks by how close they are to their deadline, as of ${data.as_of_text}` }),
    ]),
    el("div", { class: "head-right" }, [
      asOf.chip,
      actionsMenu([{ label: "Reset status date to today", run: actions.resetAsOf }]),
    ]),
  ]);
}

function heatmap(data, actions) {
  const head = el("tr", {}, [el("th", { text: "Joiner" })]);
  for (const column of data.columns) {
    head.append(el("th", { class: "c" }, [document.createTextNode(column.label), el("span", { class: "thd", text: column.dates })]));
  }
  head.append(el("th", { class: "c", text: "Done" }));
  const body = el("tbody");
  for (const row of data.rows) {
    const tr = el("tr", {}, [
      el("td", {}, [
        el("button", { class: "jname", text: row.name, attrs: { type: "button" }, on: { click: () => actions.open(row.id) } }),
        el("span", { class: "jsub", text: `Roll-on ${row.roll_on_text} · ${row.since_text}` }),
      ]),
    ]);
    for (const cell of row.cells) {
      const label = data.columns.find((c) => c.key === cell.bucket).label;
      const button = el("button", {
        class: `hc ${cell.css}`,
        text: cell.count,
        attrs: {
          type: "button",
          tabindex: cell.count ? null : "-1",
          "aria-label": `${cell.count} ${label} tasks for ${row.name}`,
        },
      });
      if (cell.count) button.addEventListener("click", () => actions.open(row.id, cell.bucket));
      tr.append(el("td", { class: "c" }, [button]));
    }
    tr.append(el("td", { class: "c pct", text: `${row.percent}%` }));
    body.append(tr);
  }
  const legend = el("div", { class: "legend" }, [
    el("span", {}, [el("i", { class: "sq s-Delayed" }), document.createTextNode("Past deadline")]),
    el("span", {}, [el("i", { class: "sq s-CompletedLate" }), document.createTextNode("Due within 3 days")]),
    el("span", {}, [el("i", { class: "sq s-OnTrack" }), document.createTextNode("Due later")]),
  ]);
  return el("section", { class: "card" }, [
    el("div", { class: "card-head" }, [
      el("h3", { text: "Open tasks by joiner and deadline" }),
      el("span", { class: "asofchip", text: `As of ${data.as_of_text}` }),
    ]),
    el("p", { class: "hint", text: "Select a joiner to open the checklist, or a number to see just those tasks." }),
    el("div", { class: "tablewrap" }, [el("table", { class: "heat" }, [el("thead", {}, [head]), body])]),
    legend,
  ]);
}

function attention(data, actions) {
  const card = el("section", { class: "card" }, [
    el("h3", { text: "Needs attention" }),
    el("p", { class: "hint", text: "Overdue first, then due today." }),
  ]);
  if (!data.attention.length) {
    card.append(el("p", { class: "hint", text: "Nothing is overdue or due today." }));
    return card;
  }
  const items = state.showAll ? data.attention : data.attention.slice(0, ATTENTION_LIMIT);
  for (const item of items) {
    card.append(
      el("button", { class: "att", attrs: { type: "button" }, on: { click: () => actions.open(item.joiner_id) } }, [
        el("span", {}, [el("b", { text: item.title }), el("small", { text: item.who })]),
        el("span", { class: `badge b-${item.badge_css}`, text: item.badge }),
      ]),
    );
  }
  if (data.attention.length > ATTENTION_LIMIT) {
    card.append(
      el("button", {
        class: "btn small",
        text: state.showAll ? "Show fewer" : `Show all ${data.attention.length}`,
        attrs: { type: "button" },
        on: {
          click: () => {
            state.showAll = !state.showAll;
            actions.redraw();
          },
        },
      }),
    );
  }
  return card;
}

function renderOverview(data, actions) {
  const main = $("main");
  const parts = [overviewHead(data, actions)];
  if (!data.rows.length) {
    const waiting = data.sidebar.waiting.length;
    parts.push(
      emptyCard(
        waiting
          ? "Type the roll-on date of the joiners waiting in the sidebar to see their progress here."
          : "No joiners yet. Joiners appear here after a sync.",
      ),
    );
    main.replaceChildren(...parts);
    return;
  }
  const k = data.kpis;
  parts.push(
    el("div", { class: "kpis" }, [
      kpi(k.joiners, "Joiners", ""),
      kpi(k.delayed, "Delayed tasks", k.delayed > 0 ? "k-bad" : ""),
      kpi(k.due_soon, "Due within 3 days", k.due_soon > 0 ? "k-warn" : ""),
      kpi(k.average, "Average completed", ""),
    ]),
    el("div", { class: "ov-grid" }, [heatmap(data, actions), attention(data, actions)]),
  );
  main.replaceChildren(...parts);
}
