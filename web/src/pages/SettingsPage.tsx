import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { EvalModelConfig, RunDefaults, WebSettings } from '../api/types'

const fallbackRunDefaults: RunDefaults = {
  agent: 'openai:gpt-4o-mini',
  output_dir: './eval_results',
  report_formats: ['json', 'html', 'markdown'],
  orchestrator: {
    max_workers: 2,
    queue_backend: 'memory',
    storage: { type: 'json', output_dir: './eval_results' },
    log_level: 'INFO',
  },
}

export function SettingsPage() {
  const [settings, setSettings] = useState<WebSettings | null>(null)
  const [secret, setSecret] = useState('')
  const [evalApiKey, setEvalApiKey] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.settings().then(setSettings).catch((error) => setMessage(error instanceof Error ? error.message : '配置加载失败'))
  }, [])

  if (!settings) return <section><div className="card"><h2>配置中心</h2><p className="muted">配置加载中...</p>{message && <p className="message">{message}</p>}</div></section>

  function updateRunDefaults(update: Partial<RunDefaults>) {
    setSettings((current) => current ? { ...current, run_defaults: { ...current.run_defaults, ...update } } : current)
  }

  function updateOrchestrator(update: Partial<RunDefaults['orchestrator']>) {
    setSettings((current) => current ? { ...current, run_defaults: { ...current.run_defaults, orchestrator: { ...current.run_defaults.orchestrator, ...update } } } : current)
  }

  function updateStorage(update: Partial<RunDefaults['orchestrator']['storage']>) {
    setSettings((current) => current ? { ...current, run_defaults: { ...current.run_defaults, orchestrator: { ...current.run_defaults.orchestrator, storage: { ...current.run_defaults.orchestrator.storage, ...update } } } } : current)
  }

  function updateEvalModel(update: Partial<EvalModelConfig>) {
    setSettings((current) => current ? { ...current, eval_model: { ...current.eval_model, ...update } } : current)
  }

  async function save() {
    if (!settings) return
    const saved = await api.saveSettings({
      run_defaults: settings.run_defaults,
      langfuse: { ...settings.langfuse, secret_key: secret },
      eval_model: { ...settings.eval_model, api_key: evalApiKey },
    })
    setSettings(saved)
    setSecret('')
    setEvalApiKey('')
    setMessage('配置已保存')
  }

  async function testLangfuse() {
    try {
      const result = await api.testLangfuse()
      setMessage(`Langfuse 连接成功：${result.host}，检查 sessions ${result.sessions_checked} 条`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '连接测试失败')
    }
  }

  return (
    <section>
      <div className="page-header">
        <h2>配置中心</h2>
        <button className="primary" onClick={save}>保存配置</button>
      </div>
      {message && <p className="message">{message}</p>}
      <div className="two-column">
        <div className="card form">
          <h3>评测默认配置</h3>
          <label>默认 Agent Spec</label>
          <input value={settings.run_defaults.agent} onChange={(event) => updateRunDefaults({ agent: event.target.value })} />
          <label>默认输出目录</label>
          <input value={settings.run_defaults.output_dir} onChange={(event) => updateRunDefaults({ output_dir: event.target.value })} />
          <label>报告格式，逗号分隔</label>
          <input value={settings.run_defaults.report_formats.join(', ')} onChange={(event) => updateRunDefaults({ report_formats: event.target.value.split(',').map((item) => item.trim()).filter(Boolean) })} />
          <div className="two-field-row">
            <div>
              <label>Max Workers</label>
              <input type="number" min="1" value={settings.run_defaults.orchestrator.max_workers} onChange={(event) => updateOrchestrator({ max_workers: Number(event.target.value) })} />
            </div>
            <div>
              <label>Log Level</label>
              <select value={settings.run_defaults.orchestrator.log_level} onChange={(event) => updateOrchestrator({ log_level: event.target.value })}>
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
            </div>
          </div>
          <label>Queue Backend</label>
          <input value={settings.run_defaults.orchestrator.queue_backend} onChange={(event) => updateOrchestrator({ queue_backend: event.target.value })} />
          <div className="two-field-row">
            <div>
              <label>Storage Type</label>
              <select value={settings.run_defaults.orchestrator.storage.type} onChange={(event) => updateStorage({ type: event.target.value })}>
                <option value="json">json</option>
                <option value="sqlite">sqlite</option>
                <option value="memory">memory</option>
              </select>
            </div>
            <div>
              <label>Storage Output Dir</label>
              <input value={settings.run_defaults.orchestrator.storage.output_dir} onChange={(event) => updateStorage({ output_dir: event.target.value })} />
            </div>
          </div>
        </div>

        <div>
          <div className="card form">
            <div className="section-title">
              <div>
                <h3>Langfuse 配置</h3>
                <p className="muted">保存到 .agent-eval/langfuse.json；secret 默认脱敏，留空不覆盖。</p>
              </div>
              <label className="switch-row"><input type="checkbox" checked={settings.langfuse.enabled} onChange={(event) => setSettings({ ...settings, langfuse: { ...settings.langfuse, enabled: event.target.checked } })} />启用</label>
            </div>
            <label>Host</label>
            <input value={settings.langfuse.host} onChange={(event) => setSettings({ ...settings, langfuse: { ...settings.langfuse, host: event.target.value } })} />
            <label>Public Key</label>
            <input value={settings.langfuse.public_key} onChange={(event) => setSettings({ ...settings, langfuse: { ...settings.langfuse, public_key: event.target.value } })} />
            <label>Secret Key</label>
            <input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={settings.langfuse.secret_configured ? '已配置；留空表示不修改' : '输入 secret key'} />
            <label>Project</label>
            <input value={settings.langfuse.project} onChange={(event) => setSettings({ ...settings, langfuse: { ...settings.langfuse, project: event.target.value } })} />
            <div className="actions-inline"><button onClick={testLangfuse}>测试连接</button></div>
          </div>
          <div className="card form">
            <h3>评测模型配置</h3>
            <p className="muted">打分器（LLM-as-Judge）使用的评测大模型。保存到 .agent-eval/eval-model.json；API Key 默认脱敏，留空不覆盖。</p>
            <label>模型</label>
            <input value={settings.eval_model.model} onChange={(event) => updateEvalModel({ model: event.target.value })} placeholder="gpt-4o-mini" />
            <label>API Key</label>
            <input type="password" value={evalApiKey} onChange={(event) => setEvalApiKey(event.target.value)} placeholder={settings.eval_model.api_key_configured ? '已配置；留空表示不修改' : '输入 API Key'} />
            <label>Base URL（可选）</label>
            <input value={settings.eval_model.base_url} onChange={(event) => updateEvalModel({ base_url: event.target.value })} placeholder="https://api.openai.com/v1" />
            <label>Timeout（秒）</label>
            <input type="number" min="1" max="300" value={settings.eval_model.timeout} onChange={(event) => updateEvalModel({ timeout: Number(event.target.value) })} />
          </div>
          <div className="card">
            <h3>Trace 配置</h3>
            <p className="muted">Trace 目录由服务启动参数控制，当前仅展示。</p>
            <div className="list-row"><span>本地 Trace 目录</span><code>{settings.trace.trace_dir}</code></div>
          </div>
        </div>
      </div>
    </section>
  )
}

export { fallbackRunDefaults }
