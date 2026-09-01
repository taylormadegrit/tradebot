const $ = (id) => document.getElementById(id);
const fmt = (v) => (v === null || v === undefined ? "—" : v);

// event timestamps shown in both US Eastern (EST/EDT) and US Pacific (PST/PDT)
const _tf = (tz) =>
  new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hour12: false,
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    timeZoneName: "short",
  });
const etFmt = _tf("America/New_York");
const ptFmt = _tf("America/Los_Angeles");
const etpt = (ms) => `${etFmt.format(ms)} / ${ptFmt.format(ms)}`;

async function act(route) {
  try {
    const r = await fetch(`/api/${route}`, { method: "POST" });
    const j = await r.json();
    console.log(route, j);
  } catch (e) {
    $("err").textContent = String(e);
  }
}

function fillTable(tbodySel, rows) {
  const tb = document.querySelector(tbodySel);
  tb.innerHTML = "";
  for (const cells of rows) {
    const tr = document.createElement("tr");
    for (const c of cells) {
      const td = document.createElement("td");
      if (c && typeof c === "object") {
        td.textContent = c.text;
        if (c.cls) td.className = c.cls;
      } else {
        td.textContent = c;
      }
      tr.appendChild(td);
    }
    tb.appendChild(tr);
  }
}

async function tick() {
  try {
    const r = await fetch("/api/state");
    const s = await r.json();
    if (s.error) {
      $("err").textContent = s.error;
      return;
    }
    $("err").textContent = s.instruments && s.instruments._error ? s.instruments._error : "";

    $("mode").textContent = s.mode ? `[${s.mode}]` : "";
    $("clock").textContent = s.now
      ? `${s.now.et}  |  ${s.now.pt}  |  ${s.now.utc}`
      : etpt(Date.now());
    $("balance").textContent = fmt(s.account && s.account.balance);
    $("equity").textContent = fmt(s.account && s.account.equity);
    const acc = s.account || {};
    const st = s.trade_stats || {};
    $("realized").textContent =
      acc.realized === undefined || acc.realized === null
        ? "—"
        : `${acc.realized >= 0 ? "+" : ""}${acc.realized}`;
    $("record").textContent = st.n
      ? `${st.n} tr · ${st.win_rate_pct}% · PF ${st.profit_factor ?? "∞"}`
      : `${acc.open_trades ?? 0} open · 0 closed`;
    if (s.halted_reason) {
      $("status").textContent = "HALTED";
      $("status").className = "big halt";
      $("status").title = s.halted_reason;
    } else {
      $("status").textContent = s.running ? "running" : "idle";
      $("status").className = "big";
    }

    fillTable(
      "#reads tbody",
      Object.entries(s.instruments || {})
        .filter(([k]) => !k.startsWith("_"))
        .map(([sym, v]) => [
          sym,
          [v.read || "—", ...(v.patterns || []).map((p) => "• " + p)].join("\n"),
        ])
    );

    fillTable(
      "#wl tbody",
      Object.entries(s.watchlist || {}).map(([sym, v]) => [
        sym,
        fmt(v.price),
        fmt(v.prior_high),
        v.to_high_pct === null || v.to_high_pct === undefined
          ? "—"
          : `${v.to_high_pct > 0 ? "+" : ""}${v.to_high_pct}%`,
        {
          text: v.error ? "error" : v.status || "—",
          cls: v.new_high ? "buy" : "",
        },
      ])
    );

    const ageStr = (epoch) => {
      if (!epoch) return "—";
      const m = Math.round((Date.now() / 1000 - epoch) / 60);
      if (m < 60) return `${m}m`;
      if (m < 1440) return `${Math.round(m / 60)}h`;
      return `${Math.round(m / 1440)}d`;
    };
    fillTable(
      "#news tbody",
      Object.entries(s.news || {}).map(([sym, v]) => [
        sym,
        v.error ? `error: ${v.error}` : v.latest || "—",
        ageStr(v.latest_epoch),
        {
          text: v.error ? "" : String(v.count_new ?? 0),
          cls: v.count_new ? "buy" : "",
        },
      ])
    );

    const cal = s.calendar || {};
    $("cal-window").textContent = cal.window
      ? `(no new entries ${cal.window} around high-impact releases)`
      : "(no new entries near high-impact releases)";
    const blackouts = Object.entries(cal.blackout || {})
      .filter(([, v]) => v)
      .map(([k, v]) => `${k} — ${v}`);
    $("cal-warn").textContent =
      cal.ok === false
        ? "calendar data missing or stale — blackout filter is NOT active"
        : blackouts.join("     |     ");
    fillTable(
      "#cal tbody",
      (cal.next || []).map((e) => {
        const cls = e.blackout ? "" : "none"; // out-of-scope events shown muted
        return [
          { text: etpt(e.epoch * 1000), cls },
          {
            text: e.in_minutes < 0 ? `${-e.in_minutes}m ago` : `${e.in_minutes}m`,
            cls,
          },
          { text: e.country, cls },
          { text: e.impact, cls },
          { text: e.blackout ? e.title : `${e.title}  (not in scope)`, cls },
        ];
      })
    );

    fillTable(
      "#inst tbody",
      Object.entries(s.instruments || {})
        .filter(([k]) => !k.startsWith("_"))
        .map(([sym, v]) => [
          sym,
          fmt(v.bid),
          fmt(v.ask),
          { text: v.signal, cls: v.signal },
          v.blocked ? `blocked: ${v.blocked}` : v.reason || "",
        ])
    );

    fillTable(
      "#pos tbody",
      (s.positions || []).map((p) => [
        fmt(p.symbol),
        { text: fmt(p.side), cls: p.side },
        fmt(p.lots),
        fmt(p.entry),
        { text: fmt(p.pnl), cls: p.pnl >= 0 ? "buy" : "sell" },
      ])
    );

    fillTable(
      "#trades tbody",
      (s.trades || []).map((t) => [
        etpt(t.ts * 1000),
        t.symbol,
        { text: t.side, cls: t.side },
        fmt(t.lots),
        fmt(t.entry),
        fmt(t.exit),
        t.reason,
        { text: `${t.pnl >= 0 ? "+" : ""}${t.pnl}`, cls: t.pnl >= 0 ? "buy" : "sell" },
      ])
    );

    fillTable(
      "#ev tbody",
      (s.events || []).map((e) => [
        etpt(e.ts * 1000),
        e.kind,
        e.symbol || "",
        e.detail ? JSON.stringify(e.detail) : "",
      ])
    );
  } catch (e) {
    $("err").textContent = String(e);
  }
}

tick();
setInterval(tick, 2000);
