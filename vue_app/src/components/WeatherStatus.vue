<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { MapPin, RefreshCw } from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
const weather = ref<any>(null),
  busy = ref(false),
  error = ref("");
const open = ref(false),
  query = ref(""),
  results = ref<any[]>([]),
  searching = ref(false),
  searched = ref(false),
  searchError = ref("");
let timer: ReturnType<typeof setInterval> | undefined;
async function load(force = false) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    weather.value = await api("weather.current", { force });
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function search() {
  searching.value = true;
  searchError.value = "";
  results.value = [];
  searched.value = true;
  try {
    results.value = await api("weather.search", { query: query.value });
  } catch (e) {
    searchError.value = (e as Error).message;
  } finally {
    searching.value = false;
  }
}
async function choose(city: any) {
  searchError.value = "";
  try {
    await api("weather.choose", { location: city });
    weather.value = null;
    open.value = false;
    await load(true);
  } catch (e) {
    searchError.value = (e as Error).message;
  }
}
function updated(value: string) {
  return new Date(value).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
onMounted(() => {
  void load();
  timer = setInterval(
    () => {
      void load();
    },
    15 * 60 * 1000,
  );
});
onUnmounted(() => clearInterval(timer));
</script>
<template>
  <div class="weather-status">
    <button
      class="weather-chip"
      aria-label="天气与城市设置"
      @click="open = true"
    >
      <template v-if="weather?.configured"
        ><span aria-hidden="true">{{ weather.emoji }}</span
        ><strong>{{ weather.location.name }}</strong
        ><span
          >{{ weather.description }}
          {{ weather.temperature.toFixed(1) }}°C</span
        ><small v-if="weather.stale">上次天气</small></template
      >
      <template v-else
        ><MapPin :size="15" /><span>{{
          busy ? "正在更新天气…" : error ? "天气暂不可用" : "选择天气城市"
        }}</span></template
      >
    </button>
    <small v-if="weather?.configured" class="weather-updated"
      >{{ weather.stale ? "离线 · " : ""
      }}{{ updated(weather.updated_at) }} 更新 · Open-Meteo</small
    >
  </div>
  <Dialog v-model:open="open"
    ><DialogContent class="sm:max-w-md"
      ><DialogHeader
        ><DialogTitle>天气与城市</DialogTitle
        ><DialogDescription
          >选择要展示的城市，气温单位为 °C。天气由 Open-Meteo 提供，每 15
          分钟更新。<a
            href="https://open-meteo.com/"
            target="_blank"
            rel="noreferrer"
            >数据来源</a
          ></DialogDescription
        ></DialogHeader
      >
      <div v-if="weather?.configured" class="weather-current">
        <span
          >{{ weather.emoji }} {{ weather.location.label }} ·
          {{ weather.description }} {{ weather.temperature.toFixed(1) }}°C</span
        ><Button
          variant="outline"
          size="sm"
          :disabled="busy"
          @click="load(true)"
          ><RefreshCw :size="14" />刷新</Button
        >
      </div>
      <p v-if="error" role="alert" class="field-error">{{ error }}</p>
      <Button
        v-if="error"
        variant="outline"
        :disabled="busy"
        @click="load(true)"
        >重试天气</Button
      >
      <p v-if="weather?.stale" class="muted">
        网络暂不可用，当前显示上次更新的数据。
      </p>
      <form class="path-input" @submit.prevent="search">
        <Input
          v-model="query"
          aria-label="天气城市名称"
          placeholder="输入城市，如杭州或北京"
        /><Button
          type="submit"
          :disabled="searching || query.trim().length < 2"
          >{{ searching ? "查询中…" : "搜索城市" }}</Button
        >
      </form>
      <p v-if="searchError" role="alert" class="field-error">
        {{ searchError }}
      </p>
      <div class="weather-cities">
        <button
          v-for="city in results"
          :key="city.label + city.latitude"
          @click="choose(city)"
        >
          <MapPin :size="16" /><span>{{ city.label }}</span>
        </button>
        <p
          v-if="searched && !searching && !results.length && !searchError"
          class="muted"
        >
          未找到城市，请补充省份或使用城市拼音。
        </p>
      </div>
    </DialogContent></Dialog
  >
</template>
