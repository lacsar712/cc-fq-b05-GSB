<template>
  <q-page class="page-pad">
    <div class="text-h5 q-mb-md">提交质控作业</div>

    <q-banner v-if="auth.role !== 'bioops'" class="bg-warning text-dark q-mb-md" rounded>
      审计员不可提交作业，请使用 bioops 账号。
    </q-banner>

    <q-card v-if="auth.role === 'bioops'" flat bordered class="q-mb-md">
      <q-card-section>
        <div class="text-subtitle1 q-mb-sm">容量门禁配置（落库生效，浏览器与服务端双拦）</div>
        <div class="row q-col-gutter-md items-center">
          <q-input
            v-model.number="cfgForm.maxChars"
            type="number"
            outlined
            dense
            label="最大字符数"
            :min="1"
            class="col-12 col-sm-4"
          />
          <q-input
            v-model.number="cfgForm.maxReads"
            type="number"
            outlined
            dense
            label="粗估最大读段数"
            :min="1"
            class="col-12 col-sm-4"
          />
          <q-toggle
            v-model="cfgForm.recordRejected"
            label="拒绝时写入 rejected 草稿记录"
            class="col-12 col-sm-4"
          />
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <div v-if="cfg" class="text-caption text-grey-7 q-mr-auto">
          最近由 {{ cfg.updated_by }} 更新：{{ fmtTime(cfg.updated_at) }}
        </div>
        <q-btn flat color="primary" label="保存配置" :loading="savingCfg" @click="saveCfg" />
      </q-card-actions>
    </q-card>

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
          class="q-mb-lg"
          hint="选样例开跑按样例内容长度校验，与粘贴框无关"
        />

        <div class="text-subtitle1 q-mb-sm">方式二：粘贴 FASTQ 文本</div>
        <q-input
          v-model="fastqText"
          type="textarea"
          outlined
          autogrow
          :input-style="{ minHeight: '160px', fontFamily: 'monospace' }"
          hint="四行一组：@header / 序列 / + / 质量串。若已选样例则优先用样例。"
        />
        <div
          class="row justify-between text-caption q-mt-xs"
          :class="pasteOver ? 'text-negative text-weight-bold' : 'text-grey-7'"
        >
          <span>当前 {{ pasteCharCount }} 字符 / 粗估 {{ pasteEstReads }} 读段</span>
          <span>上限 {{ cfg ? cfg.max_chars : '…' }} 字符 / {{ cfg ? cfg.max_reads : '…' }} 读段</span>
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat label="取消" to="/samples" />
        <q-btn color="primary" label="启动 Actor 流水线" :loading="submitting" @click="submit" />
      </q-card-actions>
    </q-card>
  </q-page>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import {
  createJob,
  getCapacityConfig,
  listSamples,
  updateCapacityConfig,
} from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const $q = useQuasar()

const samples = ref([])
const sampleId = ref(null)
const fastqText = ref('')
const submitting = ref(false)
const cfg = ref(null)
const savingCfg = ref(false)
const cfgForm = reactive({ maxChars: 0, maxReads: 0, recordRejected: true })

const sampleOptions = computed(() =>
  samples.value.map((s) => ({
    label: `${s.name}（${s.is_broken ? '损坏' : '合格'} · ${s.content_length} 字符）`,
    value: s.id,
  })),
)

const pasteCharCount = computed(() => fastqText.value.trim().length)

// 与服务端一致的粗估：FASTQ 四行一条，按行数 / 4 向上取整
function estimateReads(text) {
  if (!text) return 0
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  if (lines.length && lines[lines.length - 1] === '') lines.pop()
  return Math.ceil(lines.length / 4)
}

const pasteEstReads = computed(() => estimateReads(fastqText.value.trim()))

const pasteOver = computed(() => {
  if (!cfg.value || !fastqText.value.trim()) return false
  return (
    pasteCharCount.value > cfg.value.max_chars || pasteEstReads.value > cfg.value.max_reads
  )
})

function fmtTime(iso) {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

async function load() {
  try {
    const [sampleList, capacity] = await Promise.all([listSamples(), getCapacityConfig()])
    samples.value = sampleList
    applyCfg(capacity)
    const q = route.query.sampleId
    if (q) {
      sampleId.value = Number(q)
    }
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '加载样例/配置失败' })
  }
}

function applyCfg(capacity) {
  cfg.value = capacity
  cfgForm.maxChars = capacity.max_chars
  cfgForm.maxReads = capacity.max_reads
  cfgForm.recordRejected = capacity.record_rejected
}

async function saveCfg() {
  if (!Number.isInteger(cfgForm.maxChars) || cfgForm.maxChars < 1) {
    $q.notify({ type: 'warning', message: '最大字符数须为 ≥1 的整数' })
    return
  }
  if (!Number.isInteger(cfgForm.maxReads) || cfgForm.maxReads < 1) {
    $q.notify({ type: 'warning', message: '粗估最大读段数须为 ≥1 的整数' })
    return
  }
  savingCfg.value = true
  try {
    const capacity = await updateCapacityConfig({
      max_chars: cfgForm.maxChars,
      max_reads: cfgForm.maxReads,
      record_rejected: cfgForm.recordRejected,
    })
    applyCfg(capacity)
    $q.notify({ type: 'positive', message: '容量门禁配置已保存' })
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '保存配置失败' })
  } finally {
    savingCfg.value = false
  }
}

async function submit() {
  if (sampleId.value) {
    // 样例开跑：按样例内容长度校验，粘贴框为空也不受影响
    const s = samples.value.find((x) => x.id === sampleId.value)
    if (cfg.value && s) {
      if (s.content_length > cfg.value.max_chars || s.est_reads > cfg.value.max_reads) {
        $q.notify({
          type: 'negative',
          message: `样例超出容量门禁（${s.content_length} 字符 / 粗估 ${s.est_reads} 读段），请调整上限或更换样例`,
        })
        return
      }
    }
  } else {
    const text = fastqText.value.trim()
    if (!text) {
      $q.notify({ type: 'warning', message: '请选择样例或粘贴 FASTQ 文本' })
      return
    }
    if (cfg.value) {
      if (text.length > cfg.value.max_chars) {
        $q.notify({
          type: 'negative',
          message: `超出容量门禁：字符数 ${text.length} 超过上限 ${cfg.value.max_chars}`,
        })
        return
      }
      const est = estimateReads(text)
      if (est > cfg.value.max_reads) {
        $q.notify({
          type: 'negative',
          message: `超出容量门禁：粗估读段数 ${est} 超过上限 ${cfg.value.max_reads}`,
        })
        return
      }
    }
  }
  submitting.value = true
  try {
    const body = sampleId.value
      ? { sampleId: sampleId.value }
      : { fastqText: fastqText.value }
    const job = await createJob(body)
    $q.notify({ type: 'positive', message: `作业 #${job.id} 已创建` })
    router.push(`/jobs/${job.id}`)
  } catch (e) {
    $q.notify({ type: 'negative', message: e.message || '提交失败' })
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>
