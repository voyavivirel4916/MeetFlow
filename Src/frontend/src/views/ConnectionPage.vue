<script setup lang="ts">
import { ref } from 'vue'
import { ApiFailure, checkHealth } from '../api/client'
import StateNotice from '../components/StateNotice.vue'
const state = ref<'empty' | 'loading' | 'success' | 'error'>('empty')
const message = ref('点击检查，确认本机前后端能够连接。')
const requestId = ref<string>()
async function check() {
  if (state.value === 'loading') return
  state.value = 'loading'; message.value = '正在连接本机服务…'; requestId.value = undefined
  try {
    const result = await checkHealth()
    if (result.data?.status !== 'ok') throw new ApiFailure('protocol', '服务状态无法识别。')
    state.value = 'success'; message.value = '本机服务已连接，数据库可读取且结构版本正确。账户与会议业务将按后续步骤接入。'; requestId.value = result.request_id
  } catch (error) {
    state.value = 'error'; message.value = error instanceof ApiFailure ? error.message : '连接检查未完成。'; requestId.value = error instanceof ApiFailure ? error.requestId : undefined
  }
}
</script>
<template>
  <p class="eyebrow">MEETFLOW / 工程检查</p><h1>连接检查</h1>
  <StateNotice :kind="state" :title="state === 'success' ? '连接成功' : state === 'error' ? '连接失败' : '本机服务'" :message="message" :request-id="requestId">
    <button :disabled="state === 'loading'" @click="check">{{ state === 'loading' ? '正在检查…' : '检查连接' }}</button>
  </StateNotice>
</template>
