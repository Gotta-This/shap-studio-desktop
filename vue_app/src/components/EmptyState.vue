<script setup lang="ts">
import { FolderOpen } from "lucide-vue-next";
defineProps<{ title: string; description?: string }>();
</script>
<template>
  <div class="empty-state">
    <div class="empty-icon">
      <slot name="icon"><FolderOpen :size="25" :stroke-width="1.5" /></slot>
    </div>
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <slot />
  </div>
</template>
