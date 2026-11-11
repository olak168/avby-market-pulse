/* AV.BY Market Pulse — dashboard logic (vanilla JS + ECharts). */

const API = "/api";
const STATIC_DATA = "data";
const PAGE_SIZE = 12;
const DEALS_PAGE_SIZE = 12;
const REFRESH_MS = 60_000;
const PALETTE = ["#818cf8", "#22d3ee", "#fbbf24", "#34d399", "#fb7185", "#a78bfa", "#38bdf8", "#f472b6", "#4ade80", "#facc15"];

const state = { page: 1, filters: {}, loading: false, scrapedAt: null, dealsPage: 1, mode: "api" };
const charts = {};

const nf = new Intl.NumberFormat("ru-RU");
const money = (n) => (n == null ? "—" : "$" + nf.format(Math.round(n)));
const km = (n) => (n == null ? "—" : nf.format(n) + " км");
const pct = (n) => (n == null ? "—" : n.toFixed(1).replace(".0", "") + "%");
const compact = (n) => {
  if (n == null) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return Math.round(n / 1e3) + "k";
  return String(n);
};
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (typeof u === "string" && /^https?:\/\//i.test(u) ? u : "#");

const TOOLTIP = {
  backgroundColor: "rgba(10,14,26,0.96)",
  borderColor: "rgba(129,140,248,0.3)",
  borderWidth: 1,
  padding: [9, 12],
  textStyle: { color: "#e8ecff", fontSize: 12 },
  extraCssText: "border-radius:10px;box-shadow:0 12px 30px rgba(0,0,0,.55);",
};
const AXIS_LABEL = { color: "#8b95b8", fontSize: 11 };
const AXIS_LINE = { lineStyle: { color: "rgba(129,140,248,0.16)" } };
const SPLIT_LINE = { lineStyle: { color: "rgba(129,140,248,0.08)" } };

function vGrad(from, to) {
  return new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: from },
    { offset: 1, color: to },
  ]);
}
function hGrad(from, to) {
  return new echarts.graphic.LinearGradient(0, 0, 1, 0, [
    { offset: 0, color: from },
    { offset: 1, color: to },
  ]);
}

function getChart(id) {
  if (!charts[id]) charts[id] = echarts.init(document.getElementById(id));
  return charts[id];
}
function emptyOption(message) {
  return {
    title: {
      text: message,
      left: "center",
      top: "middle",
      textStyle: { color: "#5c6688", fontSize: 13, fontWeight: 400 },
    },
  };
}
function setChart(id, option) {
  getChart(id).setOption(option, true);
}

/* ----------------------------- rendering ----------------------------- */

