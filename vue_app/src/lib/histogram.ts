export function buildHistogram(input: readonly number[]) {
  const values = input.filter(Number.isFinite);
  if (!values.length) return null;
  const minimum = Math.min(...values),
    maximum = Math.max(...values);
  const constant = minimum === maximum;
  const padding = Math.max(0.5, Math.abs(minimum) * 0.01);
  const start = constant ? minimum - padding : minimum;
  const end = constant ? maximum + padding : maximum;
  const count = constant
    ? 1
    : Math.min(16, Math.ceil(Math.sqrt(values.length)));
  const width = (end - start) / count;
  const bins = Array.from({ length: count }, (_, i) => ({
    lower: start + i * width,
    upper: i === count - 1 ? end : start + (i + 1) * width,
    count: 0,
  }));
  for (const value of values)
    bins[Math.min(count - 1, Math.max(0, Math.floor((value - start) / width)))]
      .count++;
  const peak = Math.max(...bins.map((bin) => bin.count));
  const rough = Math.max(1, peak / 4);
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = Math.max(
    1,
    ([1, 2, 5, 10].find((value) => value * power >= rough) || 10) * power,
  );
  const ceiling = Math.ceil(peak / step) * step;
  const yTicks = Array.from(
    { length: Math.round(ceiling / step) + 1 },
    (_, i) => i * step,
  );
  const xTicks = Array.from(
    { length: 6 },
    (_, i) => start + ((end - start) * i) / 5,
  );
  const digits = Math.min(
    8,
    Math.max(0, 2 - Math.floor(Math.log10((end - start) / 5))),
  );
  const format = (value: number) =>
    value.toLocaleString("zh-CN", {
      maximumFractionDigits: digits,
      useGrouping: false,
    });
  return {
    minimum,
    maximum,
    start,
    end,
    bins,
    xTicks,
    yTicks,
    ceiling,
    total: values.length,
    format,
  };
}
