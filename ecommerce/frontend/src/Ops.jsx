import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, getOpsToken, setOpsToken } from './api'

export default function Ops() {
  const [token, setTokenState] = useState(getOpsToken())
  const [catalogue, setCatalogue] = useState(null)
  const [experiments, setExperiments] = useState([])
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ username: '', password: '' })
  const [faultId, setFaultId] = useState('slow_responses')
  const [loadId, setLoadId] = useState('browse_load')
  const [faultTarget, setFaultTarget] = useState('ecommerce-shop-api')
  const [loadTarget, setLoadTarget] = useState('ecommerce-shop-api')
  const [faultParams, setFaultParams] = useState({})
  const [loadParams, setLoadParams] = useState({})

  const fault = catalogue?.scenarios?.find((item) => item.id === faultId)
  const loadScenario = catalogue?.scenarios?.find((item) => item.id === loadId)

  async function refreshLab(activeToken = token) {
    if (!activeToken) return
    const [nextCatalogue, nextExperiments, nextStatus] = await Promise.all([
      api('/ops/scenarios', { token: activeToken }),
      api('/ops/experiments', { token: activeToken }),
      api('/ops/status', { token: activeToken }),
    ])
    setCatalogue(nextCatalogue)
    setExperiments(nextExperiments)
    setStatus(nextStatus)
  }

  useEffect(() => {
    if (!token) return undefined
    refreshLab().catch((err) => setError(err.message))
    const timer = setInterval(() => refreshLab().catch(() => {}), 3000)
    return () => clearInterval(timer)
  }, [token])

  useEffect(() => {
    if (!fault) return
    const next = {}
    Object.entries(fault.parameters).forEach(([name, rule]) => { next[name] = rule.default })
    setFaultParams(next)
    if (!fault.targets.includes(faultTarget)) setFaultTarget(fault.targets[0])
  }, [fault?.id])

  useEffect(() => {
    if (!loadScenario) return
    const next = {}
    Object.entries(loadScenario.parameters).forEach(([name, rule]) => { next[name] = rule.default })
    setLoadParams(next)
    if (!loadScenario.targets.includes(loadTarget)) setLoadTarget(loadScenario.targets[0])
  }, [loadScenario?.id])

  async function login(event) {
    event.preventDefault()
    setError('')
    try {
      const result = await api('/ops/login', { method: 'POST', body: form, token: '' })
      setOpsToken(result.access_token)
      setTokenState(result.access_token)
    } catch (err) {
      setError(err.message)
    }
  }

  async function start(kind) {
    setError('')
    try {
      const source = kind === 'fault' ? faultParams : loadParams
      const numbers = {}
      Object.entries(source).forEach(([key, value]) => { numbers[key] = Number(value) })
      await api(kind === 'fault' ? '/ops/faults' : '/ops/load', {
        method: 'POST',
        token,
        body: {
          scenario_id: kind === 'fault' ? faultId : loadId,
          target_service: kind === 'fault' ? faultTarget : loadTarget,
          parameters: numbers,
        },
      })
      await refreshLab()
    } catch (err) {
      setError(err.message)
    }
  }

  async function stop(kind) {
    setError('')
    try {
      await api(kind === 'fault' ? '/ops/faults/stop' : '/ops/load/stop', { method: 'POST', token })
      await refreshLab()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <main className="ops">
      <p><Link to="/">Back to the shop</Link></p>
      <h1>Fault and load lab</h1>
      <p className="warn">Development only. This page is absent unless the API was started with fault injection explicitly enabled. Experiments expire on their own, and the controls cannot run shell commands or change Docker.</p>
      {error && <div className="error">{error}</div>}
      {!token && (
        <form className="form" onSubmit={login}>
          <label className="field"><span>Operator name</span><input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} /></label>
          <label className="field"><span>Password</span><input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
          <button className="btn">Enter the lab</button>
        </form>
      )}
      {token && fault && loadScenario && (
        <>
          <div className="notice">
            Fault active: {String(status?.fault?.active)} · Load active: {String(status?.load?.active)} · Load requests: {status?.load?.stats?.requests ?? 0}
            {status?.experiment ? (
              <>
                {' '}· Experiment {status.experiment.id} is {status.experiment.outcome}
                {status.experiment.investigation_incident_id
                  ? ` · listed as incident ${status.experiment.investigation_incident_id}`
                  : ' · not listed on the investigation dashboard yet'}
              </>
            ) : ' · No experiment is running'}
          </div>
          <div className="ops-grid">
            <section className="card pad">
              <h2>Direct fault</h2>
              <label className="field"><span>Scenario</span>
                <select value={faultId} onChange={(event) => setFaultId(event.target.value)}>
                  {catalogue.scenarios.filter((item) => item.kind === 'fault').map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                </select>
              </label>
              <ScenarioFields scenario={fault} target={faultTarget} setTarget={setFaultTarget} params={faultParams} setParams={setFaultParams} />
              <div className="row">
                <button className="btn" onClick={() => start('fault')}>Start fault</button>
                <button className="btn-line" onClick={() => stop('fault')}>Stop fault</button>
              </div>
            </section>
            <section className="card pad">
              <h2>Load test</h2>
              <label className="field"><span>Scenario</span>
                <select value={loadId} onChange={(event) => setLoadId(event.target.value)}>
                  {catalogue.scenarios.filter((item) => item.kind === 'load').map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                </select>
              </label>
              <ScenarioFields scenario={loadScenario} target={loadTarget} setTarget={setLoadTarget} params={loadParams} setParams={setLoadParams} />
              <div className="row">
                <button className="btn" onClick={() => start('load')}>Start load</button>
                <button className="btn-line" onClick={() => stop('load')}>Stop load</button>
              </div>
              <p className="muted">Load tests call the real shop API. They do not switch on a fault flag. Run one experiment at a time so the telemetry stays readable.</p>
            </section>
          </div>
          <h2>Experiments</h2>
          <table>
            <thead><tr><th>ID</th><th>Kind</th><th>Scenario</th><th>Service</th><th>Outcome</th><th>Incident</th></tr></thead>
            <tbody>
              {experiments.map((item) => (
                <tr key={item.id}>
                  <td>{item.id}</td>
                  <td>{item.kind}</td>
                  <td>{item.scenario_id}</td>
                  <td>{item.target_service}</td>
                  <td>{item.outcome}</td>
                  <td>{item.investigation_incident_id ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  )
}

function ScenarioFields({ scenario, target, setTarget, params, setParams }) {
  return (
    <>
      <p>{scenario.expected_symptoms.join(' ')}</p>
      <label className="field"><span>Service</span>
        <select value={target} onChange={(event) => setTarget(event.target.value)}>
          {scenario.targets.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>
      {Object.entries(scenario.parameters).map(([name, rule]) => (
        <label className="field" key={name}>
          <span>{name} ({rule.min}–{rule.max})</span>
          <input type="number" min={rule.min} max={rule.max} value={params[name] ?? rule.default} onChange={(event) => setParams({ ...params, [name]: event.target.value })} />
        </label>
      ))}
    </>
  )
}
