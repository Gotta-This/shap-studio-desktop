<script setup lang="ts">
import { Badge } from "@/components/ui/badge";
defineProps<{ value: string }>();
</script>
<template>
  <Badge
    variant="secondary"
    :class="[
      'status-badge',
      {
        'tone-amber': value === '待补资料' || value === '高',
        'tone-purple': value === '返修中',
        'tone-green': value === '进行中' || value === '已完成',
        'tone-blue': value === '待交付',
      },
    ]"
    >{{ value }}</Badge
  >
</template>
