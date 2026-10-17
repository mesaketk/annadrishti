import { useStore } from '../lib/store'
import { navigate, type Role } from '../lib/route'
import { Icon, Modal, type IconName } from './ui'

export const ROLE_INFO: Record<Role, { icon: IconName; title: string; hint: string }> = {
  farmer: { icon: 'agriculture', title: 'Farmer', hint: 'Is my season risky? What should I sow? Where do I get help?' },
  officer: { icon: 'badge', title: 'District officer', hint: 'Is my district flagged, who is at risk, and what are my actions?' },
  planner: { icon: 'map', title: 'State planner', hint: 'Which districts first, how much to pre-position, which department does what.' },
}

export function chooseRole(r: Role) {
  useStore.getState().setRole(r)
  if (r === 'farmer') useStore.getState().setMode('now')
  navigate(r)
}

export default function RolePicker({ open, onClose, dismissible }: { open: boolean; onClose: () => void; dismissible: boolean }) {
  const role = useStore((s) => s.role)
  return (
    <Modal open={open} onClose={onClose} dismissible={dismissible} title="I am a…" widthClass="max-w-md" ariaLabel="Choose your role">
      <div className="space-y-3 px-6 pb-6 pt-2">
        <p className="md-body-medium text-muted">AnnaDrishti shows what the coming season could mean for food and farming. Pick what fits you best. You can change this any time from the top bar.</p>
        {(Object.keys(ROLE_INFO) as Role[]).map((r) => (
          <button
            key={r} type="button" onClick={() => { chooseRole(r); onClose() }}
            className={`md-state flex min-h-[72px] w-full items-center gap-4 rounded-m3-md border p-4 text-left transition-colors ${role === r ? 'border-transparent bg-secondary-container text-on-secondary-container' : 'border-outline-variant bg-surface-container-low text-on-surface'}`}
          >
            <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${role === r ? 'bg-primary text-on-primary' : 'bg-primary-container text-on-primary-container'}`} aria-hidden><Icon name={ROLE_INFO[r].icon} fill size={26} /></span>
            <span>
              <span className="block md-title-medium">{ROLE_INFO[r].title}</span>
              <span className={`block md-body-medium ${role === r ? 'text-on-secondary-container' : 'text-muted'}`}>{ROLE_INFO[r].hint}</span>
            </span>
          </button>
        ))}
      </div>
    </Modal>
  )
}
