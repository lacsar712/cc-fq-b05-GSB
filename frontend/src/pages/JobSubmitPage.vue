<template>
  <q-page class="page-pad">
    <div class="text-h5 q-mb-md">提交质控作业</div>

    <q-banner v-if="auth.role !== 'bioops'" class="bg-warning text-dark q-mb-md" rounded>
      审计员不可提交作业，请使用 bioops 账号。
    </q-banner>

    <q-card flat bordered>
      <q-card-section>
        <div class="text-subtitle1 q-mb-sm">方式一：选择 seed 样例</div>
        <q-select
          v-model="sampleId"
          :options="sampleOptions"
          label="样例"
          outlined
          dense
          clearable
          emit-value
          map-options
          class="q-mb-sm"
        />
        <div v-if="selectedSample" class="text-caption q-mb-lg">
          样例内容：{{ selectedSample.char_count }} 字符 · 粗估 {{ selectedSample.read_estimate }} 读段
        </div>
        <div v-else class="q-mb-lg" />

        <div class="text-subtitle1 q-mb-sm">方式二：粘贴 FASTQ 文本</div>
        <q-input
          v-model="fastqText"
          type="textarea"
          outlined
          autogrow
          :input-style="{ minHeight: '160px', fontFamily: 'monospace' }"
          hint="四行一组：@header / 序列 / + / 质量串。若已选样例则优先用样例。"
        />
        <div class="text-caption q-mt-xs" :class="violation ? 'text-negative' : 'text-grey-7'">
          {{ sizeHint }}
        </div>

        <q-toggle
          v-model="saveDraft"
          class="q-mt-md"
          label="超限时留存 rejected 草稿到历史（供查看拒绝原因）"
        />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat label="取消" to="/samples" />
        <q-btn
          color="primary"
          label="启动 Actor 流水线"
          :loading="submitting"
          :disable="auth.role !== 'bioops'"
          @click="submit"
        />
      </q-card-actions>
    </q-card>
  </q-page>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { createJob, getLimits, listSamples } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { limitViolation, measureContent } from '../utils/limits'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const $q = useQuasar()

const samples = ref([])
const sampleId = ref(null)
const fastqText = ref('')
const limits = ref(null)
const saveDraft = ref(true)
const submitting = ref(false)

const sampleOptions = computed(() =>
  samples.value.map((s) => ({
    label: `${s.name}（${s.is_broken ? '损坏' : '合格'}）`,
    value: s.id,
  })),
)

const selectedSample = computed(
  () => samples.value.find((s) => s.id === sampleId.value) || null,
)

const pasteSize = computed(() => measureContent(fastqText.value))

// 选了样例就按样例内容度量；否则按粘贴框，保证样例不受空粘贴框误伤
const effectiveSize = computed(() =>
  selectedSample.value
    ? {
        char_count: selectedSample.value.char_count,
        read_estimate: selectedSample.value.read_estimate,
      }
    : pasteSize.value,
)

const violation = computed(() => limitViolation(effectiveSize.value, limits.value))

const sizeHint = computed(() => {
  if (!limits.value) return '门禁配置加载中…'
  const s = effectiveSize.value
  const head = selectedSample.value ? '样例门禁' : '粘贴门禁'
  const base = `${head}：${s.char_count} / ${limits.value.max_chars} 字符 · 粗估 ${s.read_estimate} / ${limits.value.max_reads} 读段`
  return violation.value ? `${base} —— ${violation.value}` : base
})

async function load() {
  try {
    const [sampleList, lim] = await Promise.all([listSamples(), getLimits()])
    samples.value = sampleList
    limits.value = lim
    const q = route.query.sampleId
    if (q) {
      sampleId.value = Number(q)
    }
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载失败' })
  }
}

async function submit() {
  if (auth.role !== 'bioops') return
  if (!selectedSample.value && pasteSize.value.char_count === 0) {
    $q.notify({ type: 'warning', message: '请选择样例或粘贴非空 FASTQ 文本' })
    return
  }
  // 浏览器侧第一道门禁：超限先拦截确认；用户确认后仍交由服务端终裁，
  // 这样服务端可按选择写入 rejected 草稿供历史查看。
  if (violation.value) {
    const proceed = await new Promise((resolve) => {
      $q.dialog({
        title: '触发容量门禁',
        message:
          `${violation.value}。服务端将拒绝创建正式作业` +
          (saveDraft.value ? '，并留存一条 rejected 草稿到历史。' : '，且不会留存任何记录。'),
        ok: saveDraft.value ? '仍要提交并留草稿' : '仍要提交',
        cancel: '返回修改',
        dark: false,
      }).onOk(() => resolve(true)).onCancel(() => resolve(false))
    })
    if (!proceed) return
  }
  submitting.value = true
  try {
    const body = selectedSample.value
      ? { sampleId: selectedSample.value.id, saveRejectedDraft: saveDraft.value }
      : { fastqText: fastqText.value, saveRejectedDraft: saveDraft.value }
    const job = await createJob(body)
    $q.notify({ type: 'positive', message: `作业 #${job.id} 已创建队` })
    router.push(`/jobs/${job.id}`)
  } catch (e) {
    // 服务端兜底门禁（422）：结构化 detail
    const r = e.rejection
    if (r) {
      $q.notify({
        type: 'negative',
        message:
          r.draft_saved && r.draft_id
            ? `${r.reason}，已留存 rejected 草稿 #${r.draft_id}`
            : r.reason || '提交被拒绝',
        actions: r.draft_id
          ? [
              {
                label: '查看草稿',
                color: 'white',
                handler: () => router.push(`/jobs/${r.draft_id}`),
              },
            ]
          : [],
        timeout: 6000,
      })
    } else {
      $q.notify({ type: 'negative', message: e.message || '提交失败' })
    }
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>
