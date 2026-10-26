<script setup lang="ts">
defineProps<{ kind: 'empty' | 'loading' | 'error' | 'success' | 'uncertain'; title: string; message: string; requestId?: string }>()
</script>
<template>
  <section class="notice" :class="kind" :role="kind === 'error' || kind === 'uncertain' ? 'alert' : 'status'" :aria-busy="kind === 'loading'">
    <h2>{{ title }}</h2><p>{{ message }}</p><small v-if="requestId">请求编号：{{ requestId }}</small><slot />
  </section>
</template>
