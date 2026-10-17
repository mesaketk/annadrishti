import type { Lang } from '../../types'
import { t } from '../drawer/i18n'
import { Icon, type IconName } from '../ui'
import { CARD, cx } from '../ui/m3'

// Generic national links; they do not resolve to a district-specific office.
const ITEMS: { k: string; icon: IconName; href: string }[] = [
  { k: 'kvk', icon: 'agriculture', href: 'https://kvk.icar.gov.in/' },
  { k: 'office', icon: 'account_balance', href: 'https://www.farmer.gov.in/' },
  { k: 'pmfby', icon: 'shield', href: 'https://pmfby.gov.in/' },
  { k: 'pds', icon: 'restaurant', href: 'https://nfsa.gov.in/' },
]
export default function HelpList({ lang }: { lang: Lang }) {
  return (
    <section aria-labelledby="help-h" className={cx(CARD, '!rounded-m3-lg p-4')}>
      <h3 id="help-h" className="mb-2 md-title-large text-on-surface">{t(lang, 'help.title')}</h3>
      <ul className="divide-y divide-outline-variant">
        {ITEMS.map((i) => (
          <li key={i.k}>
            <a href={i.href} target="_blank" rel="noopener noreferrer" className="md-state flex min-h-16 items-center gap-4 py-3 text-on-surface">
              <span aria-hidden className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-container text-on-primary-container"><Icon name={i.icon} size={22} /></span>
              <span className="min-w-0 flex-1">
                <span className="block md-title-medium">{t(lang, `help.${i.k}`)}</span>
                <span className="block md-body text-muted">{t(lang, `help.${i.k}.d`)}</span>
              </span>
              <Icon name="arrow_outward" size={20} className="text-on-surface-variant" />
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
