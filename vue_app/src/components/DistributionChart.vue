<script setup lang="ts">
import { computed, ref } from "vue";
import { buildHistogram } from "@/lib/histogram";
const props = defineProps<{ values: number[] }>();
const chart = computed(() => buildHistogram(props.values));
const hovered = ref<number | null>(null);
const left = 56,
  top = 28,
  width = 566,
  height = 166,
  bottom = top + height;
const x = (value: number) =>
  left +
  ((value - chart.value!.start) / (chart.value!.end - chart.value!.start)) *
    width;
const y = (value: number) => bottom - (value / chart.value!.ceiling) * height;
function description(index: number) {
  const data = chart.value!,
    bin = data.bins[index];
  return `${bin.lower.toLocaleString("zh-CN", { maximumFractionDigits: 6, useGrouping: false })} ≤ 数值 ${index === data.bins.length - 1 ? "≤" : "<"} ${bin.upper.toLocaleString("zh-CN", { maximumFractionDigits: 6, useGrouping: false })}：${bin.count} 个`;
}
</script>
<template>
  <figure v-if="chart" class="distribution-chart" aria-label="模拟数据分布预览">
    <figcaption>
      <strong>生成数据分布</strong>
      <span
        >实际范围：{{ chart.minimum }} ～ {{ chart.maximum }} · 共
        {{ chart.total }} 个数值</span
      >
    </figcaption>
    <div class="distribution-scroll">
      <svg viewBox="0 0 640 240" role="group" aria-label="数值区间与频数直方图">
        <text x="10" y="15" class="axis-label">频数（个）</text>
        <g v-for="tick in chart.yTicks" :key="'y' + tick">
          <line
            :x1="left"
            :x2="left + width"
            :y1="y(tick)"
            :y2="y(tick)"
            class="chart-grid"
          />
          <text :x="left - 9" :y="y(tick) + 4" text-anchor="end">
            {{ tick }}
          </text>
        </g>
        <line :x1="left" :x2="left" :y1="top" :y2="bottom" class="chart-axis" />
        <line
          :x1="left"
          :x2="left + width"
          :y1="bottom"
          :y2="bottom"
          class="chart-axis"
        />
        <g
          v-for="(bin, i) in chart.bins"
          :key="i"
          class="hist-bin"
          tabindex="0"
          role="img"
          :aria-label="description(i)"
          @mouseenter="hovered = i"
          @mouseleave="hovered = null"
          @focus="hovered = i"
          @blur="hovered = null"
        >
          <rect
            :x="x(bin.lower) + 1"
            :y="top"
            :width="Math.max(1, width / chart.bins.length - 2)"
            :height="height"
            fill="transparent"
          />
          <rect
            class="hist-bar"
            :x="x(bin.lower) + 1"
            :y="y(bin.count)"
            :width="Math.max(1, width / chart.bins.length - 2)"
            :height="bottom - y(bin.count)"
            rx="2"
          >
            <title>{{ description(i) }}</title>
          </rect>
        </g>
        <g v-for="(tick, i) in chart.xTicks" :key="'x' + i">
          <line
            :x1="x(tick)"
            :x2="x(tick)"
            :y1="bottom"
            :y2="bottom + 5"
            class="chart-axis"
          />
          <text
            :x="x(tick)"
            :y="bottom + 20"
            :text-anchor="i === 0 ? 'start' : i === 5 ? 'end' : 'middle'"
          >
            {{ chart.format(tick) }}
          </text>
        </g>
        <text
          :x="left + width / 2"
          y="237"
          text-anchor="middle"
          class="axis-label"
        >
          数值区间
        </text>
      </svg>
    </div>
    <p class="distribution-readout" aria-live="polite">
      {{
        hovered !== null && chart.bins[hovered]
          ? description(hovered)
          : "悬停或聚焦柱条，可查看对应区间和数量。"
      }}
    </p>
  </figure>
</template>
