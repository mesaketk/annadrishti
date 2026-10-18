import { Icon } from './Icon'
import { cx } from './m3'

/** The two named AI features: Sanket = early-warning briefings (department briefing, state plan), Spark = advice and questions (farmer advice, Ask a question). */
export type AiFeature = 'sanket' | 'spark'
const NAME: Record<AiFeature, string> = { sanket: 'Sanket', spark: 'Spark' }
export const AI_NAME = NAME

export interface AiBadgeProps {
  feature: AiFeature
  /** `solid` gradient chip (default); `glass` translucent chip for use on top of a gradient surface (e.g. the FAB). */
  variant?: 'solid' | 'glass'
  size?: 'sm' | 'md'
  /** Hide the word and show the sparkle only. */
  iconOnly?: boolean
  className?: string
}
/** Gradient chip: sparkle icon + "Sanket" / "Spark". Tooltip: "Powered by Gemini". Import from `components/ui`. */
export function AiBadge({ feature, variant = 'solid', size = 'sm', iconOnly, className }: AiBadgeProps) {
  const name = NAME[feature]
  return (
    <span
      title="Powered by Gemini" aria-label={`${name}, powered by Gemini`}
      className={cx(
        'inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full font-medium',
        size === 'sm' ? 'h-6 px-2 md-label-medium' : 'h-8 px-3 md-label-large',
        variant === 'solid' ? 'ai-gradient shadow-[inset_0_0_0_1px_rgb(255_255_255/0.18)]' : 'bg-white/20 text-on-primary shadow-[inset_0_0_0_1px_rgb(255_255_255/0.35)]',
        className,
      )}
    >
      <Icon name="auto_awesome" fill size={size === 'sm' ? 14 : 18} />
      {!iconOnly && name}
    </span>
  )
}