function renderMeta(meta) {
  const count = meta?.count ?? 0;
  document.getElementById("meta-count").textContent = nf.format(count) + " авто";
  document.getElementById("hero-count").textContent = nf.format(count);
  const date = meta?.scraped_at ? new Date(meta.scraped_at) : null;
  const dateText = date
    ? "срез " + date.toLocaleString("ru-RU", {
        day: "2-digit",
        month: "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "дата неизвестна";
  document.getElementById("meta-date").textContent = dateText;
  document.getElementById("footer-date").textContent = dateText;
  if (meta?.source) document.getElementById("footer-source").textContent = "Источник: " + meta.source;
}

function yearsWord(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "год";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "года";
  return "лет";
}

function renderInsight(data) {
  const el = document.getElementById("insight");
  const s = data.summary;
  if (!s.total) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  const body = data.charts.by_body[0];
  const loc = data.charts.by_location[0];
  const age = s.avg_year ? Math.max(0, Math.round(new Date().getFullYear() - s.avg_year)) : null;
  const parts = [
    `В выборке <strong>${nf.format(s.total)}</strong> авто, медианная цена — <strong>${money(s.median_price_usd)}</strong>${age != null ? `, средний возраст — <strong>${age} ${yearsWord(age)}</strong>` : ""}.`,
  ];
  const tail = [];
  if (loc) tail.push(`лидер по предложению — <strong>${esc(loc.name)}</strong> (${loc.share}%)`);
  if (body) tail.push(`самый частый кузов — <strong>${esc(body.name)}</strong> (${body.share}%)`);
  if (tail.length) {
    const sentence = tail.join(", ");
    parts.push(sentence.charAt(0).toUpperCase() + sentence.slice(1) + ".");
  }
  parts.push(`Электромобили занимают <strong>${pct(s.electric_share)}</strong> выборки.`);
  el.innerHTML = parts.join(" ");
}

function renderKpis(summary) {
  document.getElementById("kpi-total").textContent = nf.format(summary.total);
  document.getElementById("kpi-avg-price").textContent = money(summary.avg_price_usd);
  document.getElementById("kpi-median-price").textContent = money(summary.median_price_usd);
  document.getElementById("kpi-avg-year").textContent =
    summary.avg_year == null ? "—" : Math.round(summary.avg_year);
  document.getElementById("kpi-avg-mileage").textContent =
    summary.avg_mileage_km == null ? "—" : nf.format(Math.round(summary.avg_mileage_km));
  document.getElementById("kpi-electric").textContent = pct(summary.electric_share);
}

function renderPriceHistogram(data) {
  if (!data.labels.length) return setChart("chart-price", emptyOption("Нет данных под фильтр"));
  setChart("chart-price", {
    grid: { left: 6, right: 16, top: 26, bottom: 6, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(129,140,248,0.08)" } },
      formatter: (p) => `<b>${p[0].axisValue}</b><br/>${nf.format(p[0].value)} авто`,
    },
    xAxis: {
      type: "category",
      data: data.labels,
      axisLabel: { ...AXIS_LABEL, interval: 0, rotate: data.labels.length > 7 ? 26 : 0 },
      axisTick: { show: false },
      axisLine: AXIS_LINE,
    },
    yAxis: { type: "value", splitLine: SPLIT_LINE, axisLabel: AXIS_LABEL },
    series: [
      {
        type: "bar",
        data: data.values,
        barWidth: "62%",
        itemStyle: { borderRadius: [6, 6, 0, 0], color: vGrad("#818cf8", "rgba(34,211,238,0.25)") },
        emphasis: { itemStyle: { color: vGrad("#a5b4fc", "#22d3ee") } },
      },
    ],
  });
}

function renderSegments(data) {
  const total = data.reduce((acc, d) => acc + d.count, 0);
  if (!total) return setChart("chart-segments", emptyOption("Нет данных под фильтр"));
  setChart("chart-segments", {
    tooltip: { ...TOOLTIP, trigger: "item", formatter: (p) => `${p.name}<br/><b>${nf.format(p.value)}</b> авто (${p.percent}%)` },
    title: {
      text: nf.format(total),
      subtext: "авто",
      left: "center",
      top: "37%",
      textStyle: { color: "#fff", fontSize: 25, fontWeight: 800 },
      subtextStyle: { color: "#8b95b8", fontSize: 11 },
    },
    legend: {
      bottom: 2,
      left: "center",
      itemWidth: 9,
      itemHeight: 9,
      textStyle: { color: "#8b95b8", fontSize: 10.5 },
    },
    series: [
      {
        type: "pie",
        radius: ["50%", "74%"],
        center: ["50%", "46%"],
        itemStyle: { borderColor: "#0b1020", borderWidth: 2 },
        label: { show: false },
        emphasis: { scale: true, scaleSize: 6 },
        data: data.map((d, i) => ({ name: d.name, value: d.count, itemStyle: { color: PALETTE[i % PALETTE.length] } })),
      },
    ],
  });
}

function renderBrands(data) {
  if (!data.length) return setChart("chart-brands", emptyOption("Нет данных под фильтр"));
  const rows = [...data].reverse();
  setChart("chart-brands", {
    grid: { left: 6, right: 58, top: 10, bottom: 6, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(129,140,248,0.08)" } },
      formatter: (p) => {
        const row = rows[p[0].dataIndex];
        return `<b>${esc(row.brand)}</b><br/>Средняя: <b>${money(row.avg_price_usd)}</b><br/>Медиана: ${money(row.median_price_usd)}<br/>Объявлений: ${nf.format(row.count)}`;
      },
    },
    xAxis: { type: "value", splitLine: SPLIT_LINE, axisLabel: { ...AXIS_LABEL, formatter: (v) => "$" + compact(v) } },
    yAxis: {
      type: "category",
      data: rows.map((r) => r.brand),
      axisLabel: { ...AXIS_LABEL, color: "#c7cffd", fontSize: 11.5 },
      axisTick: { show: false },
      axisLine: AXIS_LINE,
    },
    series: [
      {
        type: "bar",
        data: rows.map((r) => r.avg_price_usd),
        barWidth: "58%",
        itemStyle: { borderRadius: [0, 5, 5, 0], color: hGrad("rgba(129,140,248,0.35)", "#22d3ee") },
        label: {
          show: true,
          position: "right",
          color: "#c7cffd",
          fontSize: 10.5,
          formatter: (p) => "$" + compact(p.value),
        },
      },
    ],
  });
}

function renderBody(data) {
  const total = data.reduce((acc, d) => acc + d.count, 0);
  if (!total) return setChart("chart-body", emptyOption("Нет данных под фильтр"));
  setChart("chart-body", {
    tooltip: { ...TOOLTIP, trigger: "item", formatter: (p) => `${p.name}<br/><b>${nf.format(p.value)}</b> авто (${p.percent}%)` },
    legend: {
      orient: "vertical",
      right: 4,
      top: "center",
      itemWidth: 9,
      itemHeight: 9,
      textStyle: { color: "#8b95b8", fontSize: 11 },
    },
    series: [
      {
        type: "pie",
        radius: ["38%", "72%"],
        center: ["34%", "50%"],
        roseType: "radius",
        itemStyle: { borderColor: "#0b1020", borderWidth: 2, borderRadius: 4 },
        label: { show: false },
        emphasis: { scale: true, scaleSize: 5 },
        data: data.map((d, i) => ({ name: d.name, value: d.count, itemStyle: { color: PALETTE[i % PALETTE.length] } })),
      },
    ],
  });
}

function renderYear(data) {
  if (!data.length) return setChart("chart-year", emptyOption("Нет данных под фильтр"));
  setChart("chart-year", {
    grid: { left: 6, right: 6, top: 34, bottom: 6, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      trigger: "axis",
      axisPointer: { type: "cross", crossStyle: { color: "rgba(129,140,248,0.4)" } },
      formatter: (params) => {
        const year = params[0].axisValue;
        const price = params.find((p) => p.seriesName === "Средняя цена");
        const count = params.find((p) => p.seriesName === "Объявлений");
        return `<b>${year}</b><br/>Средняя цена: <b>${price ? money(price.value) : "—"}</b><br/>Объявлений: ${count ? nf.format(count.value) : "—"}`;
      },
    },
    legend: { top: 0, right: 0, itemWidth: 9, itemHeight: 9, textStyle: { color: "#8b95b8", fontSize: 11 } },
    xAxis: {
      type: "category",
      data: data.map((d) => d.year),
      axisLabel: AXIS_LABEL,
      axisTick: { show: false },
      axisLine: AXIS_LINE,
    },
    yAxis: [
      {
        type: "value",
        name: "цена, $",
        nameTextStyle: { color: "#5c6688", fontSize: 10 },
        splitLine: SPLIT_LINE,
        axisLabel: { ...AXIS_LABEL, formatter: (v) => "$" + compact(v) },
      },
      {
        type: "value",
        name: "объявлений",
        nameTextStyle: { color: "#5c6688", fontSize: 10 },
        splitLine: { show: false },
        axisLabel: AXIS_LABEL,
      },
    ],
    series: [
      {
        name: "Объявлений",
        type: "bar",
        yAxisIndex: 1,
        data: data.map((d) => d.count),
        barWidth: "55%",
        itemStyle: { borderRadius: [4, 4, 0, 0], color: "rgba(129,140,248,0.22)" },
        z: 1,
      },
      {
        name: "Средняя цена",
        type: "line",
        yAxisIndex: 0,
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        data: data.map((d) => d.avg_price_usd),
        lineStyle: { width: 2.5, color: "#22d3ee" },
        itemStyle: { color: "#22d3ee", borderColor: "#0b1020", borderWidth: 2 },
        areaStyle: { color: vGrad("rgba(34,211,238,0.28)", "rgba(34,211,238,0)") },
        z: 3,
      },
    ],
  });
}

function renderFuel(data) {
  if (!data.length) return setChart("chart-fuel", emptyOption("Нет данных под фильтр"));
  const rows = [...data].reverse();
  setChart("chart-fuel", {
    grid: { left: 6, right: 18, top: 10, bottom: 6, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(129,140,248,0.08)" } },
      formatter: (p) => {
        const row = rows[p[0].dataIndex];
        return `<b>${esc(row.name)}</b><br/>${nf.format(row.count)} авто<br/>Средняя цена: ${money(row.avg_price_usd)}`;
      },
    },
    xAxis: { type: "value", splitLine: SPLIT_LINE, axisLabel: AXIS_LABEL },
    yAxis: {
      type: "category",
      data: rows.map((r) => r.name),
      axisLabel: { ...AXIS_LABEL, color: "#c7cffd", fontSize: 10.5 },
      axisTick: { show: false },
      axisLine: AXIS_LINE,
    },
    series: [
      {
        type: "bar",
        data: rows.map((r) => r.count),
        barWidth: "55%",
        itemStyle: { borderRadius: [0, 5, 5, 0], color: hGrad("rgba(52,211,153,0.3)", "#22d3ee") },
      },
    ],
  });
}

function renderScatter(data) {
  if (!data.length) return setChart("chart-scatter", emptyOption("Нет данных под фильтр"));
  setChart("chart-scatter", {
    grid: { left: 6, right: 18, top: 18, bottom: 22, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      trigger: "item",
      formatter: (p) => {
        const d = data[p.dataIndex];
        return `<b>${esc(d.brand || "")}</b><br/>Пробег: ${km(d.x)}<br/>Цена: <b>${money(d.y)}</b><br/>Двигатель: ${esc(d.fuel || "—")}`;
      },
    },
    xAxis: {
      type: "value",
      name: "пробег, км",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: "#5c6688", fontSize: 10 },
      splitLine: SPLIT_LINE,
      axisLabel: { ...AXIS_LABEL, formatter: (v) => compact(v) },
    },
    yAxis: {
      type: "value",
      name: "цена, $",
      nameTextStyle: { color: "#5c6688", fontSize: 10 },
      splitLine: SPLIT_LINE,
      axisLabel: { ...AXIS_LABEL, formatter: (v) => "$" + compact(v) },
    },
    series: [
      {
        type: "scatter",
        data: data.map((d) => [d.x, d.y]),
        symbolSize: 7,
        large: true,
        largeThreshold: 400,
        itemStyle: { color: "rgba(34,211,238,0.5)", borderColor: "rgba(34,211,238,0.85)", borderWidth: 0.5 },
        emphasis: { itemStyle: { color: "#fbbf24", borderColor: "#fbbf24" } },
      },
    ],
  });
}

function renderDays(data) {
  if (!data.some((d) => d.count)) return setChart("chart-days", emptyOption("Нет данных под фильтр"));
  setChart("chart-days", {
    grid: { left: 6, right: 14, top: 26, bottom: 6, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(129,140,248,0.08)" } },
      formatter: (p) => `<b>${p[0].axisValue}</b><br/>${nf.format(p[0].value)} авто`,
    },
    xAxis: {
      type: "category",
      data: data.map((d) => d.name),
      axisLabel: { ...AXIS_LABEL, interval: 0, fontSize: 10 },
      axisTick: { show: false },
      axisLine: AXIS_LINE,
    },
    yAxis: { type: "value", splitLine: SPLIT_LINE, axisLabel: AXIS_LABEL },
    series: [
      {
        type: "bar",
        data: data.map((d) => d.count),
        barWidth: "52%",
        itemStyle: { borderRadius: [5, 5, 0, 0], color: vGrad("#34d399", "rgba(52,211,153,0.2)") },
      },
    ],
  });
}

function renderLocations(data) {
  if (!data.length) return setChart("chart-locations", emptyOption("Нет данных под фильтр"));
  const rows = [...data].reverse();
  setChart("chart-locations", {
    grid: { left: 6, right: 46, top: 8, bottom: 6, containLabel: true },
    tooltip: {
      ...TOOLTIP,
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(129,140,248,0.08)" } },
      formatter: (p) => {
        const row = rows[p[0].dataIndex];
        return `<b>${esc(row.name)}</b><br/>${nf.format(row.count)} авто (${row.share}%)`;
      },
    },
    xAxis: { type: "value", splitLine: SPLIT_LINE, axisLabel: AXIS_LABEL },
    yAxis: {
      type: "category",
      data: rows.map((r) => r.name),
      axisLabel: { ...AXIS_LABEL, color: "#c7cffd", fontSize: 11 },
      axisTick: { show: false },
      axisLine: AXIS_LINE,
    },
    series: [
      {
        type: "bar",
        data: rows.map((r) => r.count),
        barWidth: "55%",
        itemStyle: { borderRadius: [0, 5, 5, 0], color: hGrad("rgba(167,139,250,0.3)", "#818cf8") },
        label: { show: true, position: "right", color: "#8b95b8", fontSize: 10, formatter: (p) => nf.format(p.value) },
      },
    ],
  });
}

function renderDeals(page) {
  state.dealsPage = page.page;
  const wrap = document.getElementById("deals");
  document.getElementById("deals-total").textContent = page.total
    ? `${nf.format(page.total)} объявлений ниже медианы своей марки`
    : "прозрачная эвристика, не оценка стоимости";
  document.getElementById("deals-page-info").textContent = `${page.page} / ${page.pages}`;
  document.getElementById("btn-deals-prev").disabled = page.page <= 1;
  document.getElementById("btn-deals-next").disabled = page.page >= page.pages;

  if (!page.items.length) {
    wrap.innerHTML = "";
    return;
  }
  wrap.innerHTML = page.items
    .map((d) => {
      const photo = d.photo
        ? `<img class="deal__img" loading="lazy" src="${esc(d.photo)}" alt="${esc(d.brand + " " + d.model)}" />`
        : `<div class="deal__img deal__img--empty">${esc((d.brand || "?")[0])}</div>`;
      return `<a class="deal" href="${esc(safeUrl(d.url))}" target="_blank" rel="noopener">
        ${photo}
        <div class="deal__body">
          <span class="deal__name">${esc(d.brand)} ${esc(d.model)}</span>
          <span class="deal__meta">${esc(d.year ?? "—")} · ${km(d.mileage_km)} · ${esc(d.location || "—")}</span>
          <span class="deal__price">${money(d.price_usd)}</span>
        </div>
        <span class="deal__badge">−${d.discount_pct}%</span>
      </a>`;
    })
    .join("");
}

function renderTable(page) {
  const body = document.getElementById("table-body");
  document.getElementById("table-total").textContent =
    `${nf.format(page.total)} объявлений в выборке`;
  document.getElementById("page-info").textContent = `${page.page} / ${page.pages}`;
  document.getElementById("btn-prev").disabled = page.page <= 1;
  document.getElementById("btn-next").disabled = page.page >= page.pages;

  body.innerHTML = page.items
    .map((c) => {
      const title = `${c.brand || ""} ${c.model || ""}`.trim() || "Автомобиль";
      const photo = c.photo
        ? `<img loading="lazy" src="${esc(c.photo)}" alt="${esc(title)}" />`
        : `<span class="thumb">${esc((c.brand || "?")[0])}</span>`;
      const engine = [c.engine_type, c.engine_power ? c.engine_power + " л.с." : null].filter(Boolean).join(" · ");
      return `<tr>
        <td>
          <div class="car-cell">
            ${photo}
            <div>
              <a href="${esc(safeUrl(c.url))}" target="_blank" rel="noopener">${esc(title)}</a>
              <small>${esc(c.body_type || "—")}${c.transmission ? " · " + esc(c.transmission) : ""}</small>
            </div>
          </div>
        </td>
        <td>${esc(c.year ?? "—")}</td>
        <td>${km(c.mileage_km)}</td>
        <td>${esc(engine || "—")}</td>
        <td>${esc(c.location || "—")}</td>
        <td class="ta-right price-cell">${money(c.price_usd)}<small>${c.price_byn ? nf.format(c.price_byn) + " BYN" : ""}</small></td>
      </tr>`;
    })
    .join("");
}

function renderDashboard(data) {
  state.scrapedAt = data.meta?.scraped_at ?? state.scrapedAt;
  renderMeta(data.meta);
  renderKpis(data.summary);
  renderInsight(data);
  renderPriceHistogram(data.charts.price_histogram);
  renderSegments(data.charts.price_segments);
  renderBrands(data.charts.by_brand);
  renderBody(data.charts.by_body);
  renderYear(data.charts.by_year);
  renderFuel(data.charts.by_fuel);
  renderScatter(data.charts.price_vs_mileage);
  renderDays(data.charts.days_on_sale);
  renderLocations(data.charts.by_location);
  renderDeals(data.deals);
  renderTable(data.cars);
  populateSort(data.sort_options);
}

/* ----------------------------- data source ----------------------------- */

/* Two interchangeable backends:
 *   api    — FastAPI (/api/*), used by `uvicorn app.server:app`
 *   static — prebuilt JSON in data/, used by GitHub Pages (no server)
 * The UI code below never cares which one is active. */

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

let staticCache = { dataset: null, meta: null };

async function detectMode() {
  // scripts/build-static.py marks the published copy, so Pages never probes
  // /api/meta (a 404 there would show up as an error in devtools).
  if (document.documentElement.dataset.mode === "static") return "static";
  try {
    await fetchJson(`${API}/meta`);
    return "api";
  } catch (error) {
    return "static";
  }
}

async function staticDataset(force = false) {
  if (force || !staticCache.dataset) {
    const data = await fetchJson(`${STATIC_DATA}/cars.json?t=${Date.now()}`);
    data.meta = {
      source: data.source,
      scraped_at: data.scraped_at,
      count: data.count ?? (data.cars || []).length,
      pages: data.pages,
    };
    staticCache.dataset = data;
  }
  return staticCache.dataset;
}

async function staticMeta() {
  try {
    return await fetchJson(`${STATIC_DATA}/meta.json?t=${Date.now()}`);
  } catch (error) {
    return (await staticDataset()).meta;
  }
}

async function requestDashboard() {
  if (state.mode === "api") return fetchJson(`${API}/dashboard?${queryString(true)}`);
  const dataset = await staticDataset();
  const result = AvbyAnalytics.buildDashboard(dataset.cars, state.page, PAGE_SIZE, state.filters);
  result.meta = dataset.meta;
  result.sort_options = AvbyAnalytics.SORT_OPTIONS.map(({ id, label }) => ({ id, label }));
  return result;
}

async function requestDeals(page) {
  if (state.mode === "api") {
    const params = new URLSearchParams(queryString(false));
    params.set("page", String(page));
    params.set("page_size", String(DEALS_PAGE_SIZE));
    return fetchJson(`${API}/deals?${params}`);
  }
  const dataset = await staticDataset();
  return AvbyAnalytics.buildDeals(dataset.cars, page, DEALS_PAGE_SIZE, state.filters);
}

function downloadCsv(filename, text) {
  const blob = new Blob(["\ufeff" + text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* ----------------------------- data loading ----------------------------- */

function value(id) {
  const el = document.getElementById(id);
  const v = el.value.trim();
  return v === "" ? null : v;
}
function number(id) {
  const v = value(id);
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function currentFilters() {
  return {
    brand: value("f-brand"),
    body: value("f-body"),
    fuel: value("f-fuel"),
    year_min: number("f-year-min"),
    year_max: number("f-year-max"),
    price_min: number("f-price-min"),
    price_max: number("f-price-max"),
    mileage_max: number("f-mileage-max"),
    q: value("f-q"),
    sort: value("f-sort") || "relevance",
  };
}
function queryString(includePage = true) {
  const params = new URLSearchParams();
  const f = state.filters;
  for (const [key, val] of Object.entries(f)) {
    if (val != null && val !== "") params.set(key, val);
  }
  if (includePage) {
    params.set("page", state.page);
    params.set("page_size", PAGE_SIZE);
  }
  return params.toString();
}
/* API mode: plain links, the server builds the CSV.
 * Static mode: no server, so the same links are wired to Blob downloads. */
function syncExport() {
  if (state.mode !== "api") return;
  document.getElementById("btn-export").href = `${API}/export.csv?${queryString(false)}`;
  document.getElementById("btn-deals-export").href = `${API}/deals.csv?${queryString(false)}`;
}

function bindExports() {
  if (state.mode === "api") return;
  const carsLink = document.getElementById("btn-export");
  const dealsLink = document.getElementById("btn-deals-export");
  carsLink.removeAttribute("href");
  dealsLink.removeAttribute("href");
  carsLink.addEventListener("click", async (event) => {
    event.preventDefault();
    const dataset = await staticDataset();
    downloadCsv("cars.csv", AvbyAnalytics.exportCars(dataset.cars, state.filters));
  });
  dealsLink.addEventListener("click", async (event) => {
    event.preventDefault();
    const dataset = await staticDataset();
    downloadCsv("deals.csv", AvbyAnalytics.exportDeals(dataset.cars, state.filters));
  });
}

let loadingCount = 0;
function setLoading(on) {
  loadingCount += on ? 1 : -1;
  loadingCount = Math.max(0, loadingCount);
  document.getElementById("loading").classList.toggle("is-on", loadingCount > 0);
}

let toastTimer;
function showToast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.add("is-on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-on"), 4500);
}

let requestSeq = 0;
async function loadDashboard() {
  const seq = ++requestSeq;
  state.loading = true;
  state.filters = currentFilters();
  syncExport();
  setLoading(true);
  try {
    const response = await requestDashboard();
    if (seq !== requestSeq) return; // a newer request won
    renderDashboard(response);
  } catch (error) {
    if (seq !== requestSeq) return;
    console.error(error);
    document.getElementById("table-body").innerHTML = "";
    showToast("Не удалось загрузить данные — проверьте, что датасет собран (py -m scraper.cli --pages 50)");
  } finally {
    setLoading(false);
    if (seq === requestSeq) state.loading = false;
  }
}

let dealsSeq = 0;
async function loadDeals(page = 1) {
  const seq = ++dealsSeq;
  setLoading(true);
  try {
    const data = await requestDeals(page);
    if (seq !== dealsSeq) return;
    renderDeals(data);
  } catch (error) {
    if (seq !== dealsSeq) return;
    console.error("deals failed", error);
    renderDeals({ items: [], total: 0, page: 1, pages: 1 });
  } finally {
    setLoading(false);
  }
}

async function checkForUpdates() {
  if (document.hidden || state.loading) return;
  try {
    const meta = state.mode === "api" ? await fetchJson(`${API}/meta`) : await staticMeta();
    if (meta.scraped_at && meta.scraped_at !== state.scrapedAt) {
      if (state.mode === "static") await staticDataset(true);
      await loadDashboard();
      showToast(
        "Данные обновлены — срез от " +
          new Date(meta.scraped_at).toLocaleString("ru-RU", {
            day: "2-digit",
            month: "long",
            hour: "2-digit",
            minute: "2-digit",
          })
      );
    }
  } catch (error) {
    /* server restarting or offline — retry on the next tick */
  }
}

function populateSort(options) {
  const select = document.getElementById("f-sort");
  if (select.dataset.ready === "1") return;
  select.innerHTML = (options || [])
    .map((o) => `<option value="${esc(o.id)}">${esc(o.label)}</option>`)
    .join("");
  select.value = "relevance";
  select.dataset.ready = "1";
}

async function loadFilters() {
  let data;
  if (state.mode === "api") {
    data = await fetchJson(`${API}/filters`);
  } else {
    const dataset = await staticDataset();
    data = AvbyAnalytics.filterOptions(dataset.cars);
  }
  const fill = (id, items, allLabel, labeler) => {
    const select = document.getElementById(id);
    select.innerHTML =
      `<option value="">${esc(allLabel)}</option>` +
      items.map((item) => `<option value="${esc(item.name)}">${esc(labeler(item))}</option>`).join("");
  };
  fill("f-brand", data.brands, "Все марки", (i) => `${i.name} (${i.count})`);
  fill("f-body", data.bodies, "Любой кузов", (i) => `${i.name} (${i.count})`);
  fill("f-fuel", data.fuels, "Любой", (i) => `${i.name} (${i.count})`);
  document.getElementById("f-year-min").placeholder = data.year_min ?? "1990";
  document.getElementById("f-year-max").placeholder = data.year_max ?? "2026";
  document.getElementById("f-price-min").placeholder = data.price_min ?? "0";
  document.getElementById("f-price-max").placeholder = data.price_max ?? "200000";
}

async function loadMeta() {
  try {
    const meta = state.mode === "api" ? await fetchJson(`${API}/meta`) : await staticMeta();
    if (meta) renderMeta(meta);
  } catch (error) {
    console.warn("meta unavailable", error);
  }
}

/* ----------------------------- wiring ----------------------------- */

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function bindFilters() {
  const onChange = () => {
    state.page = 1;
    loadDashboard();
  };
  const debounced = debounce(onChange, 300);

  ["f-brand", "f-body", "f-fuel", "f-sort"].forEach((id) =>
    document.getElementById(id).addEventListener("change", onChange)
  );
  ["f-year-min", "f-year-max", "f-price-min", "f-price-max", "f-mileage-max"].forEach((id) =>
    document.getElementById(id).addEventListener("input", debounced)
  );
  document.getElementById("f-q").addEventListener("input", debounced);
  document.getElementById("f-q").addEventListener("keydown", (e) => {
    if (e.key === "Enter") onChange();
  });

  document.getElementById("btn-reset").addEventListener("click", () => {
    ["f-brand", "f-body", "f-fuel", "f-year-min", "f-year-max", "f-price-min", "f-price-max", "f-mileage-max", "f-q"].forEach(
      (id) => (document.getElementById(id).value = "")
    );
    document.getElementById("f-sort").value = "relevance";
    state.page = 1;
    loadDashboard();
  });

  document.getElementById("btn-prev").addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      loadDashboard();
      document.getElementById("table-body").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
  document.getElementById("btn-next").addEventListener("click", () => {
    state.page += 1;
    loadDashboard();
    document.getElementById("table-body").scrollIntoView({ behavior: "smooth", block: "center" });
  });

  const dealsSection = document.getElementById("deals-section");
  const showDeals = (page) => {
    loadDeals(page);
    dealsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  document.getElementById("btn-deals-prev").addEventListener("click", () => {
    if (state.dealsPage > 1) showDeals(state.dealsPage - 1);
  });
  document.getElementById("btn-deals-next").addEventListener("click", () => {
    showDeals(state.dealsPage + 1);
  });

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => Object.values(charts).forEach((c) => c.resize()), 120);
  });
}

async function init() {
  state.mode = await detectMode();
  bindFilters();
  bindExports();
  try {
    await Promise.all([loadFilters(), loadMeta()]);
  } catch (error) {
    console.error("filter options failed", error);
  }
  await loadDashboard();

  // Poll for a fresh snapshot (the scheduled task re-scrapes at 13:00) and
  // refresh immediately when the user comes back to the tab.
  setInterval(checkForUpdates, REFRESH_MS);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) checkForUpdates();
  });
}

init();
