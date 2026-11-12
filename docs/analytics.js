/* AV.BY Market Pulse — client-side analytics.
 *
 * A JavaScript mirror of app/analytics.py, used only in static mode
 * (GitHub Pages), where there is no FastAPI backend. The Python module stays
 * the reference implementation; tests/test_analytics.py covers it, and the
 * dashboard is checked against /api/* for parity.
 *
 * Exposes a single global: window.AvbyAnalytics.
 */
(function (global) {
  "use strict";

  const SORT_OPTIONS = [
    { id: "relevance", label: "По релевантности", key: null },
    { id: "price_asc", label: "Цена: по возрастанию", key: (c) => c.price_usd || 0 },
    { id: "price_desc", label: "Цена: по убыванию", key: (c) => -(c.price_usd || 0) },
    { id: "year_desc", label: "Год: новее", key: (c) => -(c.year || 0) },
    { id: "year_asc", label: "Год: старше", key: (c) => c.year || 0 },
    { id: "mileage_asc", label: "Пробег: меньше", key: (c) => c.mileage_km || 0 },
    { id: "mileage_desc", label: "Пробег: больше", key: (c) => -(c.mileage_km || 0) },
    { id: "fresh", label: "Дольше всего в продаже", key: (c) => -(c.days_on_sale || 0) },
    { id: "score_desc", label: "В порядке убывания скорингового балла", key: (c) => -(c.score || 0) },
    {
      id: "score_price_asc",
      label: "В порядке убывания скорингового балла и возрастания цены",
      // Score first, cheapest listing first among equal scores.
      key: (c) => [-(c.score || 0), c.price_usd || 0],
    },
  ];
  const SORT_KEYS = new Map(SORT_OPTIONS.map((o) => [o.id, o.key]));

  /* A sort key is either a number or an array of numbers (primary key, then
   * tie-breakers), so the comparator walks the array field by field. */
  function compareByKey(key) {
    return (a, b) => {
      const ka = key(a);
      const kb = key(b);
      if (Array.isArray(ka)) {
        for (let i = 0; i < ka.length; i += 1) {
          if (ka[i] !== kb[i]) return ka[i] - kb[i];
        }
        return 0;
      }
      return ka - kb;
    };
  }

  /* Each half of the 0..10 score: up to 5 points for a newer year, up to 5
   * for lower mileage. Both scales are linear over the whole dataset, so a
   * listing keeps the same score no matter which filters are active. */
  const SCORE_MAX = 5;

  function scoreBounds(cars) {
    const years = cars.filter((c) => c.year).map((c) => c.year);
    const kms = cars.filter((c) => c.mileage_km != null).map((c) => c.mileage_km);
    if (!years.length || !kms.length) return null;
    return {
      yLo: Math.min(...years),
      yHi: Math.max(...years),
      kLo: Math.min(...kms),
      kHi: Math.max(...kms),
    };
  }

  function scale(value, low, high, reverse = false) {
    if (high <= low) return SCORE_MAX;
    let ratio = (value - low) / (high - low);
    if (reverse) ratio = 1 - ratio;
    return round1(SCORE_MAX * Math.min(1, Math.max(0, ratio)));
  }

  function withScore(cars, reference) {
    const bounds = scoreBounds(reference || cars);
    return cars.map((car) => {
      const item = Object.assign({}, car);
      item.score_year = bounds && car.year ? scale(car.year, bounds.yLo, bounds.yHi) : 0;
      item.score_mileage =
        bounds && car.mileage_km != null ? scale(car.mileage_km, bounds.kLo, bounds.kHi, true) : 0;
      item.score = round1(item.score_year + item.score_mileage);
      return item;
    });
  }

  const PRICE_BUCKETS = [
    [0, 3000, "до $3k"],
    [3000, 6000, "$3–6k"],
    [6000, 10000, "$6–10k"],
    [10000, 15000, "$10–15k"],
    [15000, 20000, "$15–20k"],
    [20000, 30000, "$20–30k"],
    [30000, 40000, "$30–40k"],
    [40000, 60000, "$40–60k"],
    [60000, 80000, "$60–80k"],
    [80000, 1e12, "$80k+"],
  ];

  const DAY_BUCKETS = [
    ["0–7 дней", 0, 7],
    ["8–30 дней", 8, 30],
    ["31–90 дней", 31, 90],
    ["90+ дней", 91, 1e9],
  ];

  const CARS_COLUMNS = [
    ["id", "ID"],
    ["brand", "Марка"],
    ["model", "Модель"],
    ["year", "Год"],
    ["score", "Балл"],
    ["price_usd", "Цена, USD"],
    ["price_byn", "Цена, BYN"],
    ["mileage_km", "Пробег, км"],
    ["engine_type", "Двигатель"],
    ["engine_capacity", "Объём, л"],
    ["engine_power", "Мощность, л.с."],
    ["transmission", "КПП"],
    ["body_type", "Кузов"],
    ["drive_type", "Привод"],
    ["color", "Цвет"],
    ["condition", "Состояние"],
    ["location", "Город"],
    ["seller", "Продавец"],
    ["days_on_sale", "Дней в продаже"],
    ["url", "Ссылка"],
  ];

  const DEAL_COLUMNS = [
    ["id", "ID"],
    ["brand", "Марка"],
    ["model", "Модель"],
    ["year", "Год"],
    ["score", "Балл"],
    ["price_usd", "Цена, USD"],
    ["brand_median_usd", "Медиана, USD"],
    ["discount_pct", "Ниже медианы, %"],
    ["mileage_km", "Пробег, км"],
    ["engine_type", "Двигатель"],
    ["body_type", "Кузов"],
    ["location", "Город"],
    ["url", "Ссылка"],
  ];

  const round1 = (n) => Math.round(n * 10) / 10;

  function avg(values) {
    const nums = values.filter((v) => v != null);
    if (!nums.length) return null;
    return round1(nums.reduce((a, b) => a + b, 0) / nums.length);
  }

  function median(values) {
    const nums = values.filter((v) => v != null).slice().sort((a, b) => a - b);
    if (!nums.length) return null;
    const mid = Math.floor(nums.length / 2);
    return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
  }

  function filterCars(cars, filters) {
    const f = filters || {};
    let result = cars;
    if (f.brand) result = result.filter((c) => c.brand === f.brand);
    if (f.model) result = result.filter((c) => c.model === f.model);
    if (f.body) result = result.filter((c) => c.body_type === f.body);
    if (f.fuel) result = result.filter((c) => c.engine_type === f.fuel);
    if (f.year_min != null) result = result.filter((c) => (c.year || 0) >= f.year_min);
    if (f.year_max != null) result = result.filter((c) => (c.year || 0) <= f.year_max);
    if (f.price_min != null) result = result.filter((c) => (c.price_usd || 0) >= f.price_min);
    if (f.price_max != null) result = result.filter((c) => (c.price_usd || 0) <= f.price_max);
    if (f.mileage_max != null) result = result.filter((c) => (c.mileage_km || 0) <= f.mileage_max);
    if (f.q) {
      const needle = String(f.q).trim().toLowerCase();
      if (needle) {
        result = result.filter((c) =>
          `${c.brand || ""} ${c.model || ""}`.toLowerCase().includes(needle)
        );
      }
    }

    const key = SORT_KEYS.get(f.sort);
    result = withScore(result, cars);
    if (key) result = result.slice().sort(compareByKey(key));
    return result;
  }

  function summary(cars) {
    const prices = cars.filter((c) => c.price_usd).map((c) => c.price_usd);
    const years = cars.filter((c) => c.year).map((c) => c.year);
    const mileage = cars.filter((c) => c.mileage_km).map((c) => c.mileage_km);
    const brands = new Set(cars.filter((c) => c.brand).map((c) => c.brand));
    const electric = cars.filter((c) => c.engine_type === "электро").length;

    const brandCounts = new Map();
    for (const c of cars) {
      if (c.brand) brandCounts.set(c.brand, (brandCounts.get(c.brand) || 0) + 1);
    }
    let topBrand = null;
    let topCount = 0;
    for (const [brand, count] of brandCounts) {
      if (count > topCount) {
        topBrand = brand;
        topCount = count;
      }
    }

    return {
      total: cars.length,
      avg_price_usd: avg(prices),
      median_price_usd: prices.length ? round1(median(prices)) : null,
      min_price_usd: prices.length ? Math.min(...prices) : null,
      max_price_usd: prices.length ? Math.max(...prices) : null,
      avg_year: avg(years),
      avg_mileage_km: avg(mileage),
      electric_share: cars.length ? round1((electric / cars.length) * 100) : 0.0,
      top_brand: topBrand,
      brands_count: brands.size,
    };
  }

  function priceHistogram(cars) {
    const counts = new Array(PRICE_BUCKETS.length).fill(0);
    for (const car of cars) {
      const price = car.price_usd;
      if (!price) continue;
      for (let i = 0; i < PRICE_BUCKETS.length; i += 1) {
        const [lo, hi] = PRICE_BUCKETS[i];
        if (price >= lo && price < hi) {
          counts[i] += 1;
          break;
        }
      }
    }
    return { labels: PRICE_BUCKETS.map((b) => b[2]), values: counts };
  }

  function groupBy(cars, field) {
    const groups = new Map();
    for (const car of cars) {
      const key = car[field];
      if (!key) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(car);
    }
    return groups;
  }

  function byBrand(cars, limit = 12, minCount = 2) {
    const rows = [];
    for (const [brand, items] of groupBy(cars, "brand")) {
      if (items.length < minCount) continue;
      const prices = items.filter((c) => c.price_usd).map((c) => c.price_usd);
      rows.push({
        brand,
        count: items.length,
        avg_price_usd: avg(prices),
        median_price_usd: prices.length ? round1(median(prices)) : null,
      });
    }
    rows.sort((a, b) => b.count - a.count);
    return rows.slice(0, limit);
  }

  function byCategory(cars, field, limit = 10) {
    const counter = new Map();
    for (const car of cars) {
      const value = car[field];
      if (!value) continue;
      counter.set(value, (counter.get(value) || 0) + 1);
    }
    const total = Array.from(counter.values()).reduce((a, b) => a + b, 0) || 1;
    const rows = Array.from(counter, ([name, count]) => ({
      name,
      count,
      share: round1((count / total) * 100),
    }));
    rows.sort((a, b) => b.count - a.count);
    return rows.slice(0, limit);
  }

  function byFuel(cars) {
    const rows = [];
    for (const [name, items] of groupBy(cars, "engine_type")) {
      const prices = items.filter((c) => c.price_usd).map((c) => c.price_usd);
      rows.push({ name, count: items.length, avg_price_usd: avg(prices) });
    }
    rows.sort((a, b) => b.count - a.count);
    return rows;
  }

  function byYear(cars, minYear = 1990, minCount = 2) {
    const groups = new Map();
    for (const car of cars) {
      const year = car.year;
      if (!year || year < minYear) continue;
      if (!groups.has(year)) groups.set(year, []);
      groups.get(year).push(car);
    }
    const rows = [];
    for (const year of Array.from(groups.keys()).sort((a, b) => a - b)) {
      const items = groups.get(year);
      if (items.length < minCount) continue;
      const prices = items.filter((c) => c.price_usd).map((c) => c.price_usd);
      rows.push({ year, count: items.length, avg_price_usd: avg(prices) });
    }
    return rows;
  }

  function priceSegments(cars) {
    const edges = [0, 5000, 10000, 20000, 40000, 1e12];
    const labels = ["до $5k", "$5–10k", "$10–20k", "$20–40k", "$40k+"];
    const counts = new Array(labels.length).fill(0);
    for (const car of cars) {
      const price = car.price_usd;
      if (!price) continue;
      for (let i = 0; i < labels.length; i += 1) {
        if (price >= edges[i] && price < edges[i + 1]) {
          counts[i] += 1;
          break;
        }
      }
    }
    return labels.map((name, i) => ({ name, count: counts[i] }));
  }

  function daysOnSaleHistogram(cars) {
    const counts = new Array(DAY_BUCKETS.length).fill(0);
    for (const car of cars) {
      const days = car.days_on_sale;
      if (days == null) continue;
      for (let i = 0; i < DAY_BUCKETS.length; i += 1) {
        const [, lo, hi] = DAY_BUCKETS[i];
        if (days >= lo && days <= hi) {
          counts[i] += 1;
          break;
        }
      }
    }
    return DAY_BUCKETS.map(([name], i) => ({ name, count: counts[i] }));
  }

  function priceVsMileage(cars, limit = 700) {
    let points = cars
      .filter((c) => c.mileage_km && c.price_usd)
      .map((c) => ({
        x: c.mileage_km,
        y: c.price_usd,
        brand: c.brand,
        fuel: c.engine_type,
        url: c.url,
      }));
    if (points.length > limit) {
      const step = points.length / limit;
      points = Array.from({ length: limit }, (_, i) => points[Math.floor(i * step)]);
    }
    return points;
  }

  function belowBrandMedian(
    cars,
    minBrandCount = 5,
    sort = "relevance",
    reference,
    model,
    minModelCount = 3
  ) {
    // Medians come from `reference` (the full dataset), so an active filter
    // cannot raise a brand's median and let above-median cars into the block.
    // With a model selected the median is the brand+model pair's median, so
    // the block answers "ниже медианы по марке и модели".
    const basis = reference || cars;
    const scope = model ? "model" : "brand";
    const minCount = model ? minModelCount : minBrandCount;
    const keyOf = (car) => {
      if (!car.brand || !car.price_usd) return null;
      if (scope === "model") return car.model ? `${car.brand}\u0000${car.model}` : null;
      return car.brand;
    };

    const groups = new Map();
    for (const car of basis) {
      const key = keyOf(car);
      if (key == null) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(car);
    }
    const medians = new Map();
    for (const [key, items] of groups) {
      const prices = items.filter((c) => c.price_usd).map((c) => c.price_usd);
      if (items.length >= minCount && prices.length) medians.set(key, median(prices));
    }

    const scored = [];
    for (const car of cars) {
      const key = keyOf(car);
      const price = car.price_usd;
      if (key == null || !medians.has(key) || !price) continue;
      const groupMedian = medians.get(key);
      const discount = ((groupMedian - price) / groupMedian) * 100;
      if (discount <= 0) continue;
      scored.push({
        id: car.id,
        brand: car.brand,
        model: car.model,
        year: car.year,
        mileage_km: car.mileage_km,
        price_usd: price,
        price_byn: car.price_byn,
        discount_pct: round1(discount),
        brand_median_usd: round1(groupMedian),
        median_scope: scope,
        engine_type: car.engine_type,
        body_type: car.body_type,
        days_on_sale: car.days_on_sale,
        score: car.score,
        score_year: car.score_year,
        score_mileage: car.score_mileage,
        photo: car.photo,
        url: car.url,
        location: car.location,
      });
    }
    // Default: biggest gap to the median first. A chosen sort key re-orders
    // the same rows exactly like the listings table.
    scored.sort((a, b) => b.discount_pct - a.discount_pct);
    const key = SORT_KEYS.get(sort);
    if (key) scored.sort(compareByKey(key));
    return scored;
  }

  /* What the "below median" block compares against: the brand, or the
   * brand+model pair when the model filter is active. `group_count` is how
   * many such listings exist in the full dataset, so an empty block can
   * explain itself. */
  function dealsScope(filters, reference, minModelCount = 3) {
    const f = filters || {};
    const model = f.model || null;
    const brand = f.brand || null;
    const scope = model ? "model" : "brand";
    let groupCount = null;
    if (reference) {
      if (model) {
        groupCount = reference.filter(
          (c) => c.model === model && (!brand || c.brand === brand)
        ).length;
      } else if (brand) {
        groupCount = reference.filter((c) => c.brand === brand).length;
      }
    }
    return {
      scope,
      brand,
      model,
      min_count: model ? minModelCount : 5,
      group_count: groupCount,
    };
  }

  function paginate(cars, page = 1, pageSize = 20) {
    page = Math.max(1, page);
    pageSize = Math.min(Math.max(1, pageSize), 100);
    const total = cars.length;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    page = Math.min(page, pages);
    const start = (page - 1) * pageSize;
    return {
      items: cars.slice(start, start + pageSize),
      total,
      page,
      page_size: pageSize,
      pages,
    };
  }

  function buildDashboard(cars, page = 1, pageSize = 12, filters = {}) {
    const filtered = filterCars(cars, filters);
    // Medians always come from the full dataset, like the 0..10 score.
    const model = filters.model || null;
    const deals = belowBrandMedian(filtered, 5, filters.sort || "relevance", cars, model);
    const dealsPage = paginate(deals, 1, 12);
    dealsPage.scope = dealsScope(filters, cars);
    return {
      summary: summary(filtered),
      charts: {
        price_histogram: priceHistogram(filtered),
        by_brand: byBrand(filtered),
        by_body: byCategory(filtered, "body_type", 8),
        by_fuel: byFuel(filtered),
        by_year: byYear(filtered),
        price_segments: priceSegments(filtered),
        days_on_sale: daysOnSaleHistogram(filtered),
        price_vs_mileage: priceVsMileage(filtered),
        by_location: byCategory(filtered, "location", 10),
      },
      deals: dealsPage,
      best_deals: deals.slice(0, 8),
      cars: paginate(filtered, page, pageSize),
    };
  }

  function buildDeals(cars, page = 1, pageSize = 12, filters = {}) {
    const f = filters || {};
    const model = f.model || null;
    const result = paginate(
      belowBrandMedian(filterCars(cars, f), 5, f.sort || "relevance", cars, model),
      page,
      pageSize
    );
    result.scope = dealsScope(f, cars);
    return result;
  }

  function filterOptions(cars) {
    const count = (field) => {
      const counter = new Map();
      for (const car of cars) {
        const value = car[field];
        if (!value) continue;
        counter.set(value, (counter.get(value) || 0) + 1);
      }
      return Array.from(counter, ([name, n]) => ({ name, count: n })).sort(
        (a, b) => b.count - a.count
      );
    };
    const years = cars.filter((c) => c.year).map((c) => c.year);
    const prices = cars.filter((c) => c.price_usd).map((c) => c.price_usd);
    // Model names are only unique inside a brand, so the select is keyed by
    // the brand+model pair.
    const models = new Map();
    for (const car of cars) {
      if (!car.brand || !car.model) continue;
      const key = `${car.brand}\u0000${car.model}`;
      const entry = models.get(key) || { brand: car.brand, name: car.model, count: 0 };
      entry.count += 1;
      models.set(key, entry);
    }
    return {
      brands: count("brand"),
      models: Array.from(models.values()).sort(
        (a, b) =>
          a.brand.localeCompare(b.brand) || b.count - a.count || a.name.localeCompare(b.name)
      ),
      bodies: count("body_type"),
      fuels: count("engine_type"),
      year_min: years.length ? Math.min(...years) : null,
      year_max: years.length ? Math.max(...years) : null,
      price_min: prices.length ? Math.min(...prices) : null,
      price_max: prices.length ? Math.max(...prices) : null,
    };
  }

  function csvValue(value) {
    const text = value == null ? "" : String(value);
    return /[;"\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function toCsv(columns, rows) {
    const lines = [columns.map(([, label]) => label).join(";")];
    for (const row of rows) {
      lines.push(columns.map(([key]) => csvValue(row[key])).join(";"));
    }
    return lines.join("\r\n") + "\r\n";
  }

  const exportCars = (cars, filters) => toCsv(CARS_COLUMNS, filterCars(cars, filters));
  const exportDeals = (cars, filters) => {
    const f = filters || {};
    return toCsv(
      DEAL_COLUMNS,
      belowBrandMedian(filterCars(cars, f), 5, f.sort || "relevance", cars, f.model || null)
    );
  };

  global.AvbyAnalytics = {
    SORT_OPTIONS,
    filterCars,
    summary,
    belowBrandMedian,
    dealsScope,
    paginate,
    buildDashboard,
    buildDeals,
    filterOptions,
    exportCars,
    exportDeals,
  };
})(window);
