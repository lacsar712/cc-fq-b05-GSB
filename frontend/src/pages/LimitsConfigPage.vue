<template>
  <q-page class="page-pad">
    <div class="text-h5 q-mb-md">容量门禁配置</div>

    <q-banner v-if="auth.role !== 'bioops'" class="bg-warning text-dark q-mb-md" rounded>
      审计员仅可查看，不能修改门禁配置。
    </q-banner>

    <q-card flat bordered style="max-width: 560px">
      <q-card-section>
        <div class="text-subtitle2 q-mb-md">
          粘贴/样例内容超过任一门禁时，服务端拒绝创建正式作业。
        </div>
        <q-input
          v-model.number="form.max_chars"
          label="最大字符数"
          type="number"
          outlined
          dense
          class="q-mb-md"
          :readonly="auth.role !== 'bioops'"
          hint="按去除首尾空白后的字符数计"
        />
        <q-input
          v-model.number="form.max_reads"
          label="粗估最大读段数"
          type="number"
          outlined
          dense
          :readonly="auth.role !== 'bioops'"
          hint="按非空行数 ÷ 4 向上取整粗估"
        />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          v-if="auth.role === 'bioops'"
          color="primary"
          label="保存配置"
          :loading="saving"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-page>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { getLimits, updateLimits } from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const $q = useQuasar()
const saving = ref(false)
const form = ref({ max_chars: null, max_reads: null })

async function load() {
  try {
    form.value = await getLimits()
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载门禁配置失败' })
  }
}

async function save() {
  const maxChars = Number(form.value.max_chars)
  const maxReads = Number(form.value.max_reads)
  if (!Number.isInteger(maxChars) || maxChars <= 0) {
    $q.notify({ type: 'warning', message: '最大字符数须为正整数' })
    return
  }
  if (!Number.isInteger(maxReads) || maxReads <= 0) {
    $q.notify({ type: 'warning', message: '粗估最大读段数须为正整数' })
    return
  }
  saving.value = true
  try {
    const saved = await updateLimits({ max_chars: maxChars, max_reads: maxReads })
    form.value = saved
    $q.notify({ type: 'positive', message: '门禁配置已保存并落库' })
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '保存失败' })
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
