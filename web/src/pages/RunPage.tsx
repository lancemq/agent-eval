import { RunWizard } from '../components/RunWizard'

export function RunPage() {
  return (
    <section>
      <div className="page-header">
        <h2>新建实验</h2>
      </div>
      <RunWizard />
    </section>
  )
}
