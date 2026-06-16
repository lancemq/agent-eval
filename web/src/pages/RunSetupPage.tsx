import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { PluginInfo, RunDefaults } from '../api/types'
import { CustomEvalBuilder } from '../components/CustomEvalBuilder'
import { PluginSelector } from '../components/PluginSelector'

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

function buildDefaultConfig(defaults: RunDefaults) {
  return {
    orchestrator: defaults.orchestrator,
    agent: { type: 'callable', module: '', config: { model: 'gpt-4o-mini', temperature: 0 } },
    plugins: {},
    eval_config: { priority: 'normal' },
    report: { formats: defaults.report_formats, output_dir: defaults.output_dir },
  }
}

export function RunSetupPage({ setPage, setActiveRunId, draftEvalConfig, clearDraftEvalConfig }: { setPage: (page: string) => void; setActiveRunId: (id: string) => void; draftEvalConfig?: any; clearDraftEvalConfig: () => void }) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([])
  const [selectedPlugins, setSelectedPlugins] = useState<string[]>([])
  const [runDefaults, setRunDefaults] = useState<RunDefaults>(fallbackRunDefaults)
  const [agent, setAgent] = useState(fallbackRunDefaults.agent)
  const [outputDir, setOutputDir] = useState(fallbackRunDefaults.output_dir)
  const [configText, setConfigText] = useState(JSON.stringify(buildDefaultConfig(fallbackRunDefaults), null, 2))
  const [message, setMessage] = useState('')

  useEffect(() => {
    api.plugins().then((items) => {
      setPlugins(items)
      setSelectedPlugins(items.slice(0, 1).map((plugin) => plugin.name))
    }).catch(console.error)
    api.settings().then((settings) => {
      setRunDefaults(settings.run_defaults)
      setAgent(settings.run_defaults.agent)
      setOutputDir(settings.run_defaults.output_dir)
      setConfigText(JSON.stringify(buildDefaultConfig(settings.run_defaults), null, 2))
    }).catch(console.error)
  }, [])

  useEffect(() => {
    if (!draftEvalConfig) return
    const nextConfig = { ...buildDefaultConfig(runDefaults), plugins: { custom_eval: draftEvalConfig } }
    setConfigText(JSON.stringify(nextConfig, null, 2))
    setSelectedPlugins((items) => items.includes('custom_eval') ? items : [...items, 'custom_eval'])
    setMessage('已载入 Trace 生成的 custom_eval 配置，请确认 Agent 后开始评测')
    clearDraftEvalConfig()
  }, [draftEvalConfig, clearDraftEvalConfig])

  const parsedConfig = useMemo(() => {
    try { return JSON.parse(configText) } catch { return null }
  }, [configText])

  async function validate() {
    if (!parsedConfig) return setMessage('配置 JSON 格式错误')
    const result = await api.validateConfig(parsedConfig)
    setMessage(result.valid ? `配置有效，warnings: ${result.warnings.length}` : JSON.stringify(result.errors))
  }

  function applyConfig(nextConfig: any) {
    setConfigText(JSON.stringify(nextConfig, null, 2))
    if (nextConfig.plugins?.custom_eval && !selectedPlugins.includes('custom_eval')) {
      setSelectedPlugins([...selectedPlugins, 'custom_eval'])
    }
  }

  async function startRun() {
    if (!parsedConfig) return setMessage('配置 JSON 格式错误')
    const mergedPlugins = { ...(parsedConfig.plugins || {}) }
    for (const name of selectedPlugins) {
      mergedPlugins[name] = { enabled: true, ...(mergedPlugins[name] || {}) }
    }
    const config = { ...parsedConfig, plugins: mergedPlugins }
    const run = await api.createRun({ agent, config, plugins: selectedPlugins, output_dir: outputDir })
    setActiveRunId(run.run_id)
    setPage('monitor')
  }

  return (
    <section>
      <div className="page-header"><h2>新建评测</h2></div>
      <div className="two-column">
        <div className="card form">
          <label>Agent Spec</label>
          <input value={agent} onChange={(event) => setAgent(event.target.value)} placeholder="openai:gpt-4o-mini 或 module:Class" />
          <label>输出目录</label>
          <input value={outputDir} onChange={(event) => setOutputDir(event.target.value)} />
          <label>配置 JSON</label>
          <textarea value={configText} onChange={(event) => setConfigText(event.target.value)} />
          <div className="actions">
            <button onClick={validate}>校验配置</button>
            <button className="primary" onClick={startRun}>开始评测</button>
          </div>
          {message && <p className="message">{message}</p>}
          <p className="muted">API key 不会保存在前端，请通过环境变量配置模型服务凭据。</p>
        </div>
        <div>
          <CustomEvalBuilder config={parsedConfig || buildDefaultConfig(runDefaults)} onApply={applyConfig} />
          <div className="card">
            <h3>选择插件</h3>
            <PluginSelector plugins={plugins} selected={selectedPlugins} onChange={setSelectedPlugins} />
          </div>
        </div>
      </div>
    </section>
  )
}
